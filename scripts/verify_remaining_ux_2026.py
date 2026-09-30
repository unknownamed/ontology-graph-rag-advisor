"""Exercise student-facing remaining-plan wording through the real local API."""
from __future__ import annotations

import json
import threading
from copy import deepcopy
from http.server import HTTPServer
from pathlib import Path

from verify_remaining_2026_e2e import ROOT, canonical, core, make_fixtures, post
from curriculum_assistant.authority import RuleSetStore
from curriculum_assistant.graph import Graph
from curriculum_assistant.server import Handler

RESULTS = ROOT / "evaluation/results/remaining_2026_ux_results.json"
REPORT = ROOT / "evaluation/results/remaining_2026_ux_report.md"
QUESTIONS = (
    ("앞으로 뭐 더 들어야 해?", "REMAINING_PLAN", "ALL"),
    ("다음엔 무슨 과목 들어야 돼?", "REMAINING_PLAN", "ALL"),
    ("전필 뭐 남았어?", "REMAINING_PLAN", "MAJOR_REQUIRED"),
    ("졸업까지 몇 학점 더 필요해?", "REMAINING_PLAN", "ALL"),
    ("전공에서 남은 거 알려줘.", "REMAINING_PLAN", "MAJOR"),
    ("교양 뭐 더 들어야 해?", "REMAINING_PLAN", "GENERAL"),
    ("지금 가장 먼저 채워야 하는 필수요건이 뭐야?", "REMAINING_PLAN", "ALL"),
    ("이 과목 들으면 뭐가 달라져?", "WHAT_IF", None),
    ("내가 지금 어느 정도까지 채웠어?", "REMAINING_PLAN", "ALL"),
    ("4학년인데 아직 뭐가 남았어?", "REMAINING_PLAN", "ALL"),
)


def check_plan(payload: dict) -> None:
    decision = payload["decision"]
    view = payload["remaining_presentation"]
    summary = decision["remaining_requirements"]
    candidates = decision["candidate_courses"]
    assert view["satisfied_count"] == len(summary["satisfied_requirements"])
    assert view["unsatisfied_count"] == len(summary["unsatisfied_requirements"])
    assert view["needs_information_count"] == len(summary["needs_information"])
    assert [c["course_id"] for c in view["required_courses"]] == (summary["missing_required_courses"] or [])
    assert len(payload["answer_text"]) < 1200, len(payload["answer_text"])
    assert "졸업요건상 후보" in payload["answer_text"]
    assert "우선순위 아님" in payload["answer_text"]
    assert "다음 학기 개설·선수과목·시간표 충돌은 확인되지 않았습니다" in payload["answer_text"]
    assert "반드시 이수:" in payload["answer_text"] and "부족 학점:" in payload["answer_text"]
    options = [c for c in candidates if c["candidate_status"] == "ELIGIBLE_OPTION"]
    for group in view["candidate_groups"]:
        scoped = [c for c in options if c["course_classification"].startswith(group["area"] + "_")]
        assert group["candidate_count"] == len(scoped)
        for item in group["requirement_groups"]:
            ids = sorted(c["course_id"] for c in scoped if item["rule_id"] in c["satisfies_requirement_ids"])
            assert item["course_ids"] == ids and item["candidate_count"] == len(ids)
            assert item["rule_id"] in summary["unsatisfied_requirements"]
    if len(options) > 50:
        assert options[-1]["course_id"] not in payload["answer_text"], "Large catalog was dumped into chat"
    for course in candidates:
        if course["candidate_status"] in {"REQUIRED", "ELIGIBLE_OPTION"}:
            assert not course["already_completed"] and course["relationship_ids"]
            assert course["next_term_offering_status"] == "NOT_VERIFIED"


def main() -> None:
    catalog = RuleSetStore(ROOT / "data/processed/ruleset_versions").load_active()
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
        raise RuntimeError("Test API server did not initialize")
    rows = []
    reviewer = []
    try:
        fixtures = make_fixtures()
        baseline = {}
        for fixture in fixtures:
            fid = fixture["fixture_id"]
            state = deepcopy(fixture["student_state"])
            original = canonical(state)
            context = {"last_course_id": fixture["expected"]["simulation_course_id"]}
            responses = []
            for question, intent, focus in QUESTIONS:
                payload = post(port, state, question, context=context if intent == "WHAT_IF" else None)
                query = payload["interpretation"]["structured_query"]
                assert query["intent"] == intent, (fid, question, query)
                if focus is not None:
                    assert query["focus"] == focus, (fid, question, query)
                    check_plan(payload)
                    if focus == "ALL" and fid not in baseline:
                        baseline[fid] = payload
                else:
                    assert payload["scenario_decision"] and payload["scenario_delta"]["status"] == "CALCULATED"
                    assert query["course_id"] == context["last_course_id"]
                    assert payload["scenario_delta"]["actual_total"] == baseline[fid]["decision"]["credited_amount"]["total"]
                assert canonical(state) == original
                responses.append({"question": question, "intent": intent, "focus": focus,
                                  "answer": payload["answer_text"],
                                  "answer_length": len(payload["answer_text"]),
                                  "decision_id": payload["decision"]["decision_id"],
                                  "candidate_group_counts": {g["area"]: g["candidate_count"]
                                                             for g in payload.get("remaining_presentation", {}).get("candidate_groups", [])},
                                  "trace_events": len(payload["execution_trace"]["events"])})
            on = post(port, state, QUESTIONS[0][0], use_local_llm=True)
            off = baseline[fid]
            assert core(on) == core(off)
            assert on["remaining_presentation"] == off["remaining_presentation"]
            assert on["evidence"] == off["evidence"] and on["execution_trace"] == off["execution_trace"]
            assert canonical(state) == original
            rows.append({"fixture_id": fid, "course_count": len(state["course_attempts"]),
                         "required_count": len(off["remaining_presentation"]["required_courses"]),
                         "candidate_group_counts": {g["area"]: g["candidate_count"]
                                                    for g in off["remaining_presentation"]["candidate_groups"]},
                         "questions": responses, "llm_on_off_core_identical": True})
            print(f"{fid}: {len(responses)} API questions, basic answer {responses[0]['answer_length']} chars", flush=True)
        early = deepcopy(fixtures[0]["student_state"])
        early["grade_label"] = "4학년"
        changed_label = post(port, early, QUESTIONS[-1][0])
        assert changed_label["remaining_presentation"] == baseline["year1_early"]["remaining_presentation"]
        reviewer.append("grade_label_does_not_change_student_plan")
        assert baseline["year1_early"]["remaining_presentation"] != baseline["year1_late"]["remaining_presentation"]
        reviewer.append("same_grade_different_completion_changes_plan")
        assert not any(c["candidate_status"] in {"REQUIRED", "ELIGIBLE_OPTION"}
                       for c in baseline["year4_late"]["decision"]["candidate_courses"])
        reviewer.append("completed_student_has_no_recommended_courses")
        why = post(port, fixtures[-2]["student_state"], "왜 이 과목이 후보야?",
                   context={"last_course_id": fixtures[-2]["expected"]["simulation_course_id"]})
        assert why["decision"]["intent"] == "REMAINING_PLAN"
        target = next(c for c in why["decision"]["candidate_courses"]
                      if c["course_id"] == fixtures[-2]["expected"]["simulation_course_id"])
        edge_ids = {e["id"] for e in why["evidence"]["relationship_details"]}
        assert target["relationship_ids"] and set(target["relationship_ids"]) <= edge_ids
        assert target["provenance"]["source"]["pdf_page"] > 0
        reviewer.append("candidate_reason_has_actual_rule_edge_and_pdf")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
    version = catalog["curriculum_ruleset"]["ruleset_version"]
    RESULTS.write_text(json.dumps({"notice": "SYNTHETIC TEST DATA ONLY", "ruleset_version": version, "profile_count": len(rows),
                                   "question_count": sum(len(r["questions"]) for r in rows),
                                   "profiles": rows, "reviewer": reviewer}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = ["# 학생용 남은 요건 답변 UX 검증", "", f"활성 RuleSet v{version} 결정값을 바꾸지 않고 10개 합성 학생 상태에 10개 질문을 실제 `/api/query`로 실행했다.", "",
             "| 상태 | 과목 수 | 필수 미이수 | 전공 선택 후보 | 교양 선택 후보 | 기본 답변 길이 |",
             "| --- | ---: | ---: | ---: | ---: | ---: |"]
    for row in rows:
        lines.append(f"| {row['fixture_id']} | {row['course_count']} | {row['required_count']} | "
                     f"{row['candidate_group_counts']['MAJOR']} | {row['candidate_group_counts']['GENERAL']} | "
                     f"{row['questions'][0]['answer_length']} |")
    lines += ["", "기본 답변은 현재 상태, 반드시 이수, 부족 학점, 요건별 후보 수, 추가 확인을 다섯 줄로 구분한다. 전체 후보와 실제 SATISFIES 관계·Rule·PDF는 펼쳐보기에서 확인한다. 정렬은 우선순위가 아니다.",
              "", f"Reviewer 반례 {len(reviewer)}건: {', '.join(reviewer)}.", ""]
    for row in rows:
        lines += [f"## {row['fixture_id']}", "", row["questions"][0]["answer"], ""]
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    print(f"PASS: {len(rows)} profiles, {sum(len(r['questions']) for r in rows)} API questions, {len(reviewer)} reviewer cases", flush=True)


if __name__ == "__main__":
    main()
