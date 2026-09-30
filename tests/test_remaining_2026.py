"""Regression and Reviewer checks for deterministic remaining-course projections."""
from __future__ import annotations

import json
import sys
import unittest
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]
from curriculum_assistant.engine import execute  # noqa: E402
from curriculum_assistant.graph import Graph  # noqa: E402
from curriculum_assistant.nlp import interpret  # noqa: E402
from curriculum_assistant.verifier import verify_payload  # noqa: E402
from generate_remaining_fixtures import DEST  # noqa: E402
from generate_mock_2026_transcripts import catalog_v1  # noqa: E402


class Remaining2026Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = catalog_v1()
        cls.graph = Graph(Path(":memory:"), cls.catalog)

    @classmethod
    def tearDownClass(cls):
        cls.graph.close()

    def fixture(self, name: str) -> dict:
        return json.loads((DEST / f"{name}.json").read_text(encoding="utf-8"))

    def run_plan(self, name: str) -> dict:
        result = execute(self.graph, self.fixture(name)["student_state"], {"intent": "REMAINING_PLAN", "focus": "ALL"})
        verify_payload(result)
        return result

    def test_required_course_is_not_recommended_after_completion(self):
        incomplete = self.run_plan("required_missing")["decision"]
        required = [c for c in incomplete["candidate_courses"] if c["candidate_status"] == "REQUIRED"]
        self.assertEqual([c["course_id"] for c in required], incomplete["missing_courses"])
        complete = self.run_plan("year4_late")["decision"]
        self.assertFalse(any(c["candidate_status"] == "REQUIRED" for c in complete["candidate_courses"]))
        self.assertTrue(all(c["candidate_status"] == "ALREADY_COMPLETED" for c in complete["candidate_courses"]
                            if c["course_id"] in {r["course_id"] for r in complete["recognitions"]}))

    def test_candidate_satisfies_relation_is_from_graph_and_pdf(self):
        result = self.run_plan("year1_early")
        active = next(c for c in result["decision"]["candidate_courses"] if c["candidate_status"] == "REQUIRED")
        edges = {r["id"]: r for r in result["evidence"]["relationship_details"]}
        self.assertTrue(active["relationship_ids"])
        self.assertTrue(all(edges[eid]["kind"] == "SATISFIES" for eid in active["relationship_ids"]))
        self.assertEqual(active["provenance"]["source_document_id"], "CURRICULUM-2026")
        self.assertGreater(active["provenance"]["source"]["pdf_page"], 0)

    def test_all_satisfied_has_no_option_recommendations(self):
        decision = self.run_plan("year4_late")["decision"]
        self.assertEqual(decision["decision_status"], "SATISFIED")
        self.assertFalse(any(c["candidate_status"] in {"REQUIRED", "ELIGIBLE_OPTION"}
                             for c in decision["candidate_courses"]))

    def test_grade_label_does_not_change_result(self):
        original = self.fixture("year2_late")["student_state"]
        a, b = deepcopy(original), deepcopy(original)
        a["grade_label"] = "1학년"
        b["grade_label"] = "4학년"
        left = execute(self.graph, a, {"intent": "REMAINING_PLAN"})["decision"]
        right = execute(self.graph, b, {"intent": "REMAINING_PLAN"})["decision"]
        for key in ("decision_status", "requirement_results", "credited_amount", "missing_amount",
                    "missing_courses", "remaining_requirements", "candidate_courses"):
            self.assertEqual(left[key], right[key])

    def test_same_grade_different_attempts_changes_progress(self):
        early = self.run_plan("year1_early")["decision"]
        late = self.run_plan("year1_late")["decision"]
        self.assertNotEqual(early["credited_amount"], late["credited_amount"])
        self.assertNotEqual(early["remaining_requirements"], late["remaining_requirements"])

    def test_unknown_course_does_not_become_candidate(self):
        student = self.fixture("year1_early")["student_state"]
        student["course_attempts"].append({"attempt_id": "UNKNOWN-REVIEWER", "course_id": "ZZZ9999",
            "completion_status": "COMPLETED", "verification_status": "VERIFIED", "evidence_id": "TEST-UNKNOWN",
            "earned_credits": None})
        result = execute(self.graph, student, {"intent": "REMAINING_PLAN"})
        self.assertNotIn("ZZZ9999", [c["course_id"] for c in result["decision"]["candidate_courses"]])
        self.assertIn("NEEDS_INFORMATION", {r["status"] for r in result["requirement_results"]})
        self.assertEqual(result["remaining_presentation"]["required_courses_status"], "NEEDS_INFORMATION")
        self.assertIn("미이수 과목을 확정할 수 없음", result["answer_text"])

    def test_student_answer_groups_only_the_requested_catalog_area(self):
        student = self.fixture("year1_early")["student_state"]
        result = execute(self.graph, student, {"intent": "REMAINING_PLAN", "focus": "GENERAL"})
        self.assertEqual([g["area"] for g in result["remaining_presentation"]["candidate_groups"]], ["GENERAL"])
        self.assertNotIn("전공: 현재 조회 범위에 선택 후보 없음", result["answer_text"])
        self.assertIn("교양: 후보", result["answer_text"])

    def test_large_option_catalog_is_summarized_without_a_rank(self):
        result = self.run_plan("year1_early")
        options = [c for c in result["decision"]["candidate_courses"]
                   if c["candidate_status"] == "ELIGIBLE_OPTION"]
        self.assertGreater(len(options), 200)
        self.assertNotIn(options[-1]["course_id"], result["answer_text"])
        self.assertIn("우선순위 아님", result["answer_text"])
        self.assertIn("한 과목이 여러 요건에 포함될 수 있습니다", result["answer_text"])

    def test_what_if_does_not_mutate_student_state(self):
        fixture = self.fixture("required_missing")
        student = fixture["student_state"]
        original = deepcopy(student)
        code = fixture["expected"]["simulation_course_id"]
        result = execute(self.graph, student, {"intent": "WHAT_IF", "course_id": code,
                                                    "assumed_completion": "SUCCESS"})
        self.assertEqual(student, original)
        self.assertEqual(result["scenario_delta"]["status"], "CALCULATED")
        self.assertIn("R-CE-2026-REQUIRED-COURSES", [r["rule_id"] for r in result["scenario_delta"]["changed_requirements"]])

    def test_what_if_shows_required_course_progress_without_status_flip(self):
        fixture = self.fixture("year1_early")
        code = fixture["expected"]["simulation_course_id"]
        result = execute(self.graph, fixture["student_state"],
                         {"intent": "WHAT_IF", "course_id": code, "assumed_completion": "SUCCESS"})
        delta = result["scenario_delta"]
        self.assertIn(code, delta["missing_required_before"])
        self.assertNotIn(code, delta["missing_required_after"])
        self.assertEqual(delta["completed_required_course_ids"], [code])
        self.assertEqual(result["decision"]["decision_status"], "UNSATISFIED")
        self.assertEqual(result["scenario_decision"]["decision_status"], "UNSATISFIED")
        self.assertIn(code, result["answer_text"])

    def test_korean_plan_phrasings_are_structured_without_free_query(self):
        for question in ("앞으로 뭐 더 들어야 해?", "다음엔 무슨 과목 들어야 돼?", "전필 뭐 남았어?",
                         "졸업하려면 앞으로 몇 학점 더 필요해?", "교양 뭐 더 들어야 해?",
                         "전공에서 남은 거 알려줘", "이 상태에서 다음에 뭘 채우면 돼?",
                         "내가 지금 얼마나 채운 상태야?"):
            with self.subTest(question=question):
                query = interpret(question, self.catalog)["structured_query"]
                self.assertIsNotNone(query)
                self.assertEqual(query["intent"], "REMAINING_PLAN")
                self.assertNotIn("cypher", query)

    def test_short_gap_question_keeps_existing_audit_intent(self):
        query = interpret("컴공 전필 뭐 남음?", self.catalog)["structured_query"]
        self.assertEqual(query["intent"], "REQUIREMENT_GAPS")


if __name__ == "__main__":
    unittest.main()
