"""Source-derived policy fact lookup and generalization counterexamples."""
from __future__ import annotations

import sys
import unittest
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]
from build_catalog import build  # noqa: E402
from curriculum_assistant.engine import execute  # noqa: E402
from curriculum_assistant.graph import Graph  # noqa: E402
from curriculum_assistant.nlp import interpret  # noqa: E402
from curriculum_assistant.verifier import verify_payload  # noqa: E402


def state():
    return {"student_state_id": "SYNTHETIC-POLICY", "department_id": "DEPT-COMPUTER-ENGINEERING",
            "admission_year": 2026, "credit_policy_year": None, "catalog_year": None,
            "applicability_status": "UNVERIFIED", "program_type": "SINGLE",
            "completion_coverage": "PARTIAL", "course_attempts": []}


class PolicyLookupCases(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = build()
        cls.graph = Graph(Path(":memory:"), cls.catalog)

    @classmethod
    def tearDownClass(cls):
        cls.graph.close()

    def lookup(self, question):
        parsed = interpret(question, self.catalog)
        self.assertEqual("POLICY_LOOKUP", parsed["structured_query"]["intent"])
        return execute(self.graph, state(), parsed["structured_query"])

    def test_credit_minimum_is_source_rule_not_student_amount(self):
        result = self.lookup("새내기 컴퓨터공학과 단일전공의 졸업학점 기준 알려줘")
        self.assertIn("130학점", result["answer_text"])
        self.assertIsNone(result["decision"]["credited_amount"])
        self.assertIn("CE-CREDITS", result["evidence"]["source_locators"])

    def test_entry_year_is_distinct_from_document_year(self):
        current = self.lookup("2026학번에게 이 교육과정이 적용되는 기준은?")
        earlier = self.lookup("2025학번에게 이 교육과정이 적용되는 기준은?")
        self.assertIn("2026학년도 일반 신입생", current["answer_text"])
        self.assertIn("2025학년도 입학생", earlier["answer_text"])
        self.assertNotIn("2026학년도 일반 신입생", earlier["answer_text"])

    def test_review_counterexample_earlier_entry_year_does_not_inherit_2026_credit_minimum(self):
        result = self.lookup("2025학번 컴퓨터공학과 졸업학점은 몇 학점이야?")
        self.assertIn("2025학년도 단일전공 연도별 표: 졸업 총학점 130학점", result["answer_text"])
        self.assertEqual("FOUND", result["decision"]["lookup_status"])
        self.assertTrue(result["answer_text"].startswith("컴퓨터공학과 2025학년도 입학생 적용 원칙"))
        self.assertEqual([], result["decision"]["lookup_result"]["rules"])
        self.assertEqual([], result["decision"]["needs_information"])
        self.assertIn("CE-YEAR-GRAD-2025", result["evidence"]["source_locators"])
        self.assertTrue(any(e["event_type"] == "POLICY_SCOPE_EXCLUDED" for e in result["execution_trace"]["events"]))
        self.assertIn("CURRICULUM-APPLICATION-2026", result["evidence"]["source_locators"])

    def test_review_counterexample_student_entry_year_scopes_unspecified_question(self):
        student = state()
        student["admission_year"] = 2024
        result = execute(self.graph, student, {"intent": "POLICY_LOOKUP", "topics": ["MAJOR_CREDITS"]})
        self.assertEqual([], result["decision"]["lookup_result"]["rules"])
        self.assertIn("2024학년도", result["answer_text"])
        self.assertIn("전공선택 57학점", result["answer_text"])
        self.assertIn("CE-YEAR-GRAD-2020-2024", result["evidence"]["source_locators"])

    def test_historical_boundaries_are_sourced_without_student_graduation_claim(self):
        early = self.lookup("2006학번 컴퓨터공학과 졸업학점은 몇 학점이야?")
        self.assertIn("140학점", early["answer_text"])
        self.assertIn("CE-YEAR-GRAD-2006-2012", early["evidence"]["source_locators"])
        self.assertIn("교양 26·전필 15·전선 48학점", early["answer_text"])
        self.assertIn("CE-TRANSITION", early["evidence"]["source_locators"])
        unsupported = self.lookup("2002학번 컴퓨터공학과 졸업학점은 몇 학점이야?")
        self.assertEqual("NEEDS_INFORMATION", unsupported["decision"]["lookup_status"])
        self.assertNotIn("140학점", unsupported["answer_text"])

    def test_review_counterexample_historical_year_rollover_uses_own_table_row(self):
        expected = {2017: (140, 29, "CE-YEAR-GRAD-2013-2019"),
                    2018: (130, 26, "CE-YEAR-GRAD-2013-2019"),
                    2020: (130, 26, "CE-YEAR-GRAD-2020-2024"),
                    2021: (130, 26, "CE-YEAR-GRAD-2020-2024")}
        for year, (graduation, general, locator) in expected.items():
            with self.subTest(year=year):
                result = self.lookup(f"{year}학번 컴퓨터공학과 졸업학점은?")
                rows = [fact for fact in result["decision"]["lookup_result"]["policy_facts"]
                        if fact["predicate"] == "ANNUAL_SINGLE_MAJOR_CREDIT_ROW"]
                self.assertEqual(1, len(rows))
                self.assertEqual((graduation, general),
                                 (rows[0]["value"]["graduation_total"], rows[0]["value"]["general_total"]))
                self.assertEqual([], result["decision"]["lookup_result"]["rules"])
                self.assertIn(locator, result["evidence"]["source_locators"])

    def test_multi_program_policy_has_correct_scope_and_source(self):
        double = self.lookup("2026 컴퓨터공학과 복수전공 규칙과 전공학점 알려줘")
        self.assertIn("45학점", double["answer_text"])
        self.assertIn("2025학년도 이후 선발자 9학점", double["answer_text"])
        self.assertIn("DOUBLE-MAJOR-POLICY-2026", double["evidence"]["source_locators"])
        self.assertNotIn("PF-MINOR-2026", {f["policy_fact_id"] for f in double["evidence"]["policy_facts"]})
        minor = self.lookup("2026 컴퓨터공학과 부전공 기준은?")
        self.assertIn("부전공 21학점 이상", minor["answer_text"])
        self.assertIn("MINOR-POLICY-2026", minor["evidence"]["source_locators"])
        self.assertNotIn("PF-DOUBLE-2026", {f["policy_fact_id"] for f in minor["evidence"]["policy_facts"]})

    def test_review_counterexample_double_major_scope_does_not_inherit_78(self):
        result = self.lookup("컴퓨터공학과 복수전공의 전공학점 기준은?")
        rules = result["decision"]["lookup_result"]["rules"]
        self.assertTrue(any(r.get("required_value") == 45 for r in rules))
        self.assertFalse(any(r.get("required_value") == 78 for r in rules))

    def test_personal_credit_question_stays_student_state_query(self):
        parsed = interpret("내가 지금까지 전공학점 몇 학점 인정받았어?", self.catalog)
        self.assertEqual("CREDIT_SUMMARY", parsed["structured_query"]["intent"])

    def test_review_counterexample_remaining_required_courses_are_personal_gaps(self):
        parsed = interpret("전공필수 중에 남은 과목 있어?", self.catalog)
        self.assertEqual("REQUIREMENT_GAPS", parsed["structured_query"]["intent"])

    def test_recommendation_is_not_required_course(self):
        result = self.lookup("학과가 권장하는 교양 과목은 반드시 들어야 하나?")
        facts = result["decision"]["lookup_result"]["policy_facts"]
        self.assertEqual(1, len(facts))
        self.assertFalse(facts[0]["value"]["mandatory"])
        self.assertIn("CE-RECOMMENDED", result["evidence"]["source_locators"])

    def test_zero_credit_required_courses_are_in_lookup(self):
        result = self.lookup("컴퓨터공학과 전공필수 전체 목록 알려줘")
        courses = result["decision"]["lookup_result"]["courses"]
        zero = {c["course_id"] for c in courses if c["catalog_credits"] == 0}
        self.assertEqual({"CDA0034", "CDA0088"}, zero)
        self.assertEqual(9, len(courses))

    def test_unknown_policy_topic_rejected(self):
        with self.assertRaisesRegex(ValueError, "allowlisted topics"):
            execute(self.graph, state(), {"intent": "POLICY_LOOKUP", "topics": ["WRITE_SQL"]})

    def test_review_counterexample_forged_policy_source_is_rejected(self):
        result = self.lookup("교육과정 적용 학번 기준이 뭐야?")
        forged = deepcopy(result)
        forged["evidence"]["policy_facts"][0]["source_refs"] = ["NONEXISTENT-PDF-LOCATION"]
        with self.assertRaisesRegex(ValueError, "Policy fact lacks verified PDF provenance"):
            verify_payload(forged)

    def test_pdf_contains_source_phrases(self):
        import pdfplumber
        with pdfplumber.open(ROOT / "docs/curriculum/2026년도 교육과정.pdf") as pdf:
            self.assertIn("입학년도를 기준으로 적용", pdf.pages[12].extract_text())
            self.assertIn("이수학점은 잔여학점으로 인정", pdf.pages[12].extract_text())
            self.assertIn("선이수교과목의", pdf.pages[13].extract_text())
            self.assertIn("학과 권장 교과목", pdf.pages[260].extract_text())
            self.assertIn("연도별 경과조치", pdf.pages[263].extract_text())


if __name__ == "__main__":
    unittest.main()
