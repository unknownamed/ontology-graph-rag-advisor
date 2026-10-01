"""Local Ollama interpreter with deterministic entity and intent guardrails."""
from __future__ import annotations

import json
import time
import urllib.request
from copy import deepcopy
from collections.abc import Callable

from .nlp import _entities, _norm, interpret

INTENTS = {"COURSE_LOOKUP", "CREDIT_SUMMARY", "REQUIREMENT_GAPS", "REMAINING_PLAN", "WHAT_IF", "GRADUATION_STATUS", "UNCLEAR"}
SCHEMA = {"type": "object", "properties": {
    "intent": {"type": "string", "enum": sorted(INTENTS)},
    "course_mention": {"type": ["string", "null"]}},
    "required": ["intent", "course_mention"], "additionalProperties": False}
SYSTEM_PROMPT = (
    "당신은 대학 교육과정 질문 분류기입니다. 답변하지 말고 JSON만 출력하세요. "
    "의도 우선순위: (1) 졸업 가능한지 물으면 GRADUATION_STATUS, 남은 필수를 함께 물어도 동일. "
    "(2) 특정 과목을 추가로 들으면/이수하면/가정하면 WHAT_IF, 학점 변화를 함께 물어도 동일. "
    "(3) 특정 과목 자체의 학점/이수구분은 COURSE_LOOKUP. "
    "(4) 지금까지 인정된 전체 학점은 CREDIT_SUMMARY. "
    "(5) 앞으로 이수할 과목 후보나 영역별 진행도를 물으면 REMAINING_PLAN. "
    "(6) 남은 필수나 부족한 요건만 물으면 REQUIREMENT_GAPS. 불명확하면 UNCLEAR. "
    "course_mention에는 현재 사용자 문장에서 실제로 언급된 과목 표현만 그대로 복사하세요. 없으면 null입니다. "
    "학점, 판정, 교육과정 사실을 생성하지 마세요."
)
EXPRESSION_SCHEMA = {"type": "object", "properties": {
    "style": {"type": "string", "enum": ["DIRECT", "CONVERSATIONAL"]}},
    "required": ["style"], "additionalProperties": False}


def _ollama_call(question: str, *, model: str = "qwen3:8b") -> tuple[dict, dict]:
    body = {"model": model, "stream": False, "think": False, "format": SCHEMA,
            "options": {"temperature": 0, "num_predict": 120}, "keep_alive": "5m",
            "messages": [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": question}]}
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request("http://127.0.0.1:11434/api/chat", data=data,
                                     headers={"Content-Type": "application/json"})
    start = time.perf_counter()
    with urllib.request.urlopen(request, timeout=15) as response:
        raw = json.load(response)
    suggestion = json.loads(raw["message"]["content"])
    metrics = {"model": model, "wall_seconds": round(time.perf_counter() - start, 3),
               "prompt_tokens": raw.get("prompt_eval_count"), "output_tokens": raw.get("eval_count")}
    return suggestion, metrics


def interpret_with_local_llm(question: str, catalog: dict, context: dict | None = None,
                             transport: Callable[[str], tuple[dict, dict]] | None = None) -> dict:
    """Let Ollama suggest wording; code validates IDs and keeps deterministic precedence."""
    deterministic = interpret(question, catalog, context)
    deterministic_intent = (deterministic.get("structured_query") or {}).get("intent")
    if deterministic_intent == "POLICY_LOOKUP":
        return {**deterministic, "llm": {"status": "NOT_USED_FOR_POLICY_LOOKUP"}}
    if deterministic_intent in {"CATALOG_AGGREGATE", "ENTITY_CHECK", "CONSISTENCY_CHECK", "TRACE_EXPLAIN", "REMAINING_PLAN", "PLACEMENT_LOOKUP"} or (deterministic.get("structured_query") or {}).get("placement_requested"):
        return {**deterministic, "llm": {"status": "NOT_USED_FOR_DETERMINISTIC_QUERY"}}
    try:
        suggestion, metrics = (transport or _ollama_call)(question)
    except (OSError, ValueError, KeyError, TimeoutError, json.JSONDecodeError) as error:
        return {**deterministic, "llm": {"status": "UNAVAILABLE_OR_INVALID", "reason": type(error).__name__}}
    if set(suggestion) != {"intent", "course_mention"} or suggestion["intent"] not in INTENTS or not isinstance(suggestion["course_mention"], (str, type(None))):
        return {**deterministic, "llm": {"status": "REJECTED_SCHEMA", **metrics}}
    mention = suggestion["course_mention"]
    if mention is not None and _norm(mention) not in _norm(question):
        return {**deterministic, "llm": {"status": "REJECTED_INVENTED_MENTION", **metrics}}
    if deterministic["interpretation_status"] == "RESOLVED":
        if suggestion["intent"] != deterministic["structured_query"]["intent"]:
            return {**deterministic, "llm": {"status": "REJECTED_INTENT_MISMATCH", "suggested_intent": suggestion["intent"], **metrics}}
        return {**deterministic, "llm": {"status": "VALIDATED_SUGGESTION", "suggested_intent": suggestion["intent"], **metrics}}
    if not mention:
        return {**deterministic, "llm": {"status": "NO_VERIFIED_ENTITY", **metrics}}
    codes, ambiguity = _entities(mention, catalog)
    if ambiguity or len(codes) != 1:
        return {**deterministic, "llm": {"status": "ENTITY_AMBIGUOUS_OR_UNKNOWN", **metrics}}
    intent = suggestion["intent"]
    clean = _norm(question)
    evidence_cue = {
        "WHAT_IF": ("들으면", "이수하면", "추가", "가정", "하면"),
        "GRADUATION_STATUS": ("졸업",),
        "CREDIT_SUMMARY": ("학점", "인정"),
        "REQUIREMENT_GAPS": ("필수", "부족", "남"),
        "COURSE_LOOKUP": ("학점", "구분", "영역", "과목"),
    }.get(intent, ())
    if not evidence_cue or not any(term in clean for term in evidence_cue):
        return {**deterministic, "llm": {"status": "REJECTED_INTENT_WITHOUT_TEXT_CUE", **metrics}}
    query = {"intent": intent, "course_id": codes[0]}
    if intent == "WHAT_IF":
        query["assumed_completion"] = "SUCCESS"
    return {"interpretation_status": "RESOLVED", "ambiguities": [], "structured_query": query,
            "context": {"last_course_id": codes[0]}, "llm": {"status": "ACCEPTED_VERIFIED_SUGGESTION", **metrics}}


def _ollama_expression_call(locked_answer: str, *, model: str = "qwen3:8b") -> tuple[dict, dict]:
    """The model selects wording only; it cannot submit facts or a decision."""
    body = {"model": model, "stream": False, "think": False, "format": EXPRESSION_SCHEMA,
            "options": {"temperature": 0, "num_predict": 30}, "keep_alive": "5m",
            "messages": [{"role": "system", "content": "검증된 한국어 답변의 말투만 선택하세요. JSON style 값은 DIRECT 또는 CONVERSATIONAL 중 하나입니다. 수치·조건·판정·근거를 작성하거나 수정하지 마세요."},
                         {"role": "user", "content": locked_answer}]}
    request = urllib.request.Request("http://127.0.0.1:11434/api/chat",
                                     data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
                                     headers={"Content-Type": "application/json"})
    start = time.perf_counter()
    with urllib.request.urlopen(request, timeout=15) as response:
        raw = json.load(response)
    return json.loads(raw["message"]["content"]), {"model": model,
        "wall_seconds": round(time.perf_counter() - start, 3),
        "prompt_tokens": raw.get("prompt_eval_count"), "output_tokens": raw.get("eval_count")}


def express_with_local_llm(payload: dict, transport: Callable[[str], tuple[dict, dict]] | None = None) -> dict:
    """Use a local model for a bounded Korean expression choice, then reverify."""
    from .render import render_answer
    from .verifier import verify_payload
    result = deepcopy(payload)
    try:
        suggestion, metrics = (transport or _ollama_expression_call)(render_answer(result))
    except (OSError, ValueError, KeyError, TimeoutError, json.JSONDecodeError) as error:
        result["llm_expression"] = {"status": "UNAVAILABLE_OR_INVALID", "reason": type(error).__name__}
        return result
    if not isinstance(suggestion, dict) or set(suggestion) != {"style"} or suggestion["style"] not in {"DIRECT", "CONVERSATIONAL"}:
        result["llm_expression"] = {"status": "REJECTED_SCHEMA", **metrics}
        return result
    result["answer_style"] = suggestion["style"]
    result["answer_text"] = render_answer(result)
    result["llm_expression"] = {"status": "VERIFIED_STYLE", **metrics}
    verify_payload(result)
    return result
