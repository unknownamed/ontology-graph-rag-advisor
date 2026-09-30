"""Independent source-based counterexamples for policy scope and credit arithmetic."""
from __future__ import annotations

import sys
import unittest
import json
import threading
import tempfile
import urllib.request
from copy import deepcopy
from http.server import HTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]
from build_catalog import build  # noqa: E402
from refine_2026_policy import refined_catalog  # noqa: E402
from curriculum_assistant.engine import execute  # noqa: E402
from curriculum_assistant.authority import RuleSetStore  # noqa: E402
from curriculum_assistant.graph import Graph  # noqa: E402
from curriculum_assistant.nlp import interpret  # noqa: E402
from curriculum_assistant.server import catalog_query_context  # noqa: E402
from curriculum_assistant.server import Handler  # noqa: E402
from curriculum_assistant.verifier import verify_payload  # noqa: E402


class PolicyRefinementCases(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = refined_catalog(build())
        cls.graph = Graph(Path(":memory:"), cls.catalog)

    @classmethod
    def tearDownClass(cls):
        cls.graph.close()

    def ask(self, question):
        parsed = interpret(question, self.catalog)
        self.assertEqual("POLICY_LOOKUP", parsed["structured_query"]["intent"])
        payload = execute(self.graph, catalog_query_context(), parsed["structured_query"])
        verify_payload(payload)
        return payload

    # Conditional applicability: three different student/program boundaries.
    def test_transfer_excludes_all_general_obligations(self):
        payload = self.ask("전적대학에서 옮겨 온 편입생의 교양 영역 의무 범위는?")
        self.assertIn("교양 이수 의무가 없습니다", payload["answer_text"])
        app = payload["decision"]["lookup_result"]["rule_applicability"]
        self.assertTrue(all(item["status"] == "NOT_APPLICABLE" for rid, item in app.items() if rid.startswith("R-GE-")))

    def test_contract_department_has_reduced_minimum_and_no_area_minimum(self):
        payload = self.ask("계약학과에 해당하는 교양 영역별 최소 기준을 정리해줘")
        self.assertIn("26학점", payload["answer_text"])
        self.assertNotIn("교양: 최소 34학점", payload["answer_text"])
        self.assertEqual("NOT_APPLICABLE", payload["decision"]["lookup_result"]["rule_applicability"]["R-GE-2026-BALANCED-AREAS"]["status"])

    def test_minor_marked_courses_do_not_attach_to_single_major(self):
        payload = self.ask("단일전공만 등록한 학생에게 부전공 표시 과목은 추가 의무인가?")
        self.assertIn("추가 졸업요건으로 적용되지 않습니다", payload["answer_text"])
        self.assertEqual("SINGLE", payload["decision"]["lookup_result"]["program_type"])

    def test_personal_transfer_does_not_fail_regular_general_minima(self):
        fixture = json.loads((ROOT / "tests/fixtures/core_eligible_synthetic.json").read_text(encoding="utf8"))
        state = deepcopy(fixture["student_state"])
        state["student_category"] = "TRANSFER"
        state["student_category_evidence_id"] = "SYNTHETIC-TRANSFER-STATUS"
        payload = execute(self.graph, state, {"intent": "GRADUATION_STATUS"})
        verify_payload(payload)
        by_id = {r["rule_id"]: r for r in payload["decision"]["requirement_results"]}
        self.assertEqual("NOT_APPLICABLE", by_id["R-GE-2026-BALANCED-AREAS"]["status"])
        self.assertEqual("NOT_APPLICABLE", by_id["R-GE-2026-TOTAL-CREDITS"]["status"])
        self.assertEqual("PF-GE-2026-EXCEPTIONS", by_id["R-GE-2026-TOTAL-CREDITS"]["applicability_policy_fact_id"])
        self.assertEqual("UNKNOWN", payload["decision"]["graduation_outcome"])

    def test_personal_adult_category_keeps_unloaded_minimum_uncertain(self):
        fixture = json.loads((ROOT / "tests/fixtures/core_eligible_synthetic.json").read_text(encoding="utf8"))
        state = deepcopy(fixture["student_state"])
        state["student_category"] = "EMPLOYED_ADULT"
        state["student_category_evidence_id"] = "SYNTHETIC-ADULT-STATUS"
        payload = execute(self.graph, state, {"intent": "GRADUATION_STATUS"})
        verify_payload(payload)
        by_id = {r["rule_id"]: r for r in payload["decision"]["requirement_results"]}
        self.assertEqual("NOT_APPLICABLE", by_id["R-GE-2026-BALANCED-AREAS"]["status"])
        self.assertEqual("NOT_APPLICABLE", by_id["R-GE-2026-TOTAL-CREDITS"]["status"])
        self.assertEqual("UNKNOWN", payload["decision"]["graduation_outcome"])

    # Numeric boundaries: none are copied from assessment questions or answers.
    def test_general_earned_below_cap(self):
        payload = self.ask("교양 41학점 취득 시 인정 범위를 알려줘")
        calc = next(c for c in payload["decision"]["lookup_result"]["calculations"] if c["operation"] == "APPLY_VERIFIED_CREDIT_CAP")
        self.assertEqual((41, 41, 0), (calc["earned_amount"], calc["recognized_amount"], calc["excess_amount"]))

    def test_general_earned_at_cap(self):
        payload = self.ask("교양에서 42학점 이수하면 상한 계산은?")
        calc = next(c for c in payload["decision"]["lookup_result"]["calculations"] if c["operation"] == "APPLY_VERIFIED_CREDIT_CAP")
        self.assertEqual((42, 0), (calc["recognized_amount"], calc["excluded_amount"]))

    def test_general_earned_above_cap(self):
        payload = self.ask("교양에서 47학점 취득한 경우 인정 한도는?")
        calc = next(c for c in payload["decision"]["lookup_result"]["calculations"] if c["operation"] == "APPLY_VERIFIED_CREDIT_CAP")
        self.assertEqual((42, 5), (calc["recognized_amount"], calc["excess_amount"]))
        self.assertIn("47학점 중", payload["answer_text"])

    def test_general_minimum_shortfall_is_computed(self):
        payload = self.ask("교양 29학점 취득 상황의 최소 기준과 상한은?")
        calc = next(c for c in payload["decision"]["lookup_result"]["calculations"] if c["operation"] == "APPLY_VERIFIED_CREDIT_CAP")
        self.assertEqual(5, calc["remaining_amount"])

    def test_area_course_credit_is_not_student_earned_amount(self):
        payload = self.ask("균형교양 과목이 2학점짜리면 영역 분류는 유지되나?")
        self.assertFalse(any(c["operation"] == "APPLY_VERIFIED_CREDIT_CAP"
                             for c in payload["decision"]["lookup_result"]["calculations"]))

    def test_cap_threshold_mention_is_not_student_earned_amount(self):
        payload = self.ask("교양 인정 상한 42학점의 초과분은 총 취득에 남나?")
        self.assertFalse(any(c["operation"] == "APPLY_VERIFIED_CREDIT_CAP"
                             for c in payload["decision"]["lookup_result"]["calculations"]))

    def test_graduation_remainder_uses_three_distinct_source_rules(self):
        payload = self.ask("졸업 잔여학점 구조는 총량에서 어떻게 도출돼?")
        calc = next(c for c in payload["decision"]["lookup_result"]["calculations"]
                    if c["operation"] == "GRADUATION_REMAINDER_STRUCTURE")
        self.assertEqual(18, calc["required_amount"])
        self.assertEqual(3, len(calc["source_rule_ids"]))

    # Policy-only questions must not borrow or invent a StudentState.
    def test_policy_scope_without_student(self):
        payload = self.ask("2026 컴퓨터공학과 최소 졸업학점 기준을 알려줘")
        self.assertEqual("NOT_REQUESTED", payload["decision"]["graduation_outcome"])
        self.assertIsNone(payload["decision"]["credited_amount"])

    def test_general_residual_policy_is_not_a_personal_plan(self):
        payload = self.ask("2026학년도 교양 잔여학점 편성 기준을 알려줘")
        self.assertIn("13학점", payload["answer_text"])
        self.assertEqual("POLICY_LOOKUP", payload["decision"]["intent"])

    def test_earlier_year_keeps_its_own_source_row(self):
        payload = self.ask("2007학번 컴퓨터공학과 졸업 총학점 표는?")
        self.assertEqual([], payload["decision"]["lookup_result"]["rules"])
        self.assertIn("CE-YEAR-GRAD-2006-2012", payload["evidence"]["source_locators"])

    def test_open_ended_old_cohort_does_not_inherit_2026_numbers(self):
        payload = self.ask("기존 학번의 교양학점 적용 기준은 무엇인가?")
        self.assertIn("APPLICABLE_CURRICULUM_RULES_FOR_ENTRY_YEAR:UNKNOWN", payload["decision"]["needs_information"])
        self.assertNotIn("교양: 최소 34학점", payload["answer_text"])

    # Partial answers keep source-backed facts and identify the unknown part.
    def test_counseling_count_is_not_fabricated(self):
        payload = self.ask("컴퓨터공학과 심층상담의 회차별 이수 지침은?")
        self.assertIn("0학점 전공필수", payload["answer_text"])
        self.assertIn("횟수는", payload["answer_text"])

    def test_revised_course_principle_without_historical_full_ruleset(self):
        payload = self.ask("이전 학번이 개편 교육과정 과목을 들을 때 적용하는 원칙은?")
        self.assertIn("개편된 교육과정", payload["answer_text"])
        self.assertEqual([], payload["decision"]["requirement_results"])

    def test_official_substitution_pairs_remain_unknown(self):
        payload = self.ask("특정 교과목의 대체과목 지정표를 현재 규정에서 확인할 수 있나?")
        self.assertIn("공식 지정", payload["answer_text"])
        self.assertIn("아직 확인되지 않았습니다", payload["answer_text"])
        self.assertNotIn("졸업 가능", payload["answer_text"])

    def test_minor_policy_does_not_show_nine_main_major_requirements(self):
        payload = self.ask("컴퓨터공학 부전공 필수 지정과목 현황은?")
        self.assertEqual([], [r for r in payload["decision"]["lookup_result"]["rules"]
                              if r["rule_type"] == "REQUIRED_COURSES"])
        self.assertEqual({"CDA0008", "CDA0016", "CDA0017"},
                         {c["course_id"] for c in payload["decision"]["lookup_result"]["courses"]})
        self.assertTrue(any(course["source"]["pdf_page"] == 262
                            for course in payload["decision"]["lookup_result"]["courses"]))
        self.assertIn("262", payload["answer_text"])

    def test_source_refinement_preserves_v1_executable_rules(self):
        original = build()
        self.assertEqual(original["requirements"], self.catalog["requirements"])
        self.assertEqual(original["authoritative_document_set"], self.catalog["authoritative_document_set"])
        self.assertEqual(2, self.catalog["curriculum_ruleset"]["ruleset_version"])

    def test_source_refinement_rejects_unrelated_catalog_change(self):
        with tempfile.TemporaryDirectory() as directory:
            store = RuleSetStore(Path(directory))
            store.initialize(build())
            altered = refined_catalog(store.load_active())
            altered["department"]["name_ko"] = "임의 변경"
            with self.assertRaisesRegex(ValueError, "only append sourced policy facts"):
                store.activate_source_refinement(altered)

    def test_http_policy_and_mixed_personal_question_without_student(self):
        class Bound(Handler):
            pass
        server = HTTPServer(("127.0.0.1", 0), Bound)
        ready = threading.Event()
        def run():
            graph = Graph(Path(":memory:"), self.catalog)
            Bound.graph = graph
            ready.set()
            try:
                server.serve_forever()
            finally:
                graph.close()
        thread = threading.Thread(target=run, daemon=True)
        thread.start()
        self.assertTrue(ready.wait(5))
        try:
            for question, partial in (
                ("2026 교양 최소학점 기준은?", False),
                ("내 교양 인정학점과 최소 기준을 함께 알려줘", True),
            ):
                request = urllib.request.Request(
                    f"http://127.0.0.1:{server.server_address[1]}/api/query",
                    data=json.dumps({"utterance": question, "use_local_llm": False}, ensure_ascii=False).encode(),
                    headers={"Content-Type": "application/json"})
                with urllib.request.urlopen(request, timeout=10) as response:
                    self.assertEqual(200, response.status)
                    payload = json.load(response)
                verify_payload(payload)
                self.assertEqual("POLICY_LOOKUP", payload["decision"]["intent"])
                self.assertEqual(partial, "STUDENT_STATE_FOR_PERSONAL_CALCULATION" in payload["decision"]["needs_information"])
                self.assertIn("34학점", payload["answer_text"])
        finally:
            server.shutdown()
            server.server_close()
            thread.join(5)

    def test_core_graduation_result_is_unchanged_across_refinement(self):
        original_graph = Graph(Path(":memory:"), build())
        try:
            fixture = json.loads((ROOT / "tests/fixtures/core_eligible_synthetic.json").read_text(encoding="utf8"))
            state = fixture["student_state"]
            before = execute(original_graph, state, {"intent": "GRADUATION_STATUS"})
            after = execute(self.graph, state, {"intent": "GRADUATION_STATUS"})
            verify_payload(before)
            verify_payload(after)
            self.assertEqual(before["decision"]["graduation_outcome"], after["decision"]["graduation_outcome"])
            self.assertEqual(before["decision"]["credited_amount"], after["decision"]["credited_amount"])
            self.assertEqual([(r["rule_id"], r["status"]) for r in before["decision"]["requirement_results"]],
                             [(r["rule_id"], r["status"]) for r in after["decision"]["requirement_results"]])
        finally:
            original_graph.close()


if __name__ == "__main__":
    unittest.main()
