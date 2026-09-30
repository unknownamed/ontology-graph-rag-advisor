from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
from build_catalog import build  # noqa: E402
from curriculum_assistant.nlp import interpret  # noqa: E402


class KoreanQuestionCases(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = build()

    def test_official_name_and_colloquial_alias(self):
        for utterance in ("고급자료구조 몇 학점이야?", "고자구 몇 학점임?"):
            parsed = interpret(utterance, self.catalog)
            self.assertEqual("RESOLVED", parsed["interpretation_status"])
            self.assertEqual({"intent": "COURSE_LOOKUP", "course_id": "CDA0143"}, parsed["structured_query"])

    def test_spacing_error_and_typo(self):
        for utterance in ("고 급 자 료 구 조 몇 학점?", "고급자료구죠 몇 학점?"):
            self.assertEqual("CDA0143", interpret(utterance, self.catalog)["structured_query"]["course_id"])

    def test_context_and_simulation(self):
        first = interpret("자료구조 학점 알려줘", self.catalog)
        second = interpret("그 과목 하나 더 들으면?", self.catalog, first["context"])
        self.assertEqual("CDA0008", second["structured_query"]["course_id"])
        self.assertEqual("WHAT_IF", second["structured_query"]["intent"])

    def test_graduation_combined_question_and_missing_context(self):
        result = interpret("저 졸업 가능하고 필수 뭐 남았어요?", self.catalog)
        self.assertEqual("GRADUATION_STATUS", result["structured_query"]["intent"])
        unknown = interpret("그 과목 하나 더 들으면?", self.catalog)
        self.assertEqual("WHAT_IF", unknown["structured_query"]["intent"])
        self.assertEqual("CONTEXT_COURSE", unknown["structured_query"]["target_selector"])
        self.assertNotIn("course_id", unknown["structured_query"])

    def test_no_free_query_or_rule_numbers(self):
        result = interpret("CDA0143 들으면 전공 몇 학점?", self.catalog)
        self.assertEqual("WHAT_IF", result["structured_query"]["intent"])
        self.assertEqual({"intent", "course_id", "assumed_completion"}, set(result["structured_query"]))

    def test_parsed_question_uses_same_decision_engine(self):
        from curriculum_assistant.engine import execute
        from curriculum_assistant.graph import Graph
        from test_vertical_slice import student
        parsed = interpret("고자구 몇 학점임?", self.catalog)
        graph = Graph(Path(":memory:"), self.catalog)
        try:
            out = execute(graph, student(), parsed["structured_query"])
            self.assertIn("전공필수, 학점은 3학점", out["answer_text"])
            self.assertIn("PDF 262쪽", out["answer_text"])
        finally:
            graph.close()

    def test_area_credit_question_names_requested_area(self):
        from curriculum_assistant.engine import execute
        from curriculum_assistant.graph import Graph
        from test_vertical_slice import student
        graph = Graph(Path(":memory:"), self.catalog)
        try:
            state = student(["CDA0143", "CDA0163"], coverage="PARTIAL")
            parsed = interpret("지금까지 전공학점 몇 학점 인정받았어?", self.catalog)
            self.assertEqual("MAJOR_TOTAL", parsed["structured_query"]["area"])
            out = execute(graph, state, parsed["structured_query"])
            self.assertIn("전공 합계 인정학점의 하한은 6학점", out["answer_text"])
            self.assertEqual(6, out["decision"]["credited_amount"]["by_area"]["MAJOR_TOTAL"])
            with self.assertRaisesRegex(ValueError, "area is not allowlisted"):
                execute(graph, state, {"intent": "CREDIT_SUMMARY", "area": "MAJOR_ADVANCED"})
        finally:
            graph.close()


class ReviewerLanguageCases(KoreanQuestionCases):
    def test_catalog_aggregate_is_not_policy_minimum(self):
        for question, operation in (("2026 전공에 편성된 과목 총 몇 개지?", "COUNT"),
                                    ("컴퓨터공학 전공 과목 전체 학점 합계를 말해줘", "SUM_CREDITS")):
            parsed = interpret(question, self.catalog)
            self.assertEqual("CATALOG_AGGREGATE", parsed["structured_query"]["intent"])
            self.assertEqual(operation, parsed["structured_query"]["aggregate"])
            self.assertNotIn("required_value", parsed["structured_query"])

    def test_unknown_added_course_does_not_collapse_into_current_audit(self):
        parsed = interpret("내 부족한 요건과 새 수업 추가 후 변화를 같이 보여줘", self.catalog)
        self.assertEqual("WHAT_IF", parsed["structured_query"]["intent"])
        self.assertEqual("UNSPECIFIED_COURSE", parsed["structured_query"]["target_selector"])
        self.assertTrue(parsed["structured_query"]["comparison_requested"])
        self.assertNotIn("course_id", parsed["structured_query"])

    def test_catalog_context_has_no_student_claim(self):
        from curriculum_assistant.engine import execute
        from curriculum_assistant.graph import Graph
        from curriculum_assistant.server import catalog_query_context
        context = catalog_query_context()
        self.assertIsNone(context["admission_year"])
        self.assertNotIn("student_id", context)
        graph = Graph(Path(":memory:"), self.catalog)
        try:
            result = execute(graph, context, {"intent": "COURSE_LOOKUP", "course_id": "CDA0143"})
            self.assertEqual("FOUND", result["decision"]["lookup_status"])
        finally:
            graph.close()

    def test_second_program_graduation_question_is_personal_decision(self):
        parsed = interpret("제2전공까지 합친 제 졸업 여부 판정 부탁해", self.catalog)
        self.assertEqual("GRADUATION_STATUS", parsed["structured_query"]["intent"])

    def test_nesting_prefers_full_name(self):
        advanced = interpret("고급자료구조 이수구분은?", self.catalog)
        basic = interpret("자료구조 이수구분은?", self.catalog)
        self.assertEqual("CDA0143", advanced["structured_query"]["course_id"])
        self.assertEqual("CDA0008", basic["structured_query"]["course_id"])

    def test_unknown_course_is_not_fabricated(self):
        parsed = interpret("양자컴퓨팅실습 몇 학점?", self.catalog)
        self.assertEqual("NEEDS_INFORMATION", parsed["interpretation_status"])
        self.assertIsNone(parsed["structured_query"])


if __name__ == "__main__":
    unittest.main()
