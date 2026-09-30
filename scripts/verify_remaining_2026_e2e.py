"""Run ten synthetic progress profiles through the real local user-question API."""
from __future__ import annotations

import json
import hashlib
import sys
import threading
import urllib.request
from collections import Counter
from copy import deepcopy
from http.server import HTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]
from curriculum_assistant.graph import Graph, canonical  # noqa: E402
from curriculum_assistant.server import Handler  # noqa: E402
from curriculum_assistant.verifier import verify_payload  # noqa: E402
from generate_remaining_fixtures import DEST, make_fixtures  # noqa: E402
from generate_mock_2026_transcripts import catalog_v1  # noqa: E402

RESULTS = ROOT / "evaluation/results/remaining_2026_e2e_results.json"
REPORT = ROOT / "evaluation/results/remaining_2026_e2e_report.md"
QUESTIONS = (
    ("충족", "지금까지 어떤 졸업요건을 충족했어?", "REQUIREMENT_GAPS"),
    ("부족", "뭐가 부족해?", "REQUIREMENT_GAPS"),
    ("전필", "전필 뭐 남았어?", "REMAINING_PLAN"),
    ("학점", "앞으로 몇 학점 더 필요해?", "REMAINING_PLAN"),
    ("후보", "앞으로 뭐 더 들어야 해?", "REMAINING_PLAN"),
    ("가정", "이 과목 하나 추가하면 뭐가 바뀌어?", "WHAT_IF"),
    ("졸업", "지금 졸업 가능해?", "GRADUATION_STATUS"),
)


def post(port: int, state: dict, utterance: str, *, context: dict | None = None,
         use_local_llm: bool = False) -> dict:
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}/api/query",
        data=json.dumps({"student_state": state, "utterance": utterance,
                         "context": context or {}, "use_local_llm": use_local_llm}, ensure_ascii=False).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=100) as response:
        result = json.load(response)
    if "decision" not in result:
        raise AssertionError(f"Question was not executed: {utterance}: {result}")
    verify_payload(result)
    return result


def core(result: dict) -> dict:
    decision = result["decision"]
    return {"decision_status": decision["decision_status"],
            "graduation_outcome": decision["graduation_outcome"],
            "rule_statuses": {r["rule_id"]: r["status"] for r in decision["requirement_results"]},
            "total": decision["credited_amount"]["total"],
            "by_area": decision["credited_amount"]["by_area"],
            "missing_courses": decision["missing_courses"],
            "evidence_source_ids": sorted(result["evidence"]["source_locators"])}


def check_expected(result: dict, fixture: dict, intent: str) -> None:
    expected = fixture["expected"]
    decision = result["decision"]
    assert decision["intent"] == intent, (fixture["fixture_id"], decision["intent"], intent)
    assert decision["ruleset_id"] == fixture["ruleset_id"] and decision["ruleset_version"] == 1
    assert len(decision["recognitions"]) == expected["course_count"]
    observed_statuses = {r["rule_id"]: r["status"] for r in decision["requirement_results"]}
    assert observed_statuses == expected["expected_requirement_results"], (fixture["fixture_id"], intent,
        {rid: (expected["expected_requirement_results"].get(rid), observed_statuses.get(rid))
         for rid in observed_statuses.keys() | expected["expected_requirement_results"].keys()
         if observed_statuses.get(rid) != expected["expected_requirement_results"].get(rid)})
    assert decision["credited_amount"]["total"] == expected["expected_total_credits"]
    assert decision["credited_amount"]["by_area"]["MAJOR_TOTAL"] == expected["expected_major_credits"]
    if intent == "GRADUATION_STATUS":
        assert decision["graduation_outcome"] == expected["expected_final_decision"]
    if intent == "REMAINING_PLAN":
        actual = {c["course_id"]: c["candidate_status"] for c in decision["candidate_courses"]}
        assert all(status == expected["candidate_status_by_course"].get(code) for code, status in actual.items()), (
            fixture["fixture_id"], {code: (expected["candidate_status_by_course"].get(code), status)
                                  for code, status in actual.items() if status != expected["candidate_status_by_course"].get(code)})
        if result["interpretation"]["structured_query"].get("focus") == "ALL":
            assert actual == expected["candidate_status_by_course"]
        summary = decision["remaining_requirements"]
        assert summary["unsatisfied_requirements"] == sorted(
            rid for rid, status in expected["expected_requirement_results"].items() if status == "UNSATISFIED")
        for rule_id, value in expected["expected_missing_amount"].items():
            assert decision["missing_amount"][rule_id] == value
        assert set(summary["missing_required_courses"] or []) == set(
            expected["expected_missing_courses"].get("R-CE-2026-REQUIRED-COURSES", []))
        active = [c for c in decision["candidate_courses"] if c["candidate_status"] in {"REQUIRED", "ELIGIBLE_OPTION"}]
        assert all(c["relationship_ids"] and c["satisfies_requirement_ids"] and c["provenance"]["source"]["pdf_page"]
                   and c["next_term_offering_status"] == "NOT_VERIFIED" for c in active)
        assert all(c["candidate_status"] != "REQUIRED" for c in decision["candidate_courses"] if c["already_completed"])
    if intent == "WHAT_IF":
        scenario = result["scenario_decision"]
        assert scenario and result["scenario_delta"]["status"] == "CALCULATED"
        assert {r["rule_id"]: r["status"] for r in scenario["requirement_results"]} == expected["simulation_expected"]["expected_requirement_results"]
        assert scenario["credited_amount"]["total"] == expected["simulation_expected"]["expected_total_credits"]
        delta = result["scenario_delta"]
        before_required = expected["expected_missing_courses"].get("R-CE-2026-REQUIRED-COURSES", [])
        after_required = expected["simulation_expected"]["expected_missing_courses"].get("R-CE-2026-REQUIRED-COURSES", [])
        assert delta["missing_required_before"] == before_required
        assert delta["missing_required_after"] == after_required
        assert delta["completed_required_course_ids"] == sorted(set(before_required) - set(after_required))


def reviewer(port: int, fixtures: list[dict]) -> list[dict]:
    by_id = {f["fixture_id"]: f for f in fixtures}
    findings = []
    def record(name: str, fn) -> None:
        fn()
        findings.append({"case": name, "status": "PASS"})
    early = by_id["year1_early"]["student_state"]
    late = by_id["year1_late"]["student_state"]
    complete = by_id["year4_late"]["student_state"]
    def same_year_different_state():
        a = post(port, early, "앞으로 뭐 더 들어야 해?")
        b = post(port, late, "앞으로 뭐 더 들어야 해?")
        assert a["decision"]["credited_amount"] != b["decision"]["credited_amount"]
        assert a["decision"]["remaining_requirements"] != b["decision"]["remaining_requirements"]
    record("same_year_different_completions", same_year_different_state)
    def different_year_same_state():
        a, b = deepcopy(late), deepcopy(late)
        a["grade_label"] = "1학년"
        b["grade_label"] = "4학년"
        assert core(post(port, a, "앞으로 뭐 더 들어야 해?")) == core(post(port, b, "앞으로 뭐 더 들어야 해?"))
    record("same_completions_different_grade_label", different_year_same_state)
    def input_order():
        reverse = deepcopy(late)
        reverse["course_attempts"].reverse()
        a, b = post(port, late, "전필 뭐 남았어?"), post(port, reverse, "전필 뭐 남았어?")
        assert core(a) == core(b)
        assert a["decision"]["candidate_courses"] == b["decision"]["candidate_courses"]
    record("input_order_invariance", input_order)
    def duplicate_attempt():
        duplicate = deepcopy(complete)
        attempt = deepcopy(duplicate["course_attempts"][0])
        attempt["attempt_id"] += "-RETAKE"
        attempt["evidence_id"] += "-RETAKE"
        duplicate["course_attempts"].append(attempt)
        result = post(port, duplicate, "앞으로 뭐 더 들어야 해?")
        observed = result["decision"]["credited_amount"]["total"]
        baseline = post(port, complete, "앞으로 뭐 더 들어야 해?")["decision"]["credited_amount"]["total"]
        assert observed is None or observed <= baseline
        assert not any(c["candidate_status"] == "REQUIRED" and c["course_id"] == attempt["course_id"]
                       for c in result["decision"]["candidate_courses"])
    record("duplicate_completion_not_recommended", duplicate_attempt)
    def missing_record():
        unknown = deepcopy(late)
        unknown["course_attempts"].append({"attempt_id": "TEST-UNKNOWN", "course_id": "ZZZ9999",
            "completion_status": "COMPLETED", "verification_status": "VERIFIED", "evidence_id": "TEST:UNKNOWN",
            "earned_credits": None})
        result = post(port, unknown, "앞으로 뭐 더 들어야 해?")
        assert result["decision"]["decision_status"] == "NEEDS_INFORMATION" or result["decision"]["needs_information"]
        assert result["decision"]["remaining_requirements"]["needs_information"]
        assert not any(c["course_id"] == "ZZZ9999" for c in result["decision"]["candidate_courses"])
    record("unknown_course_not_invented", missing_record)
    def multiple_additions():
        fixture = by_id["year1_early"]
        selected = [code for code in fixture["expected"]["candidate_status_by_course"]
                    if fixture["expected"]["candidate_status_by_course"][code] == "REQUIRED"][:2]
        assert len(selected) == 2
        original = canonical(early)
        result = post(port, early, f"{selected[0]}와 {selected[1]}를 추가로 들으면 뭐가 바뀌어?")
        assert result["interpretation"]["structured_query"]["intent"] == "WHAT_IF"
        assert len(result["scenario_decision"]["recognitions"]) == len(early["course_attempts"]) + 2
        assert canonical(early) == original
    record("two_course_simulation_keeps_original", multiple_additions)
    def why_course():
        fixture = by_id["required_missing"]
        code = fixture["expected"]["simulation_course_id"]
        result = post(port, fixture["student_state"], "왜 이 과목 더 들어야 해?",
                      context={"last_course_id": code})
        assert result["decision"]["intent"] == "REMAINING_PLAN"
        assert result["decision"]["requested_course_id"] == code
        assert code in result["answer_text"]
        candidate = next(c for c in result["decision"]["candidate_courses"] if c["course_id"] == code)
        assert candidate["candidate_status"] == "REQUIRED" and candidate["relationship_ids"]
    record("why_course_uses_queried_relationship", why_course)
    return findings


def main() -> None:
    catalog = catalog_v1()
    pdf_path = ROOT / "docs/curriculum/2026년도 교육과정.pdf"
    assert hashlib.sha256(pdf_path.read_bytes()).hexdigest() == catalog["source_sha256"]
    import pdfplumber
    with pdfplumber.open(pdf_path) as pdf:
        page_text = {page: pdf.pages[page - 1].extract_text() or ""
                     for page in {course["source"]["pdf_page"] for course in catalog["courses"]}}
    assert all(course["course_id"] in page_text[course["source"]["pdf_page"]]
               for course in catalog["courses"])
    class BoundHandler(Handler):
        pass
    server = HTTPServer(("127.0.0.1", 0), BoundHandler)
    port = server.server_address[1]
    ready = threading.Event()
    def run_server() -> None:
        graph = Graph(Path(":memory:"), catalog)
        BoundHandler.graph = graph
        ready.set()
        try:
            server.serve_forever()
        finally:
            graph.close()
    thread = threading.Thread(target=run_server, daemon=True)
    thread.start()
    if not ready.wait(timeout=10):
        raise RuntimeError("Local E2E server did not initialize")
    details = []
    try:
        fixtures = make_fixtures()
        for fixture in fixtures:
            fid = fixture["fixture_id"]
            saved = json.loads((DEST / f"{fid}.json").read_text(encoding="utf-8"))
            assert fixture == saved
            state = deepcopy(fixture["student_state"])
            before = canonical(state)
            context = {"last_course_id": fixture["expected"]["simulation_course_id"]}
            query_rows = []
            payloads = {}
            for label, question, intent in QUESTIONS:
                result = post(port, state, question, context=context if label == "가정" else None)
                check_expected(result, fixture, intent)
                assert canonical(state) == before
                payloads[label] = result
                query_rows.append({"label": label, "question": question, "intent": intent,
                                   "answer": result["answer_text"],
                                   "decision_status": result["decision"]["decision_status"],
                                   "graduation_outcome": result["decision"]["graduation_outcome"],
                                   "execution_id": result["execution_trace"]["execution_id"],
                                   "event_count": len(result["execution_trace"]["events"])})
            plan = payloads["후보"]["decision"]
            on = post(port, state, "앞으로 뭐 더 들어야 해?", use_local_llm=True)
            assert core(on) == core(payloads["후보"])
            assert on["decision"]["candidate_courses"] == plan["candidate_courses"]
            assert on["evidence"] == payloads["후보"]["evidence"]
            assert on["execution_trace"] == payloads["후보"]["execution_trace"]
            assert canonical(state) == before
            details.append({"fixture_id": fid, "grade_label_metadata_only": fixture["grade_label_metadata_only"],
                            "course_count": len(state["course_attempts"]),
                            "total_credits": plan["credited_amount"]["total"],
                            "satisfied": plan["remaining_requirements"]["satisfied_requirements"],
                            "unsatisfied": plan["remaining_requirements"]["unsatisfied_requirements"],
                            "needs_information": plan["remaining_requirements"]["needs_information"],
                            "missing_credits": plan["remaining_requirements"]["missing_credits_by_category"],
                            "missing_required_courses": plan["remaining_requirements"]["missing_required_courses"],
                            "candidate_counts": dict(Counter(c["candidate_status"] for c in plan["candidate_courses"])),
                            "required_candidates": [c["course_id"] for c in plan["candidate_courses"] if c["candidate_status"] == "REQUIRED"],
                            "option_candidates": [c["course_id"] for c in plan["candidate_courses"] if c["candidate_status"] == "ELIGIBLE_OPTION"],
                            "simulation_course_id": fixture["expected"]["simulation_course_id"],
                            "simulation_delta": payloads["가정"]["scenario_delta"],
                            "expected_graduation": fixture["expected"]["expected_final_decision"],
                            "actual_graduation": payloads["졸업"]["decision"]["graduation_outcome"],
                            "llm_on_off_identical": True,
                            "llm_expression_status": on.get("llm_expression", {}).get("status"),
                            "queries": query_rows})
            print(f"{fid}: 7 API queries + LLM ON, {len(state['course_attempts'])} courses, "
                  f"{details[-1]['actual_graduation']}", flush=True)
        review = reviewer(port, fixtures)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
    RESULTS.parent.mkdir(parents=True, exist_ok=True)
    RESULTS.write_text(json.dumps({"notice": "SYNTHETIC TEST DATA ONLY / 실제 학생 자료 아님",
                                   "ruleset_id": "CRS-CE-2026-CORE", "ruleset_version": 1,
                                   "profiles": details, "reviewer": review}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = ["# 남은 졸업요건·과목 후보 E2E 검증", "", "RuleSet v1의 VERIFIED 과목과 수치만으로 만든 테스트용 StudentState를 사용했다. 학년은 메타데이터다.", "",
             "| 프로필 | 과목 수 | 총학점 | 충족/미충족/확인필요 | 필수 후보 | 선택 후보 | 가정학점 변화 | 졸업 결과 |",
             "| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |"]
    for d in details:
        lines.append(f"| {d['fixture_id']} | {d['course_count']} | {d['total_credits']} | "
                     f"{len(d['satisfied'])}/{len(d['unsatisfied'])}/{len(d['needs_information'])} | "
                     f"{len(d['required_candidates'])} | {len(d['option_candidates'])} | "
                     f"{d['simulation_delta']['total_credit_change']} | {d['actual_graduation']} |")
    lines += ["", "각 프로필마다 7개 한국어 질문을 `/api/query`에 보내고 StructuredQuery, RuleSet 고정, 요건 상태, 학점, 후보 상태, provenance, 가상 변화, LLM ON/OFF 핵심 일치를 검증했다.",
              f"LLM 표현 결과 상태: {dict(Counter(d['llm_expression_status'] for d in details))}.",
              f"Verifier: 공식 PDF SHA-256과 VERIFIED 과목 {len(catalog['courses'])}개의 코드/인용 페이지를 원문 텍스트로 대조했다. 후보의 SATISFIES 간선·요건 출처는 payload verifier로 검사했다.",
              "실제 다음 학기 개설·선수과목은 공식 확인 자료가 없어 NOT_VERIFIED다. 모든 70개 실제 질문·답변은 결과 JSON에 있다.", ""]
    for d in details:
        missing = {key: value for key, value in d["missing_credits"].items() if value is not None and value > 0}
        delta = d["simulation_delta"]
        lines += [f"## {d['fixture_id']}", "",
                  f"- 충족 요건: {', '.join(d['satisfied']) or '없음'}.",
                  f"- 미충족 요건: {', '.join(d['unsatisfied']) or '없음'}; 확인 필요: {', '.join(d['needs_information']) or '없음'}.",
                  f"- 부족 학점: {json.dumps(missing, ensure_ascii=False)}; 미이수 지정 필수: {', '.join(d['missing_required_courses'] or []) or '없음'}.",
                  f"- REQUIRED: {', '.join(d['required_candidates']) or '없음'}; ELIGIBLE_OPTION: {len(d['option_candidates'])}건(과목코드순 앞 10건: {', '.join(d['option_candidates'][:10]) or '없음'}). 전 목록은 JSON에 있다.",
                  f"- 가정 과목 {d['simulation_course_id']}: 총학점 {delta['total_credit_change']:+d}, 전공학점 {delta['major_credit_change']:+d}; "
                  f"미이수 필수에서 제외 {', '.join(delta['completed_required_course_ids'] or []) or '없음'}; "
                  f"졸업판정 미리보기 {delta['graduation_preview_before']} → {delta['graduation_preview_after']}; 원본 StudentState 불변.",
                  f"- 사용자 질문 7건: " + ", ".join(f"{q['label']}={q['intent']}" for q in d["queries"]) + f"; 기대/실제 졸업 결과 {d['expected_graduation']}/{d['actual_graduation']}.", ""]
    lines += ["## Reviewer 반례", ""]
    lines += [f"- {r['case']}: {r['status']}" for r in review]
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"PASS: {len(details)} profiles, {len(details)*7} user queries, {len(review)} reviewer cases")


if __name__ == "__main__":
    main()
