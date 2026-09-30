"""Cross-rule 2026 single-major graduation cases using synthetic student inputs."""
from __future__ import annotations

import sys
import json
import unittest
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
from build_catalog import build  # noqa: E402
from curriculum_assistant.engine import execute  # noqa: E402
from curriculum_assistant.verifier import verify_payload  # noqa: E402
from curriculum_assistant.graph import Graph  # noqa: E402

GENERAL_34 = [
    "GEA8001", "GEA8812", "GEA8512", "GEA8704",  # 9 basic
    "GEA8658", "GEA8666", "GEA7562", "GEA7308",  # 12, one in each balanced area
    "GEA8623", "GEA8585", "GEA3070", "GEA7003", "GEA7006",  # 13 more
]


def complete_student(catalog):
    required = [c["course_id"] for c in catalog["courses"] if c["classification"] == "MAJOR_REQUIRED"]
    electives = [c["course_id"] for c in catalog["courses"] if c["classification"] == "MAJOR_ELECTIVE" and c["catalog_credits"] == 3][:25]
    codes = required + electives + GENERAL_34
    return {"student_state_id": "SYNTHETIC-COMPLETE", "student_id": "SYNTHETIC",
            "admission_year": 2026, "department_id": "DEPT-COMPUTER-ENGINEERING",
            "credit_policy_year": 2026, "catalog_year": 2026, "applicability_status": "VERIFIED",
            "program_type": "SINGLE", "student_category": "DOMESTIC_REGULAR", "academic_events": [],
            "student_category_evidence_id": "SYNTHETIC-STUDENT-CATEGORY",
            "applicability_evidence_id": "SYNTHETIC-APPLICABILITY",
            "completion_coverage_evidence_id": "SYNTHETIC-TRANSCRIPT-COVERAGE",
            "completion_coverage": "COMPLETE", "equivalence_review_status": "VERIFIED",
            "equivalence_review_evidence_id": "SYNTHETIC-EQUIV-REVIEW",
            "official_outcomes": {key: {"value": True, "verification_status": "VERIFIED", "evidence_id": f"SYNTHETIC-{key}"}
                                  for key in ("thesis_passed", "thesis_final_semester_enrollment", "graduation_certification_passed")},
            "course_attempts": [{"attempt_id": f"A-{i}", "course_id": code, "completion_status": "COMPLETED",
                                 "verification_status": "VERIFIED", "evidence_id": f"E-{i}", "earned_credits": None}
                                for i, code in enumerate(codes)]}


def by_rule(payload, suffix):
    return next(r for r in payload["decision"]["requirement_results"] if r["rule_id"].endswith(suffix))


class GeneralAndGraduationCases(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = build()
        cls.graph = Graph(Path(":memory:"), cls.catalog)

    @classmethod
    def tearDownClass(cls):
        cls.graph.close()

    def decide(self, state):
        return execute(self.graph, state, {"intent": "GRADUATION_STATUS"})

    def test_exact_130_with_all_verified_requirements_is_eligible(self):
        state = complete_student(self.catalog)
        out = self.decide(state)
        self.assertEqual(130, out["decision"]["credited_amount"]["total"])
        self.assertEqual(34, out["decision"]["credited_amount"]["by_area"]["GENERAL_TOTAL"])
        self.assertEqual(96, out["decision"]["credited_amount"]["by_area"]["MAJOR_TOTAL"])
        self.assertEqual(51, by_rule(out, "ADVANCED-CREDITS")["observed"])
        self.assertEqual("SATISFIED", by_rule(out, "BALANCED-AREAS")["status"])
        self.assertEqual("ELIGIBLE_PDF", out["decision"]["graduation_outcome"])
        self.assertTrue(out["decision"]["coverage_complete"])
        self.assertEqual("COMPLETE", next(e for e in out["execution_trace"]["events"]
                                          if e["event_type"] == "COVERAGE_CHECK")["result"])

    def test_reviewer_missing_scope_evidence_is_actionable_information(self):
        for key, expected in (("applicability_evidence_id", "VERIFIED_APPLICABILITY_EVIDENCE"),
                              ("completion_coverage_evidence_id", "COMPLETE_VERIFIED_TRANSCRIPT_EVIDENCE")):
            with self.subTest(key=key):
                state = complete_student(self.catalog)
                state.pop(key)
                out = self.decide(state)
                self.assertEqual("UNKNOWN", out["decision"]["graduation_outcome"])
                self.assertIn(expected, out["decision"]["needs_information"])
                self.assertIn("확인 필요", out["answer_text"])
                coverage = next(e for e in out["execution_trace"]["events"] if e["event_type"] == "COVERAGE_CHECK")
                self.assertIn(expected, coverage["missing"])
                forged = deepcopy(out)
                next(e for e in forged["execution_trace"]["events"] if e["event_type"] == "COVERAGE_CHECK")["result"] = "COMPLETE"
                with self.assertRaisesRegex(ValueError, "coverage result"):
                    verify_payload(forged)

    def test_reviewer_other_catalog_year_returns_information_not_server_error(self):
        state = complete_student(self.catalog)
        state["catalog_year"] = 2025
        out = self.decide(state)
        self.assertEqual("UNKNOWN", out["decision"]["graduation_outcome"])
        self.assertFalse(out["decision"]["coverage_complete"])
        self.assertIn("VERIFIED_2026_CREDIT_AND_CATALOG_APPLICABILITY", out["needs_information"])
        self.assertEqual("INCOMPLETE", next(e for e in out["execution_trace"]["events"]
                                            if e["event_type"] == "COVERAGE_CHECK")["result"])
        verify_payload(out)

    def test_reviewer_missing_rule_cannot_yield_positive_graduation(self):
        for removed in ("R-GE-2026-AI-FOUNDATION", "R-GE-2026-CREDIT-CAP",
                        "R-CE-2026-ADVANCED-CREDITS"):
            with self.subTest(removed=removed):
                partial_catalog = deepcopy(self.catalog)
                partial_catalog["requirements"] = [rule for rule in partial_catalog["requirements"]
                                                   if rule["rule_id"] != removed]
                graph = Graph(Path(":memory:"), partial_catalog)
                try:
                    out = execute(graph, complete_student(self.catalog), {"intent": "GRADUATION_STATUS"})
                finally:
                    graph.close()
                self.assertEqual("UNKNOWN", out["decision"]["graduation_outcome"])
                self.assertFalse(out["decision"]["coverage_complete"])
                self.assertIn(f"RULE_NOT_LOADED:{removed}", out["needs_information"])
                verify_payload(out)

    def test_review_counterexample_common_credits_apply_to_double_and_minor(self):
        for program in ("DOUBLE", "MINOR"):
            with self.subTest(program=program):
                state = complete_student(self.catalog)
                state["program_type"] = program
                out = self.decide(state)
                self.assertEqual("SATISFIED", by_rule(out, "GE-2026-TOTAL-CREDITS")["status"])
                self.assertEqual("SATISFIED", by_rule(out, "GRAD-2026-TOTAL-CREDITS")["status"])
                self.assertEqual("UNKNOWN", out["decision"]["graduation_outcome"])
                self.assertFalse(out["decision"]["coverage_complete"])
                self.assertIn("RULE_FAMILY:OTHER_MAJOR_IF_APPLICABLE", out["decision"]["needs_information"])

    def test_newly_verified_recommended_general_course_is_not_required(self):
        out = execute(self.graph, complete_student(self.catalog), {"intent": "COURSE_LOOKUP", "course_id": "GEA7261"})
        entry = out["decision"]["lookup_result"]
        self.assertEqual(("GENERAL_BALANCED", "DIGITAL_COMMUNICATION", 3, 35),
                         (entry["classification"], entry["general_area"], entry["catalog_credits"], entry["source"]["pdf_page"]))

    def test_reviewer_course_lookup_does_not_hide_personal_scope(self):
        state = complete_student(self.catalog)
        foreign = execute(self.graph, state, {"intent": "COURSE_LOOKUP", "course_id": "GEA8656"})
        nonengineering = execute(self.graph, state, {"intent": "COURSE_LOOKUP", "course_id": "GEA8811"})
        expanded = execute(self.graph, state, {"intent": "COURSE_LOOKUP", "course_id": "GEA5051"})
        self.assertIn("유학생 전용", foreign["answer_text"])
        self.assertIn("자동 산입하지", nonengineering["answer_text"])
        self.assertIn("확대교양", expanded["answer_text"])

    def test_review_counterexample_expanded_general_does_not_satisfy_balanced_area(self):
        state = complete_student(self.catalog)
        state["course_attempts"] = [a for a in state["course_attempts"] if a["course_id"] not in {"GEA7562", "GEA3070"}]
        for code in ("GEA5051", "GEA5050"):
            state["course_attempts"].append({"attempt_id": f"EXPANDED-{code}", "course_id": code,
                                             "completion_status": "COMPLETED", "verification_status": "VERIFIED",
                                             "evidence_id": "SYNTHETIC-EXPANDED", "earned_credits": 3})
        out = self.decide(state)
        self.assertEqual(34, out["decision"]["credited_amount"]["by_area"]["GENERAL_TOTAL"])
        self.assertEqual("UNSATISFIED", by_rule(out, "BALANCED-AREAS")["status"])
        self.assertEqual("NOT_ELIGIBLE_PDF", out["decision"]["graduation_outcome"])

    def test_review_counterexample_foreign_only_and_conflicted_code_stay_unrecognized(self):
        for code in ("GEA8831", "GEA8617"):
            with self.subTest(code=code):
                state = complete_student(self.catalog)
                state["course_attempts"].append({"attempt_id": "RISK", "course_id": code,
                                                 "completion_status": "COMPLETED", "verification_status": "VERIFIED",
                                                 "evidence_id": "SYNTHETIC-RISK", "earned_credits": 3})
                out = self.decide(state)
                self.assertEqual("UNKNOWN", out["decision"]["graduation_outcome"])
                self.assertFalse(any(r["course_id"] == code for r in out["decision"]["recognitions"]))

    def test_verifier_all_promoted_general_codes_occur_on_cited_pdf_page(self):
        import pdfplumber
        general = [c for c in self.catalog["courses"] if c["classification"].startswith("GENERAL_")]
        self.assertEqual(280, len(general))
        index = json.loads((ROOT / "data/processed/source_index.json").read_text(encoding="utf-8"))
        scope = index["runtime_verification"]["verified_general_education"]
        self.assertEqual(list(range(34, 46)), scope["pdf_pages"])
        self.assertEqual((280, 2, "CONFLICTED"),
                         (scope["verified_row_count"], scope["excluded_candidate_count"], scope["excluded_candidate_status"]))
        self.assertNotIn("GEA8617", {c["course_id"] for c in general})
        with pdfplumber.open(ROOT / "docs/curriculum/2026년도 교육과정.pdf") as pdf:
            page_text = {page: pdf.pages[page-1].extract_text() for page in range(34, 46)}
        for course in general:
            with self.subTest(code=course["course_id"]):
                self.assertIn(course["course_id"], page_text[course["source"]["pdf_page"]])

    def test_one_course_below_total_is_confirmed_unmet(self):
        state = complete_student(self.catalog)
        state["course_attempts"] = [a for a in state["course_attempts"] if a["course_id"] != "CDA0163"]
        out = self.decide(state)
        self.assertEqual(127, out["decision"]["credited_amount"]["total"])
        self.assertEqual("UNSATISFIED", by_rule(out, "GRAD-2026-TOTAL-CREDITS")["status"])
        self.assertEqual("NOT_ELIGIBLE_PDF", out["decision"]["graduation_outcome"])

    def test_missing_certification_evidence_needs_information(self):
        state = complete_student(self.catalog)
        del state["official_outcomes"]["graduation_certification_passed"]
        out = self.decide(state)
        self.assertEqual("NEEDS_INFORMATION", by_rule(out, "GRAD-2026-CERTIFICATION")["status"])
        self.assertEqual("UNKNOWN", out["decision"]["graduation_outcome"])

    def test_review_counterexample_unmet_and_missing_evidence_are_both_explained(self):
        state = complete_student(self.catalog)
        state["course_attempts"] = [a for a in state["course_attempts"] if a["course_id"] != "CDA0163"]
        del state["official_outcomes"]["graduation_certification_passed"]
        out = self.decide(state)
        self.assertEqual("NOT_ELIGIBLE_PDF", out["decision"]["graduation_outcome"])
        self.assertIn("확인된 미충족 요건", out["answer_text"])
        self.assertIn("추가 확인 항목", out["answer_text"])

    def test_missing_required_course_name_is_queried_and_explained(self):
        state = complete_student(self.catalog)
        state["course_attempts"] = [a for a in state["course_attempts"] if a["course_id"] != "CDA0016"]
        out = self.decide(state)
        self.assertIn("컴퓨터구조(CDA0016)", out["answer_text"])
        self.assertIn("CDA0016", out["decision"]["missing_courses"])
        self.assertTrue(any(e["event_type"] == "GRAPH_QUERY" and e["operation"] == "FETCH_CATALOG_ENTRY"
                            and e["filters"].get("course_id") == "CDA0016" for e in out["execution_trace"]["events"]))

    def test_verified_certification_failure_is_unmet(self):
        state = complete_student(self.catalog)
        state["official_outcomes"]["graduation_certification_passed"]["value"] = False
        out = self.decide(state)
        self.assertEqual("NOT_ELIGIBLE_PDF", out["decision"]["graduation_outcome"])

    def test_equivalence_review_is_required_for_positive_graduation(self):
        state = complete_student(self.catalog)
        state["equivalence_review_status"] = "UNVERIFIED"
        out = self.decide(state)
        self.assertEqual("UNKNOWN", out["decision"]["graduation_outcome"])
        self.assertIn("OFFICIAL_EQUIVALENCE_REVIEW", out["decision"]["needs_information"])

    def test_review_counterexample_official_review_does_not_invent_a_repeat_choice(self):
        state = complete_student(self.catalog)
        state["course_attempts"].append({"attempt_id": "SYNTHETIC-REPEAT", "course_id": "CDA0143",
                                         "completion_status": "COMPLETED", "verification_status": "VERIFIED",
                                         "evidence_id": "SYNTHETIC-REPEAT-EVIDENCE", "earned_credits": 3})
        out = self.decide(state)
        self.assertIn("REPEAT_RESOLUTION:CDA0143", out["decision"]["needs_information"])
        self.assertEqual("UNKNOWN", out["decision"]["graduation_outcome"])
        self.assertFalse(any(r["course_id"] == "CDA0143" for r in out["decision"]["recognitions"]))

    def test_general_education_cap_changes_graduation_counted_total(self):
        state = complete_student(self.catalog)
        for code in ("GEA8660", "GEA8659", "GEA7301", "GEA7300"):
            if any(a["course_id"] == code for a in state["course_attempts"]):
                continue
            state["course_attempts"].append({"attempt_id": f"EXTRA-{code}", "course_id": code,
                                             "completion_status": "COMPLETED", "verification_status": "VERIFIED",
                                             "evidence_id": f"EXTRA-E-{code}", "earned_credits": 3})
        out = self.decide(state)
        self.assertEqual(46, out["decision"]["credited_amount"]["by_area"]["GENERAL_TOTAL"])
        self.assertEqual(138, out["decision"]["credited_amount"]["total"])
        self.assertTrue(any(e["event_type"] == "CREDIT_CAP" and e["result"]["excluded_credits"] == 4
                            for e in out["execution_trace"]["events"]))


class ReviewerGeneralCases(GeneralAndGraduationCases):
    def test_english_exemption_does_not_award_two_credits(self):
        state = complete_student(self.catalog)
        state["course_attempts"] = [a for a in state["course_attempts"] if a["course_id"] != "GEA8704"]
        state["official_outcomes"]["english_course_exemption"] = {"value": True,
            "verification_status": "VERIFIED", "evidence_id": "SYNTHETIC-ENGLISH-EXEMPTION"}
        out = self.decide(state)
        self.assertEqual("SATISFIED", by_rule(out, "GE-2026-ENGLISH")["status"])
        self.assertEqual(7, by_rule(out, "GE-2026-BASIC-CREDITS")["observed"])
        self.assertEqual("NOT_ELIGIBLE_PDF", out["decision"]["graduation_outcome"])

    def test_source_pdf_duplicate_code_is_never_auto_resolved(self):
        state = complete_student(self.catalog)
        state["course_attempts"].append({"attempt_id": "A-CONFLICT", "course_id": "GEA8617",
                                         "completion_status": "COMPLETED", "verification_status": "VERIFIED",
                                         "evidence_id": "E-CONFLICT", "earned_credits": 3})
        out = self.decide(state)
        self.assertEqual("UNKNOWN", out["decision"]["graduation_outcome"])
        self.assertIn("CATALOG_CLASSIFICATION:GEA8617", out["decision"]["needs_information"])

    def test_partially_documented_record_cannot_be_full_graduation(self):
        state = complete_student(self.catalog)
        state["completion_coverage"] = "PARTIAL"
        out = self.decide(state)
        self.assertEqual("UNKNOWN", out["decision"]["graduation_outcome"])
        self.assertIn("COMPLETE_STUDENT_TRANSCRIPT", out["decision"]["needs_information"])

    def test_missing_official_evidence_id_cannot_pass(self):
        state = complete_student(self.catalog)
        del state["official_outcomes"]["thesis_passed"]["evidence_id"]
        out = self.decide(state)
        self.assertEqual("UNKNOWN", out["decision"]["graduation_outcome"])
        self.assertEqual("NEEDS_INFORMATION", by_rule(out, "GRAD-2026-THESIS-PASSED")["status"])

    def test_missing_applicability_evidence_blocks_positive_decision(self):
        state = complete_student(self.catalog)
        del state["applicability_evidence_id"]
        out = self.decide(state)
        self.assertEqual("UNKNOWN", out["decision"]["graduation_outcome"])

    def test_unverified_cap_rule_blocks_total_graduation_judgment(self):
        changed = deepcopy(self.catalog)
        next(r for r in changed["requirements"] if r["rule_id"] == "R-GE-2026-CREDIT-CAP")["verification_status"] = "UNVERIFIED"
        graph = Graph(Path(":memory:"), changed)
        try:
            out = execute(graph, complete_student(changed), {"intent": "GRADUATION_STATUS"})
            self.assertEqual("UNKNOWN", out["decision"]["graduation_outcome"])
            self.assertIsNone(out["decision"]["credited_amount"]["total"])
            self.assertEqual("NEEDS_INFORMATION", by_rule(out, "GRAD-2026-TOTAL-CREDITS")["status"])
        finally:
            graph.close()


if __name__ == "__main__":
    unittest.main()
