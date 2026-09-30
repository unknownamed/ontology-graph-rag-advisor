"""Independent red-team cases for the declared 2026 CE single-major core."""
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
from curriculum_assistant.verifier import verify_payload  # noqa: E402


def student() -> dict:
    data = json.loads((ROOT / "tests/fixtures/core_eligible_synthetic.json").read_text(encoding="utf-8"))
    assert data["fixture_notice"].startswith("SYNTHETIC INPUT ONLY")
    return data["student_state"]


def official_residual(credits: int) -> dict:
    return {"record_id": "ACCEPTANCE-FREE-1", "course_id": "EXT9001",
            "source_category": "OTHER_DEPARTMENT_MAJOR", "verification_status": "VERIFIED",
            "recognition_status": "VERIFIED", "evidence_kind": "OFFICIAL_TRANSCRIPT_RECOGNITION",
            "completion_status": "COMPLETED", "earned_credits": credits,
            "evidence_id": "SYNTHETIC-OFFICIAL-RESIDUAL"}


class CoreRedTeam(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = build()
        cls.graph = Graph(Path(":memory:"), cls.catalog)

    @classmethod
    def tearDownClass(cls):
        cls.graph.close()

    def decide(self, state: dict, intent: str = "GRADUATION_STATUS", **fields) -> dict:
        result = execute(self.graph, state, {"intent": intent, **fields})
        verify_payload(result)
        return result

    def test_repeat_and_attempt_order_do_not_change_decision(self):
        base = student()
        second_residual = official_residual(1)
        second_residual.update({"record_id": "ACCEPTANCE-FREE-2", "course_id": "EXT9002",
                                "evidence_id": "SYNTHETIC-OFFICIAL-RESIDUAL-2"})
        base["free_choice_records"] = [official_residual(1), second_residual]
        first = self.decide(base)
        repeated = self.decide(deepcopy(base))
        shuffled = deepcopy(base)
        shuffled["course_attempts"].reverse()
        shuffled["free_choice_records"].reverse()
        reordered = self.decide(shuffled)
        for key in ("decision", "requirement_results", "credited_amount", "missing_amount",
                    "missing_courses", "needs_information", "evidence", "execution_trace", "answer_text"):
            with self.subTest(key=key):
                self.assertEqual(first[key], repeated[key])
                self.assertEqual(first[key], reordered[key])

    def test_duplicate_unknown_course_and_missing_student_field(self):
        base = student()
        repeated = deepcopy(base)
        repeated["course_attempts"].append(deepcopy(repeated["course_attempts"][0]))
        exact_duplicate = self.decide(repeated)
        self.assertEqual(130, exact_duplicate["credited_amount"]["total"])
        repeated_code = deepcopy(base)
        new_attempt = deepcopy(repeated_code["course_attempts"][0])
        new_attempt.update({"attempt_id": "NEW-RETAKE", "evidence_id": "NEW-RETAKE-EVIDENCE"})
        repeated_code["course_attempts"].append(new_attempt)
        ambiguous_repeat = self.decide(repeated_code)
        self.assertEqual("UNKNOWN", ambiguous_repeat["decision"]["graduation_outcome"])
        unknown = deepcopy(base)
        unknown["course_attempts"].append({"attempt_id": "BAD-CODE", "course_id": "CDA9999",
                                           "completion_status": "COMPLETED", "verification_status": "VERIFIED",
                                           "evidence_id": "SYNTHETIC-BAD-CODE"})
        self.assertEqual("UNKNOWN", self.decide(unknown)["decision"]["graduation_outcome"])
        malformed = self.decide(base, "COURSE_LOOKUP", course_id="CDA0143; DROP TABLE nodes")
        self.assertEqual("NOT_FOUND", malformed["decision"]["lookup_status"])
        missing = deepcopy(base)
        missing.pop("department_id")
        with self.assertRaisesRegex(ValueError, "department"):
            self.decide(missing)

    def test_graduation_boundaries_and_independent_requirements(self):
        base = student()
        self.assertEqual("ELIGIBLE_PDF", self.decide(base)["decision"]["graduation_outcome"])
        short = deepcopy(base)
        short["course_attempts"] = [a for a in short["course_attempts"] if a["course_id"] != "CDA0163"]
        self.assertEqual(127, self.decide(short)["credited_amount"]["total"])
        for credits, expected in ((2, "NOT_ELIGIBLE_PDF"), (3, "ELIGIBLE_PDF"), (4, "ELIGIBLE_PDF")):
            with self.subTest(total=127 + credits):
                case = deepcopy(short)
                case["free_choice_records"] = [official_residual(credits)]
                out = self.decide(case)
                self.assertEqual(127 + credits, out["credited_amount"]["total"])
                self.assertEqual(expected, out["decision"]["graduation_outcome"])
        missing_zero_credit = deepcopy(base)
        missing_zero_credit["course_attempts"] = [a for a in missing_zero_credit["course_attempts"]
                                                  if a["course_id"] != "CDA0034"]
        outcome = self.decide(missing_zero_credit)
        self.assertEqual(130, outcome["credited_amount"]["total"])
        self.assertEqual("NOT_ELIGIBLE_PDF", outcome["decision"]["graduation_outcome"])
        no_evidence = deepcopy(base)
        no_evidence["official_outcomes"]["graduation_certification_passed"].pop("evidence_id")
        self.assertEqual("UNKNOWN", self.decide(no_evidence)["decision"]["graduation_outcome"])
        outside = deepcopy(base)
        outside["program_type"] = "DOUBLE"
        self.assertEqual("UNKNOWN", self.decide(outside)["decision"]["graduation_outcome"])

    def test_repeated_simulation_preserves_actual_record(self):
        base = student()
        base["course_attempts"] = [a for a in base["course_attempts"] if a["course_id"] != "CDA0163"]
        frozen = deepcopy(base)
        actual_before = self.decide(base)
        first = self.decide(base, "WHAT_IF", course_id="CDA0163", assumed_completion="SUCCESS")
        second = self.decide(base, "WHAT_IF", course_id="CDA0163", assumed_completion="SUCCESS")
        actual_after = self.decide(base)
        self.assertEqual(frozen, base)
        self.assertEqual(actual_before["decision"], actual_after["decision"])
        self.assertEqual(first["scenario_decision"], second["scenario_decision"])
        self.assertEqual(127, first["credited_amount"]["total"])
        self.assertEqual(130, first["scenario_decision"]["credited_amount"]["total"])

    def test_zero_credit_simulation_explains_required_course_change(self):
        base = student()
        base["course_attempts"] = [a for a in base["course_attempts"] if a["course_id"] != "CDA0034"]
        result = self.decide(base, "WHAT_IF", course_id="CDA0034", assumed_completion="SUCCESS")
        self.assertEqual(130, result["credited_amount"]["total"])
        self.assertEqual(130, result["scenario_decision"]["credited_amount"]["total"])
        rule_id = "R-CE-2026-REQUIRED-COURSES"
        self.assertEqual("UNSATISFIED", next(r for r in result["requirement_results"]
                                              if r["rule_id"] == rule_id)["status"])
        self.assertEqual("SATISFIED", next(r for r in result["scenario_decision"]["requirement_results"]
                                            if r["rule_id"] == rule_id)["status"])
        self.assertIn("전공필수 지정 과목 미충족→충족", result["answer_text"])

    def test_new_korean_phrasings_and_context(self):
        cases = [
            ("고 자 구는 전필이에요?", "COURSE_LOOKUP", "CDA0143", None),
            ("컴퓨터구조오 이수 구분이 뭐야?", "COURSE_LOOKUP", "CDA0016", None),
            ("자 료 구 조 는 무 슨 영 역?", "COURSE_LOOKUP", "CDA0008", None),
            ("나 지금 전공 몇 점 채운 거임?", "CREDIT_SUMMARY", None, "MAJOR_TOTAL"),
            ("지금 인정되는 전공 점수 알려줘", "CREDIT_SUMMARY", None, "MAJOR_TOTAL"),
            ("전공 학점 얼마나 인정돼?", "CREDIT_SUMMARY", None, "MAJOR_TOTAL"),
            ("졸업될까? 전필 빠진 것도 같이 알려줘", "GRADUATION_STATUS", None, None),
        ]
        for question, intent, code, area in cases:
            with self.subTest(question=question):
                parsed = interpret(question, self.catalog)
                self.assertEqual("RESOLVED", parsed["interpretation_status"])
                query = parsed["structured_query"]
                self.assertEqual(intent, query["intent"])
                if code:
                    self.assertEqual(code, query["course_id"])
                if area:
                    self.assertEqual(area, query["area"])
        initial = interpret("자 료 구 조 는 무 슨 영 역?", self.catalog)
        followup = interpret("그 과목 더 들으면 전공 쪽에 뭐 달라져?", self.catalog, initial["context"])
        self.assertEqual({"intent": "WHAT_IF", "course_id": "CDA0008", "conversation_reference": "last_course_id", "assumed_completion": "SUCCESS"},
                         followup["structured_query"])

    def test_three_distinct_answer_to_pdf_chains(self):
        import pdfplumber

        partial = student()
        partial["course_attempts"] = [a for a in partial["course_attempts"]
                                      if a["course_id"] in {"CDA0143", "CDA0163"}]
        partial["completion_coverage"] = "PARTIAL"
        missing_required = student()
        missing_required["course_attempts"] = [a for a in missing_required["course_attempts"]
                                                if a["course_id"] != "CDA0034"]
        scenarios = [
            ("전공 지금까지 몇 점 쌓였지?", partial, "R-CE-2026-MAJOR-REQUIRED-CREDITS"),
            ("필수 빠진 거 뭐야?", missing_required, "R-CE-2026-REQUIRED-COURSES"),
            ("졸업될까?", student(), "R-GRAD-2026-TOTAL-CREDITS"),
        ]
        with pdfplumber.open(ROOT / "docs/curriculum/2026년도 교육과정.pdf") as pdf:
            for question, state, rule_id in scenarios:
                with self.subTest(question=question):
                    parsed = interpret(question, self.catalog)
                    self.assertEqual("RESOLVED", parsed["interpretation_status"])
                    payload = self.decide(state, **parsed["structured_query"])
                    result = next(r for r in payload["requirement_results"] if r["rule_id"] == rule_id)
                    rule = next(r for r in payload["evidence"]["rules"] if r["rule_id"] == rule_id)
                    self.assertTrue(result["used_fact_ids"])
                    self.assertIn(rule["relationship_id"], result["used_relationship_ids"])
                    returned = {item for event in payload["execution_trace"]["events"]
                                if event["event_type"] == "GRAPH_QUERY" for item in event["returned_ids"]}
                    self.assertIn(rule["relationship_id"], returned)
                    self.assertTrue(any(event["event_type"] == "RULE_EVALUATION"
                                        and event["event_id"] in result["execution_event_ids"]
                                        and event["rule_id"] == rule_id for event in payload["execution_trace"]["events"]))
                    for source_id in result["source_refs"]:
                        location = payload["evidence"]["source_locators"][source_id]
                        self.assertTrue(pdf.pages[location["pdf_page_start"] - 1].extract_text())
                    for fact_id in result["used_fact_ids"][:2]:
                        fact = next(f for f in payload["evidence"]["facts"] if f["fact_id"] == fact_id)
                        self.assertIn(fact["course_id"], pdf.pages[fact["source"]["pdf_page"] - 1].extract_text())

    def test_core_credit_thresholds_match_pdf_rows(self):
        import pdfplumber

        with pdfplumber.open(ROOT / "docs/curriculum/2026년도 교육과정.pdf") as pdf:
            department_row = " ".join((pdf.pages[260].extract_text() or "").split())
            graduation_row = " ".join((pdf.pages[576].extract_text() or "").split())
        self.assertIn("9 12 13 34 21 24 33 78 18 130", department_row)
        self.assertIn("컴퓨터공 2026 9 12 13 34 21 24 45 33 78 18 130", graduation_row)
        rules = {r["rule_id"]: r for r in self.graph.query("FETCH_REQUIREMENTS", curriculum_id="CURRICULUM-CE-2026")}
        self.assertEqual(130, rules["R-GRAD-2026-TOTAL-CREDITS"]["required_value"])
        self.assertEqual(78, rules["R-CE-2026-MAJOR-TOTAL-CREDITS"]["required_value"])
        self.assertEqual(21, rules["R-CE-2026-MAJOR-REQUIRED-CREDITS"]["required_value"])
        self.assertEqual(33, rules["R-CE-2026-ADVANCED-CREDITS"]["required_value"])
