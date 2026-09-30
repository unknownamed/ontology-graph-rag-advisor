"""Contract tests for the independent scenario failure families."""
from __future__ import annotations

import json
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
from curriculum_assistant.server import catalog_query_context  # noqa: E402
from curriculum_assistant.verifier import verify_payload  # noqa: E402


class IndependentExtensionCases(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = build()
        cls.graph = Graph(Path(":memory:"), cls.catalog)
        cls.base = json.loads((ROOT / "tests/fixtures/core_eligible_synthetic.json").read_text(encoding="utf-8"))["student_state"]
        cls.rules = {r["rule_id"]: r for r in cls.catalog["requirements"] if r["verification_status"] == "VERIFIED"}
        cls.required = next(r for r in cls.rules.values() if r["rule_type"] == "REQUIRED_COURSES")
        cls.courses = {c["course_id"]: c for c in cls.catalog["courses"] if c["verification_status"] == "VERIFIED"}

    @classmethod
    def tearDownClass(cls):
        cls.graph.close()

    def query(self, question: str, state: dict | None = None, context: dict | None = None) -> dict:
        parsed = interpret(question, self.catalog, context)
        self.assertIsNotNone(parsed["structured_query"], parsed)
        payload = execute(self.graph, state or catalog_query_context(), parsed["structured_query"])
        verify_payload(payload)
        return payload

    def test_catalog_aggregate_uses_verified_entries_not_minimum_rule(self):
        major = [c for c in self.courses.values() if c["classification"].startswith("MAJOR_")]
        count = self.query("이 교육과정의 전공 과목 개수가 몇 개입니까?")
        credits = self.query("편성된 전공 과목의 학점 총합은 얼마야?")
        self.assertEqual(len(major), count["decision"]["lookup_result"]["value"])
        self.assertEqual(sum(c["catalog_credits"] for c in major), credits["decision"]["lookup_result"]["value"])
        minimum = next(r["required_value"] for r in self.rules.values() if r.get("area") == "MAJOR_TOTAL")
        self.assertNotEqual(minimum, credits["decision"]["lookup_result"]["value"])
        self.assertIn("FETCH_CATALOG_SET", count["execution_trace"]["events"][0]["operations"])
        self.assertEqual(len(major), len(count["evidence"]["facts"]))

    def test_requirement_catalog_contains_only_verified_applicable_rules(self):
        payload = self.query("졸업을 판정할 때 확인하는 요건 목록을 나열해줘")
        rules = payload["decision"]["lookup_result"]["rules"]
        self.assertTrue(rules)
        self.assertTrue(all(r["verification_status"] == "VERIFIED" for r in rules))
        self.assertTrue(all("SINGLE" in r.get("program_types", ["SINGLE", "MINOR", "DOUBLE"]) for r in rules))
        self.assertTrue(all(set(r["source_refs"]).issubset(payload["evidence"]["source_locators"]) for r in rules))

    def test_unresolved_completion_record_is_preserved_and_not_credited(self):
        state = deepcopy(self.base)
        state["course_attempts"].append({"attempt_id": "MISSING-CODE", "completion_status": "COMPLETED",
                                         "verification_status": "UNVERIFIED", "evidence_id": "INPUT-MISSING-CODE"})
        payload = self.query("이수기록에서 코드가 비어 있으면 졸업학점에 산입해도 될까?", state)
        self.assertEqual("NEEDS_INFORMATION", payload["decision"]["decision_status"])
        self.assertTrue(any(x.startswith("UNRESOLVED_COMPLETION_RECORD:MISSING-CODE:")
                            for x in payload["decision"]["needs_information"]))
        self.assertIn("MISSING_COURSE_ID", [x["reason"] for x in payload["decision"]["excluded"]])
        self.assertIn("course_id", payload["answer_text"])

    def test_one_missing_required_target_is_derived_and_input_is_immutable(self):
        required_id = next(c for c in self.required["course_ids"] if self.courses[c]["catalog_credits"] > 0)
        state = deepcopy(self.base)
        state["course_attempts"] = [a for a in state["course_attempts"] if a["course_id"] != required_id]
        frozen = deepcopy(state)
        payload = self.query("부족한 전공필수 하나를 이수했다고 가정하면 무엇이 달라져?", state)
        self.assertIsNotNone(payload["scenario_decision"])
        self.assertEqual("CALCULATED", payload["scenario_delta"]["status"])
        self.assertEqual(state, frozen)
        self.assertTrue(any(x["rule_id"] == self.required["rule_id"] for x in payload["scenario_delta"]["changed_requirements"]))

    def test_unnamed_course_yields_partial_actual_answer(self):
        state = deepcopy(self.base)
        payload = self.query("수업 두 개를 더 들으면 현재 부족 조건이 사라질까?", state)
        self.assertIsNone(payload["scenario_decision"])
        self.assertEqual("NEEDS_TARGET", payload["scenario_delta"]["status"])
        self.assertEqual("NEEDS_INFORMATION", payload["decision"]["decision_status"])
        self.assertIn("가상 결과는 아직 계산하지 않았습니다", payload["answer_text"])

    def test_consistency_and_trace_explanation_use_executed_evidence(self):
        state = deepcopy(self.base)
        for question in ("학생 이수목록을 역순으로 넣어도 같은 결과가 나오는지 검사해줘",
                         "동일한 질문을 다시 하면 결과도 같은지 확인해줘"):
            payload = self.query(question, state)
            self.assertTrue(payload["decision"]["lookup_result"]["consistent"])
            self.assertTrue(any(e["event_type"] == "CONSISTENCY_CHECK" for e in payload["execution_trace"]["events"]))
        trace = self.query("실제로 사용한 관계와 규칙의 실행 근거를 설명해줘", state)
        self.assertEqual(set(trace["decision"]["lookup_result"]["relationship_ids"]),
                         set(trace["evidence"]["relationships"]))


if __name__ == "__main__":
    unittest.main()
