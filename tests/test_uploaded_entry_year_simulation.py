"""Counterfactual upload-state checks with synthetic, nonstudent records."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]

from build_catalog import build  # noqa: E402
from curriculum_assistant.engine import execute  # noqa: E402
from curriculum_assistant.graph import Graph, canonical  # noqa: E402
from simulate_uploaded_transcript_2026 import make_simulation, row_manifest  # noqa: E402


class UploadedEntryYearSimulationCases(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = build()
        cls.courses = {row["course_id"]: row for row in cls.catalog["courses"]}

    def _input(self):
        cases = [("CDA0143", "2022-1", 3, "A+", "RESOLVED_TO_CATALOG", "2022 원문 전공선택"),
                 (None, "2025-2", 3, "B0", "UNRESOLVED", "원문 미분류"),
                 ("CDA0088", "2026-1", 0, "U", "DUPLICATE_CANDIDATE", "전공필수"),
                 ("CDA0088", "2026-2", 0, "S", "DUPLICATE_CANDIDATE", "전공필수"),
                 ("CDA0088", "2026-2", 0, "S", "DUPLICATE_CANDIDATE", "전공필수")]
        attempts, records = [], []
        for index, (code, semester, credits, grade, status, raw_class) in enumerate(cases, 1):
            known = self.courses.get(code)
            aid = f"TEST-FIXTURE-{index}"
            attempts.append({"attempt_id": aid, "course_id": code,
                             "source_course_code": code or "ZZZ9999",
                             "source_course_name": known["name"] if known else "미등록 시험 과목",
                             "earned_credits": credits, "semester": semester, "source_grade": grade,
                             "completion_status": "FAILED" if grade == "U" else "COMPLETED",
                             "verification_status": "UNVERIFIED", "resolution_status": status,
                             "evidence_id": f"TEST-FIXTURE-EVIDENCE-{index}",
                             "evidence_type": "USER_UPLOADED_CONTEXT"})
            records.append({"candidate_id": aid, "raw_values": {"classification": raw_class},
                            "official_course": {"course_id": code, "classification": known["classification"],
                                                "credits": known["catalog_credits"]} if known else None})
        return ({"student_state_id": "TEST-FIXTURE-ACTUAL-2022", "student_id": "TEST-FIXTURE",
                 "admission_year": 2022, "department_id": "DEPT-COMPUTER-ENGINEERING",
                 "credit_policy_year": None, "catalog_year": None,
                 "applicability_status": "UNVERIFIED", "program_type": None,
                 "completion_coverage": "PARTIAL", "course_attempts": attempts}, {"records": records})

    def test_clone_preserves_upload_rows_and_separates_source_classification(self):
        actual, normalized = self._input()
        before = canonical(actual)
        graph = Graph(Path(":memory:"), self.catalog)
        try:
            simulation, audit = make_simulation(actual, normalized, graph, 2026)
        finally:
            graph.close()
        self.assertEqual(before, canonical(actual))
        self.assertEqual(2022, actual["admission_year"])
        self.assertEqual(2026, simulation["admission_year"])
        self.assertEqual(row_manifest(actual), row_manifest(simulation))
        self.assertEqual(["UNVERIFIED"] * 5, [a["verification_status"] for a in simulation["course_attempts"]])
        self.assertEqual(5, len(audit["records"]))
        self.assertEqual("2022 원문 전공선택", simulation["course_attempts"][0]["source_classification"])
        self.assertEqual("MAJOR_REQUIRED", simulation["course_attempts"][0]["catalog_classification_2026"])
        self.assertIsNone(simulation["course_attempts"][1]["catalog_classification_2026"])
        self.assertEqual(2, len(simulation["simulation_context"]["pre_admission_attempt_ids"]))
        self.assertTrue(all(not row["counted_as_credit"] for row in audit["records"]))

    def test_unverified_and_repeat_candidates_do_not_become_credits(self):
        actual, normalized = self._input()
        graph = Graph(Path(":memory:"), self.catalog)
        try:
            simulation, _ = make_simulation(actual, normalized, graph, 2026)
            decision = execute(graph, simulation, {"intent": "GRADUATION_STATUS"})["decision"]
        finally:
            graph.close()
        self.assertEqual("UNKNOWN", decision["graduation_outcome"])
        self.assertEqual("NEEDS_INFORMATION", decision["decision_status"])
        self.assertEqual([], decision["recognitions"])
        self.assertEqual(5, len(decision["excluded"]))
        self.assertIn("REPEAT_RESOLUTION_UNKNOWN", {row["reason"] for row in decision["excluded"]})
        self.assertIn("MISSING_COURSE_ID", {row["reason"] for row in decision["excluded"]})
        self.assertEqual(2022, actual["admission_year"])


if __name__ == "__main__":
    unittest.main()
