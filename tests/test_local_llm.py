from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
from build_catalog import build  # noqa: E402
from curriculum_assistant.engine import execute  # noqa: E402
from curriculum_assistant.graph import Graph  # noqa: E402
from curriculum_assistant.local_llm import express_with_local_llm, interpret_with_local_llm  # noqa: E402
from curriculum_assistant.verifier import verify_payload  # noqa: E402


class LocalModelBoundaryCases(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = build()

    def fake(self, intent, mention):
        return lambda question: ({"intent": intent, "course_mention": mention}, {"model": "fake", "wall_seconds": 0})

    def test_wrong_model_intent_cannot_change_clear_question(self):
        parsed = interpret_with_local_llm("고자구 몇 학점이야?", self.catalog,
                                          transport=self.fake("GRADUATION_STATUS", "고자구"))
        self.assertEqual("COURSE_LOOKUP", parsed["structured_query"]["intent"])
        self.assertEqual("CDA0143", parsed["structured_query"]["course_id"])
        self.assertEqual("REJECTED_INTENT_MISMATCH", parsed["llm"]["status"])

    def test_policy_lookup_does_not_invoke_model_without_policy_schema(self):
        def forbidden(question):
            raise AssertionError("Model must not be called for policy lookup")
        parsed = interpret_with_local_llm("교양 학점 상한 기준 알려줘", self.catalog, transport=forbidden)
        self.assertEqual("POLICY_LOOKUP", parsed["structured_query"]["intent"])
        self.assertEqual("NOT_USED_FOR_POLICY_LOOKUP", parsed["llm"]["status"])

    def test_invented_course_mention_is_rejected(self):
        parsed = interpret_with_local_llm("그 과목은?", self.catalog,
                                          transport=self.fake("COURSE_LOOKUP", "고자구"))
        self.assertEqual("NEEDS_INFORMATION", parsed["interpretation_status"])
        self.assertEqual("REJECTED_INVENTED_MENTION", parsed["llm"]["status"])

    def test_ambiguous_course_is_not_forced_to_first_candidate(self):
        parsed = interpret_with_local_llm("현장실습 몇 학점?", self.catalog,
                                          transport=self.fake("COURSE_LOOKUP", "현장실습"))
        self.assertEqual("AMBIGUOUS", parsed["interpretation_status"])

    def test_unavailable_model_falls_back_without_changing_decision_input(self):
        def broken(question):
            raise OSError("local server unavailable")
        parsed = interpret_with_local_llm("고자구 몇 학점?", self.catalog, transport=broken)
        self.assertEqual("COURSE_LOOKUP", parsed["structured_query"]["intent"])
        self.assertEqual("UNAVAILABLE_OR_INVALID", parsed["llm"]["status"])

    def test_expression_style_cannot_change_locked_decision_or_source(self):
        graph = Graph(Path(":memory:"), self.catalog)
        state = {"student_state_id": "SYNTHETIC-LLM", "admission_year": 2026,
                 "department_id": "DEPT-COMPUTER-ENGINEERING", "credit_policy_year": 2026,
                 "catalog_year": 2026, "applicability_status": "VERIFIED", "program_type": "SINGLE",
                 "completion_coverage": "PARTIAL", "course_attempts": []}
        try:
            base = execute(graph, state, {"intent": "COURSE_LOOKUP", "course_id": "CDA0143"})
        finally:
            graph.close()
        styled = express_with_local_llm(base, lambda _: ({"style": "CONVERSATIONAL"}, {"model": "fake"}))
        self.assertEqual(base["decision"], styled["decision"])
        self.assertEqual(base["evidence"], styled["evidence"])
        self.assertEqual(base["execution_trace"], styled["execution_trace"])
        self.assertTrue(styled["answer_text"].startswith("확인 결과, "))
        verify_payload(styled)
        rejected = express_with_local_llm(base, lambda _: ({"style": "ELIGIBLE_PDF"}, {"model": "fake"}))
        self.assertEqual("REJECTED_SCHEMA", rejected["llm_expression"]["status"])
        self.assertEqual(base["answer_text"], rejected["answer_text"])
        rejected["answer_text"] = "해당 PDF 기준 졸업 가능"
        with self.assertRaisesRegex(ValueError, "Rendered answer differs"):
            verify_payload(rejected)


if __name__ == "__main__":
    unittest.main()
