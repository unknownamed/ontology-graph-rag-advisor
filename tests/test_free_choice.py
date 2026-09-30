"""PDF page 13 free-choice residual credit recognition and reviewer cases."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts"), str(ROOT / "tests")]
from build_catalog import build  # noqa: E402
from curriculum_assistant.engine import execute  # noqa: E402
from curriculum_assistant.graph import Graph  # noqa: E402
from test_general_education import complete_student  # noqa: E402


def with_free_choice(catalog):
    student = complete_student(catalog)
    electives = [a for a in student["course_attempts"] if a["course_id"] in
                 {c["course_id"] for c in catalog["courses"] if c["classification"] == "MAJOR_ELECTIVE"}]
    removed = {a["attempt_id"] for a in electives[:6]}
    student["course_attempts"] = [a for a in student["course_attempts"] if a["attempt_id"] not in removed]
    student["free_choice_records"] = [
        {"record_id": f"FREE-{i}", "course_id": f"XYZ{i:04d}", "earned_credits": 3,
         "source_category": "OTHER_DEPARTMENT_MAJOR", "completion_status": "COMPLETED",
         "verification_status": "VERIFIED", "recognition_status": "VERIFIED",
         "evidence_kind": "OFFICIAL_TRANSCRIPT_RECOGNITION", "evidence_id": f"OFFICIAL-FREE-{i}"}
        for i in range(6)]
    return student


class FreeChoiceCases(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = build()
        cls.graph = Graph(Path(":memory:"), cls.catalog)

    @classmethod
    def tearDownClass(cls):
        cls.graph.close()

    def decide(self, student):
        return execute(self.graph, student, {"intent": "GRADUATION_STATUS"})

    def test_official_other_department_credits_fill_residual_18(self):
        result = self.decide(with_free_choice(self.catalog))
        amount = result["decision"]["credited_amount"]
        self.assertEqual(78, amount["by_area"]["MAJOR_TOTAL"])
        self.assertEqual(34, amount["by_area"]["GENERAL_TOTAL"])
        self.assertEqual(18, amount["by_area"]["FREE_CHOICE"])
        self.assertEqual(130, amount["total"])
        self.assertEqual("ELIGIBLE_PDF", result["decision"]["graduation_outcome"])
        self.assertIn("CURRICULUM-APPLICATION-2026", result["evidence"]["source_locators"])
        self.assertTrue(any(e["operation"] == "FETCH_POLICY_FACTS" for e in result["execution_trace"]["events"] if e["event_type"] == "GRAPH_QUERY"))

    def test_review_counterexample_unverified_free_credit_needs_information(self):
        student = with_free_choice(self.catalog)
        student["free_choice_records"][0]["recognition_status"] = "UNVERIFIED"
        result = self.decide(student)
        self.assertEqual("UNKNOWN", result["decision"]["graduation_outcome"])
        self.assertIsNone(result["decision"]["credited_amount"]["total"])

    def test_review_counterexample_catalog_course_cannot_be_reclassified_free(self):
        student = with_free_choice(self.catalog)
        student["free_choice_records"][0]["course_id"] = "CDA0143"
        result = self.decide(student)
        self.assertEqual("UNKNOWN", result["decision"]["graduation_outcome"])
        self.assertTrue(any(x["reason"] == "FREE_CHOICE_OVERLAP_NEEDS_REVIEW" for x in result["decision"]["excluded"]))

    def test_duplicate_free_course_is_not_counted_twice(self):
        student = with_free_choice(self.catalog)
        student["free_choice_records"][1]["course_id"] = student["free_choice_records"][0]["course_id"]
        result = self.decide(student)
        self.assertEqual("UNKNOWN", result["decision"]["graduation_outcome"])
        self.assertEqual(12, result["decision"]["credited_amount"]["by_area"]["FREE_CHOICE"])

    def test_free_choice_cannot_use_user_confirmed_ocr_as_official_recognition(self):
        student = with_free_choice(self.catalog)
        student["free_choice_records"][0]["evidence_kind"] = "USER_CONFIRMED_UPLOAD"
        with self.assertRaisesRegex(ValueError, "official transcript"):
            self.decide(student)

    def test_free_choice_and_general_cap_are_counted_once_each(self):
        student = with_free_choice(self.catalog)
        for code in ("GEA8660", "GEA8659", "GEA7301", "GEA7300"):
            student["course_attempts"].append({"attempt_id": f"EXTRA-{code}", "course_id": code,
                                                "completion_status": "COMPLETED", "verification_status": "VERIFIED",
                                                "evidence_id": f"EXTRA-E-{code}", "earned_credits": 3})
        result = self.decide(student)
        amount = result["decision"]["credited_amount"]
        self.assertEqual(46, amount["by_area"]["GENERAL_TOTAL"])
        self.assertEqual(18, amount["by_area"]["FREE_CHOICE"])
        self.assertEqual(138, amount["total"])
        self.assertTrue(any(e["event_type"] == "CREDIT_CAP" and e["result"]["excluded_credits"] == 4
                            for e in result["execution_trace"]["events"]))


if __name__ == "__main__":
    unittest.main()
