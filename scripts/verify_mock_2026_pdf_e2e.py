"""Exercise synthetic PDF upload -> review -> query through the real HTTP routes."""
from __future__ import annotations

import base64
import hashlib
import json
import sys
import threading
import urllib.request
from collections import Counter
from copy import deepcopy
from http.server import HTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]

from curriculum_assistant.authority import RuleSetStore  # noqa: E402
from curriculum_assistant.graph import Graph, canonical  # noqa: E402
from curriculum_assistant.server import Handler  # noqa: E402
from curriculum_assistant.verifier import verify_payload  # noqa: E402
from generate_mock_2026_transcripts import DEST, NOTICE, PROFILE_IDS, make_rows  # noqa: E402

RESULTS = ROOT / "evaluation" / "results" / "mock_2026_pdf_e2e_results.json"
REPORT = ROOT / "evaluation" / "results" / "mock_2026_pdf_e2e_report.md"


def post(port: int, route: str, body: dict) -> dict:
    request = urllib.request.Request(f"http://127.0.0.1:{port}{route}",
                                     data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
                                     headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=90) as response:
        return json.load(response)


def review_from_candidates(extracted: dict) -> dict:
    fields = extracted["student_fields"]

    def unique(field: str) -> str:
        observations = fields[field]["observations"]
        values = {item["raw"] for item in observations}
        if len(values) != 1:
            raise AssertionError(f"Synthetic PDF field {field} is not uniquely observed")
        return values.pop()

    student_id = unique("student_id")
    assert unique("department") == "컴퓨터공학과"
    assert unique("admission_year") == "2026"
    review = {"student_fields": {"confirmed": True, "student_id": student_id,
                                 "department": "컴퓨터공학과", "admission_year": "2026",
                                 "credit_policy_year": "2026", "catalog_year": "2026",
                                 "program_type": "SINGLE"}, "records": []}
    for candidate in extracted["candidates"]:
        raw = candidate["raw_values"]
        exact = (candidate["resolution_status"] == "RESOLVED_TO_CATALOG"
                 and raw["course_code"] == candidate["catalog_course_id"]
                 and raw["course_name"] == candidate["catalog_name"]
                 and raw["earned_credits"] == candidate["catalog_credits"]
                 and raw["grade"] in {"A+", "S"})
        review["records"].append({"candidate_id": candidate["candidate_id"],
                                  "course_code": raw["course_code"], "course_name": raw["course_name"],
                                  "earned_credits": raw["earned_credits"], "semester": raw["semester"],
                                  "classification": raw["classification"],
                                  "completion_status": "COMPLETED" if raw.get("grade") in {"A+", "S"} else "UNKNOWN",
                                  "confirmed": exact})
    return review


def verify_extracted_rows(extracted: dict, expected: dict, catalog: dict) -> None:
    """Check the uploaded PDF cells against the independently generated fixture rows."""
    missing_code = expected["unresolved_source_course_id_for_generator_audit"]
    source_rows = make_rows(expected["course_ids_for_generator_audit"], catalog, missing_code)
    source = Counter((row["course_code"], row["course_name"], row["credits"],
                      f"{row['year']}-{row['term']}", row["classification"], row["grade"])
                     for row in source_rows)
    extracted_rows = Counter((row["raw_values"]["course_code"], row["raw_values"]["course_name"],
                              row["raw_values"]["earned_credits"], row["raw_values"]["semester"],
                              row["raw_values"]["classification"], row["raw_values"].get("grade"))
                             for row in extracted["candidates"])
    assert source == extracted_rows, (expected["fixture_id"], source - extracted_rows,
                                      extracted_rows - source)


def attach_explicit_test_attestations(state: dict, fixture_id: str) -> dict:
    """Add mock evidence unavailable from a course table; do not alter row verification."""
    state = deepcopy(state)
    state["student_state_id"] += f"-{fixture_id}"
    state["student_category"] = "DOMESTIC_REGULAR"
    state["student_category_evidence_id"] = f"TEST-FIXTURE:{fixture_id}:CATEGORY"
    state["applicability_status"] = "VERIFIED"
    state["applicability_evidence_id"] = f"TEST-FIXTURE:{fixture_id}:APPLICABILITY"
    state["completion_coverage"] = "COMPLETE"
    state["completion_coverage_evidence_id"] = f"TEST-FIXTURE:{fixture_id}:COVERAGE"
    state["equivalence_review_status"] = "VERIFIED"
    state["equivalence_review_evidence_id"] = f"TEST-FIXTURE:{fixture_id}:EQUIVALENCE"
    state["academic_events"] = []
    state["official_outcomes"] = {
        key: {"value": True, "verification_status": "VERIFIED",
              "evidence_id": f"TEST-FIXTURE:{fixture_id}:{key}"}
        for key in ("thesis_passed", "thesis_final_semester_enrollment",
                    "graduation_certification_passed")}
    state["synthetic_assumption_notice"] = NOTICE
    return state


def compare(expected: dict, extracted: dict, normalized: dict, payload: dict, state: dict) -> dict:
    verify_payload(payload)
    decision = payload["decision"]
    assert extracted["candidate_count"] == expected["course_count"]
    assert not extracted["document_coverage"]["unreadable_pages"]
    assert extracted["document_coverage"]["page_count"] >= 1
    assert len(normalized["records"]) == expected["course_count"]
    assert normalized["usable_record_count"] == expected["expected_resolved_records"]
    assert len(state["course_attempts"]) == expected["course_count"]
    assert sum(item["earned_credits"] or 0 for item in state["course_attempts"]) == expected["expected_printed_total_credits"]
    assert decision["ruleset_id"] == expected["ruleset_id"]
    assert decision["ruleset_version"] == expected["ruleset_version"]
    assert decision["authoritative_document_set_id"] == expected["authoritative_document_set_id"]
    assert set(decision["applicable_rule_ids"]) == set(expected["source_rule_ids"]) - {"R-CE-2026-DOUBLE-MAJOR-MINIMUM"}
    actual_results = {item["rule_id"]: item for item in decision["requirement_results"]}
    assert set(actual_results) == set(expected["expected_requirement_results"])
    for rule_id, expected_status in expected["expected_requirement_results"].items():
        assert actual_results[rule_id]["status"] == expected_status, (expected["fixture_id"], rule_id,
                                                                      expected_status, actual_results[rule_id]["status"])
    assert decision["graduation_outcome"] == expected["expected_final_decision"]
    assert decision["credited_amount"]["total"] == expected["expected_total_credits"]
    assert decision["credited_amount"]["by_area"]["MAJOR_TOTAL"] == expected["expected_major_confirmed_minimum"]
    if expected["expected_major_credits"] is None:
        assert decision["credited_amount"]["total"] is None
    else:
        assert decision["credited_amount"]["by_area"]["MAJOR_TOTAL"] == expected["expected_major_credits"]
    assert decision["credited_amount"]["confirmed_minimum"] == expected["expected_confirmed_minimum"]
    for rule_id, amount in expected["expected_missing_amount"].items():
        assert decision["missing_amount"][rule_id] == amount
    for rule_id, course_ids in expected["expected_missing_courses"].items():
        assert actual_results[rule_id]["missing_course_ids"] == course_ids
    if expected["expected_needs_information"]:
        assert any(any(item.startswith(prefix) for prefix in expected["expected_needs_information"])
                   for item in decision["needs_information"])
    else:
        assert decision["decision_status"] != "NEEDS_INFORMATION"
    trace = payload["execution_trace"]
    events = trace["events"]
    assert any(item["event_type"] == "QUERY_PLAN" for item in events)
    assert any(item["event_type"] == "GRAPH_QUERY" and item["operation"] == "FETCH_REQUIREMENTS" for item in events)
    assert sum(item["event_type"] == "RULE_EVALUATION" for item in events) == len(expected["source_rule_ids"])
    assert all(item["source_document_id"] == "CURRICULUM-2026"
               for item in payload["evidence"]["source_locators"].values())
    assert all(row["source_refs"] and set(row["source_refs"]) <= set(payload["evidence"]["source_locators"])
               for row in decision["requirement_results"])
    assert payload["answer_text"]
    return {"fixture_id": expected["fixture_id"], "course_count": expected["course_count"],
            "printed_credits": expected["expected_printed_total_credits"],
            "extracted_pages": extracted["document_coverage"]["page_count"],
            "candidate_count": extracted["candidate_count"],
            "resolved_count": normalized["usable_record_count"],
            "expected_outcome": expected["expected_final_decision"],
            "actual_outcome": decision["graduation_outcome"],
            "confirmed_credits": decision["credited_amount"]["total"],
            "major_credits": decision["credited_amount"]["by_area"]["MAJOR_TOTAL"],
            "missing_amount": {k: v for k, v in decision["missing_amount"].items() if v},
            "missing_courses": {row["rule_id"]: row["missing_course_ids"]
                                for row in decision["requirement_results"] if row["missing_course_ids"]},
            "requirement_status_counts": dict(Counter(item["status"] for item in decision["requirement_results"])),
            "decision_id": decision["decision_id"], "execution_id": trace["execution_id"],
            "trace_events": len(events), "graph_relationships": len(payload["evidence"]["relationships"]),
            "pdf_source_locator_count": len(payload["evidence"]["source_locators"]),
            "pass": True}


def main() -> None:
    catalog = RuleSetStore(ROOT / "data/processed/ruleset_versions").load_active()

    class BoundHandler(Handler):
        pass

    server = HTTPServer(("127.0.0.1", 0), BoundHandler)
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
        raise RuntimeError("Local test server did not initialize")
    port = server.server_address[1]
    details = []
    try:
        for fixture_id in PROFILE_IDS:
            expected = json.loads((DEST / f"{fixture_id}.expected.json").read_text(encoding="utf-8"))
            # The fixed synthetic v1 expectation tests invariant requirement values;
            # only the pinned execution version follows the currently active RuleSet.
            expected["ruleset_version"] = catalog["curriculum_ruleset"]["ruleset_version"]
            file_bytes = (DEST / f"{fixture_id}.pdf").read_bytes()
            encoded = base64.b64encode(file_bytes).decode("ascii")
            extracted = post(port, "/api/extract", {"filename": f"{fixture_id}.pdf", "content_base64": encoded})
            assert extracted["source_id"] == hashlib.sha256(file_bytes).hexdigest()
            verify_extracted_rows(extracted, expected, catalog)
            review = review_from_candidates(extracted)
            normalized = post(port, "/api/normalize-upload", {"filename": f"{fixture_id}.pdf",
                                                               "content_base64": encoded,
                                                               "source_id": extracted["source_id"], "review": review})
            question = "이 학생 졸업할 수 있어?"
            upload_only = post(port, "/api/query", {"student_state": normalized["student_state"],
                                                     "utterance": question, "use_local_llm": False})
            verify_payload(upload_only)
            assert upload_only["decision"]["graduation_outcome"] == "UNKNOWN"
            state = attach_explicit_test_attestations(normalized["student_state"], fixture_id)
            state_before = canonical(state)
            off = post(port, "/api/query", {"student_state": state, "utterance": question,
                                             "use_local_llm": False})
            assert off["interpretation"]["structured_query"]["intent"] == "GRADUATION_STATUS"
            detail = compare(expected, extracted, normalized, off, state)
            detail["upload_only_outcome"] = upload_only["decision"]["graduation_outcome"]
            on = post(port, "/api/query", {"student_state": state, "utterance": question,
                                            "use_local_llm": True})
            verify_payload(on)
            for key in ("decision", "requirement_results", "credited_amount", "missing_amount",
                        "missing_courses", "needs_information", "evidence", "execution_trace"):
                assert canonical(off[key]) == canonical(on[key]), (fixture_id, key)
            detail["llm_consistency"] = True
            detail["llm_interpretation_status"] = on.get("interpretation", {}).get("llm", {}).get("status")
            detail["llm_expression_status"] = on.get("llm_expression", {}).get("status")
            assert canonical(state) == state_before
            if fixture_id == "mock_2026_boundary":
                preview = ROOT / "logs" / "synthetic-ui-preview"
                preview.mkdir(parents=True, exist_ok=True)
                (preview / "boundary_student_state.json").write_text(
                    json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                added = expected["simulation_added_course_id"]
                what_if = post(port, "/api/query", {"student_state": state,
                                                    "utterance": f"{added} 과목을 더 들으면 무엇이 달라져?",
                                                    "use_local_llm": False})
                verify_payload(what_if)
                assert what_if["interpretation"]["structured_query"]["intent"] == "WHAT_IF"
                delta = what_if["scenario_delta"]
                assert delta["status"] == "CALCULATED"
                assert delta["total_credit_change"] == 0
                assert {r["rule_id"] for r in delta["changed_requirements"]} == {"R-CE-2026-REQUIRED-COURSES"}
                assert delta["changed_requirements"][0]["before"] == "UNSATISFIED"
                assert delta["changed_requirements"][0]["after"] == "SATISFIED"
                assert what_if["scenario_decision"]["decision_status"] == "SATISFIED"
                assert any(e["event_type"] == "SCENARIO_DELTA" for e in what_if["execution_trace"]["events"])
                assert any(e["event_type"] == "SCENARIO_COMPARISON" for e in what_if["execution_trace"]["events"])
                assert canonical(state) == state_before
                scenario_state = deepcopy(state)
                scenario_state["student_state_id"] += "-SCENARIO-COPY"
                scenario_state["course_attempts"].append({"attempt_id": f"TEST-FIXTURE-SCENARIO-{added}",
                                                          "course_id": added, "completion_status": "COMPLETED",
                                                          "verification_status": "VERIFIED",
                                                          "evidence_id": f"TEST-FIXTURE:SCENARIO:{added}",
                                                          "earned_credits": next(c["catalog_credits"] for c in catalog["courses"]
                                                                                 if c["course_id"] == added)})
                scenario_graduation = post(port, "/api/query", {"student_state": scenario_state,
                                                                 "utterance": question, "use_local_llm": False})
                verify_payload(scenario_graduation)
                assert scenario_graduation["decision"]["graduation_outcome"] == "ELIGIBLE_PDF"
                assert scenario_graduation["credited_amount"]["total"] == off["credited_amount"]["total"]
                assert {r["rule_id"]: r["status"] for r in scenario_graduation["requirement_results"]} == {
                    r["rule_id"]: r["status"] for r in what_if["scenario_decision"]["requirement_results"]}
                assert canonical(state) == state_before
                (preview / "boundary_what_if_payload.json").write_text(
                    json.dumps(what_if, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                detail["simulation"] = {"added_course_id": added, "delta": delta,
                                        "actual_status": what_if["decision"]["decision_status"],
                                        "scenario_status": what_if["scenario_decision"]["decision_status"],
                                        "actual_graduation_outcome": off["decision"]["graduation_outcome"],
                                        "scenario_graduation_outcome": scenario_graduation["decision"]["graduation_outcome"],
                                        "source_course_classification": next(c["classification"] for c in catalog["courses"]
                                                                             if c["course_id"] == added)}
            details.append(detail)
            print(json.dumps({"fixture_id": fixture_id, "extracted": detail["candidate_count"],
                              "resolved": detail["resolved_count"], "outcome": detail["actual_outcome"],
                              "llm_consistency": detail["llm_consistency"]}, ensure_ascii=True))
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
    RESULTS.parent.mkdir(parents=True, exist_ok=True)
    RESULTS.write_text(json.dumps({"notice": NOTICE, "results": details}, ensure_ascii=False, indent=2) + "\n",
                       encoding="utf-8")
    report = ["# 2026 Core 합성 PDF 업로드 E2E 검증", "",
              "모든 자료는 테스트용 모의 성적표이며 실제 학생 자료가 아니다.", "",
              "| fixture | PDF 후보/연결 | 원문학점 | PDF 단독 | 기대 | 실제 | LLM 일치 |",
              "| --- | ---: | ---: | --- | --- | --- | --- |"]
    report.extend(f"| {d['fixture_id']} | {d['candidate_count']}/{d['resolved_count']} | "
                  f"{d['printed_credits']} | {d['upload_only_outcome']} | {d['expected_outcome']} | "
                  f"{d['actual_outcome']} | {'PASS' if d['llm_consistency'] else 'FAIL'} |"
                  for d in details)
    report += ["", "합성 학생 범위·논문·인증·동일과목 검토는 PDF에서 자동 추론하지 않고 "
               "테스트 fixture의 명시적 확인 입력으로 제공했다. 그러므로 PDF 단독은 4건 모두 UNKNOWN이다.", ""]
    for detail in details:
        report += [f"## {detail['fixture_id']}", "",
                   f"- 읽힌 페이지 {detail['extracted_pages']}쪽, 후보 {detail['candidate_count']}건, "
                   f"확정 연결 {detail['resolved_count']}건, "
                   f"요건 상태 {json.dumps(detail['requirement_status_counts'], ensure_ascii=False)}.",
                   f"- 총 인정학점 {detail['confirmed_credits']}, 전공 인정학점 {detail['major_credits']}; "
                   f"부족 학점 {json.dumps(detail['missing_amount'], ensure_ascii=False)}, "
                   f"미이수 필수 {json.dumps(detail['missing_courses'], ensure_ascii=False)}.",
                   f"- 실행 {detail['execution_id']}: 실제 이벤트 {detail['trace_events']}건, "
                   f"관계 {detail['graph_relationships']}개, 공식 PDF 근거 위치 {detail['pdf_source_locator_count']}개.", ""]
        if "simulation" in detail:
            simulation = detail["simulation"]
            report += [f"- 가정 과목 {simulation['added_course_id']}: 졸업 상태 "
                       f"{simulation['actual_graduation_outcome']} → {simulation['scenario_graduation_outcome']}; "
                       f"학점 변화 {simulation['delta']['total_credit_change']}, "
                       f"변경 요건 {json.dumps(simulation['delta']['changed_requirements'], ensure_ascii=False)}.", ""]
    REPORT.write_text("\n".join(report), encoding="utf-8")


if __name__ == "__main__":
    main()
