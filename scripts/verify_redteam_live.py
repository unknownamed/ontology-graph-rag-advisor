"""Independent five-scenario API check matching the acceptance browser walkthrough."""
from __future__ import annotations

import json
import sys
import urllib.request
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from curriculum_assistant.verifier import verify_payload  # noqa: E402


def post(port: int, state: dict, utterance: str, use_local_llm: bool) -> dict:
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}/api/query",
        data=json.dumps({"student_state": state, "utterance": utterance,
                         "use_local_llm": use_local_llm}, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=45) as response:
        return json.load(response)


def graph_counts(payload: dict) -> tuple[int, int]:
    used = {edge_id for result in payload["requirement_results"]
            for edge_id in result["used_relationship_ids"]}
    for decision in (payload["decision"], payload.get("scenario_decision")):
        if not decision:
            continue
        used.update(edge_id for recognition in decision.get("recognitions", [])
                    for edge_id in recognition["relationship_ids"])
        used.update(edge_id for result in decision.get("requirement_results", [])
                    for edge_id in result["used_relationship_ids"])
        lookup = decision.get("lookup_result") or {}
        used.update(lookup.get("relationship_ids", []))
    edges = [edge for edge in payload["evidence"]["relationship_details"] if edge["id"] in used]
    nodes = {node for edge in edges for node in (edge["src"], edge["dst"])}
    return len(edges), len(nodes)


def main(port: int) -> None:
    fixture = json.loads((ROOT / "tests/fixtures/core_eligible_synthetic.json").read_text(encoding="utf-8"))
    assert fixture["fixture_notice"].startswith("SYNTHETIC INPUT ONLY")
    complete = fixture["student_state"]
    one_course = deepcopy(complete)
    one_course["course_attempts"] = [a for a in complete["course_attempts"] if a["course_id"] == "CDA0143"]
    one_course["completion_coverage"] = "PARTIAL"
    missing_thesis = deepcopy(complete)
    missing_thesis["course_attempts"] = [a for a in complete["course_attempts"] if a["course_id"] != "CDA0034"]
    cases = [
        ("과목 조회", one_course, "고 자 구는 전필이에요?", "COURSE_LOOKUP", (3, 4)),
        ("전공 학점", one_course, "나 지금 전공 몇 점 채운 거임?", "CREDIT_SUMMARY", (22, 23)),
        ("필수 누락", missing_thesis, "필수 빠진 거 뭐야?", "REQUIREMENT_GAPS", (157, 158)),
        ("추가 이수", missing_thesis, "졸업논문 하나 더 들으면 어떻게 변해?", "WHAT_IF", (160, 161)),
        ("졸업 가능", complete, "졸업될까? 전필 빠진 것도 같이 알려줘", "GRADUATION_STATUS", (160, 161)),
    ]
    keys = ("decision", "scenario_decision", "requirement_results", "credited_amount", "missing_amount",
            "missing_courses", "needs_information", "evidence", "execution_trace", "answer_text")
    for label, state, utterance, expected_intent, expected_graph in cases:
        plain = post(port, state, utterance, False)
        model = post(port, state, utterance, True)
        for payload in (plain, model):
            verify_payload(payload)
            assert payload["interpretation"]["structured_query"]["intent"] == expected_intent, label
            assert graph_counts(payload) == expected_graph, (label, graph_counts(payload))
        assert all(plain[key] == model[key] for key in keys), label
        assert model["llm_expression"]["status"] == "VERIFIED_STYLE", label
        print(f"PASS {label}: {expected_intent}, graph {expected_graph[0]} edges/{expected_graph[1]} nodes, "
              f"{len(model['requirement_results'])} rules, {len(model['execution_trace']['events'])} events, LLM invariant")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 18473)
