from __future__ import annotations

import json
import sys
import unittest
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
from build_catalog import build  # noqa: E402
from curriculum_assistant.engine import execute  # noqa: E402
from curriculum_assistant.graph import Graph  # noqa: E402


def student(codes=(), *, coverage="COMPLETE", year=2026, program="SINGLE"):
    return {"student_state_id": "TEST-STATE-1", "student_id": "SYNTHETIC",
            "admission_year": 2026, "department_id": "DEPT-COMPUTER-ENGINEERING",
            "credit_policy_year": year, "catalog_year": year,
            "applicability_status": "VERIFIED", "program_type": program,
            "completion_coverage": coverage,
            "course_attempts": [{"attempt_id": f"A-{i}", "course_id": code,
                                 "completion_status": "COMPLETED", "verification_status": "VERIFIED",
                                 "evidence_id": f"TEST-EVIDENCE-{i}", "earned_credits": None}
                                for i, code in enumerate(codes)]}


def rule(payload, suffix):
    return next(r for r in payload["decision"]["requirement_results"] if r["rule_id"].endswith(suffix))


class BuilderCases(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = build()
        cls.graph = Graph(Path(":memory:"), cls.catalog)

    @classmethod
    def tearDownClass(cls):
        cls.graph.close()

    def run_query(self, state, intent="CREDIT_SUMMARY", **query):
        return execute(self.graph, state, {"intent": intent, **query})

    def test_catalog_source_and_graph_counts(self):
        major = [c for c in self.catalog["courses"] if c["course_id"].startswith("CDA")]
        self.assertEqual(43, len(major))
        self.assertEqual(280, len(self.catalog["courses"]) - len(major))
        self.assertEqual(9, sum(c["classification"] == "MAJOR_REQUIRED" for c in major))
        self.assertEqual(144, sum(c["catalog_credits"] for c in major))
        self.assertEqual(3, sum(c["minor_required"] for c in major))
        self.assertEqual(323, self.graph.db.execute("SELECT count(*) FROM nodes WHERE kind='Course'").fetchone()[0])

    def test_course_lookup_source_and_relationships(self):
        out = self.run_query(student(), "COURSE_LOOKUP", course_id="CDA0143")
        self.assertEqual("FOUND", out["decision"]["lookup_status"])
        value = out["decision"]["lookup_result"]
        self.assertEqual((3, "MAJOR_REQUIRED", 262), (value["catalog_credits"], value["classification"], value["source"]["pdf_page"]))
        self.assertEqual(3, len(value["relationship_ids"]))
        self.assertEqual(3, len(out["evidence"]["relationship_details"]))
        self.assertIn(value["entry_id"], out["execution_trace"]["events"][1]["returned_ids"])

    def test_exact_boundaries_and_required_zero_credit(self):
        required = [c["course_id"] for c in self.catalog["courses"] if c["classification"] == "MAJOR_REQUIRED"]
        out = self.run_query(student(required))
        self.assertEqual("SATISFIED", rule(out, "REQUIRED-COURSES")["status"])
        self.assertEqual("SATISFIED", rule(out, "REQUIRED-CREDITS")["status"])
        self.assertEqual(21, rule(out, "REQUIRED-CREDITS")["observed"])
        self.assertEqual("UNSATISFIED", rule(out, "ELECTIVE-CREDITS")["status"])
        below = self.run_query(student(required[:-3]))
        self.assertEqual("UNSATISFIED", rule(below, "REQUIRED-CREDITS")["status"])
        self.assertEqual("UNSATISFIED", rule(below, "REQUIRED-COURSES")["status"])

    def test_partial_and_unverified_are_information_not_failure(self):
        state = student(["CDA0143"], coverage="PARTIAL")
        out = self.run_query(state)
        self.assertEqual("NEEDS_INFORMATION", rule(out, "REQUIRED-CREDITS")["status"])
        self.assertIsNone(rule(out, "REQUIRED-CREDITS")["missing_amount"])
        state["completion_coverage"] = "COMPLETE"
        state["course_attempts"][0]["verification_status"] = "UNVERIFIED"
        out = self.run_query(state)
        self.assertEqual("NEEDS_INFORMATION", rule(out, "REQUIRED-CREDITS")["status"])
        self.assertIsNone(out["decision"]["credited_amount"]["total"])

    def test_double_program_not_applicable_and_wrong_version(self):
        out = self.run_query(student([], program="DOUBLE"))
        self.assertEqual("NOT_APPLICABLE", rule(out, "TOTAL-CREDITS")["status"])
        self.assertEqual("UNSATISFIED", rule(out, "DOUBLE-MAJOR-MINIMUM")["status"])
        wrong = self.run_query(student(["CDA0143"], year=2025))
        self.assertEqual("NEEDS_INFORMATION", wrong["decision"]["decision_status"])
        self.assertEqual([], wrong["evidence"]["facts"])

    def test_duplicate_record_and_unknown_course(self):
        state = student(["CDA0143"])
        state["course_attempts"].append(deepcopy(state["course_attempts"][0]))
        out = self.run_query(state)
        self.assertEqual(3, out["decision"]["credited_amount"]["confirmed_minimum"])
        self.assertEqual("DUPLICATE_RECORD_ID", out["decision"]["excluded"][0]["reason"])
        state = student(["CDA9999"])
        out = self.run_query(state)
        self.assertEqual("NEEDS_INFORMATION", rule(out, "REQUIRED-CREDITS")["status"])
        self.assertIn("CATALOG_CLASSIFICATION:CDA9999", out["decision"]["needs_information"])

    def test_what_if_is_isolated_and_repeatable(self):
        base = student(["CDA0143"])
        before = deepcopy(base)
        query = {"intent": "WHAT_IF", "course_id": "CDA0163"}
        first = execute(self.graph, base, query)
        again = execute(self.graph, base, query)
        self.assertEqual(before, base)
        self.assertEqual(3, first["decision"]["credited_amount"]["confirmed_minimum"])
        self.assertEqual(6, first["scenario_decision"]["credited_amount"]["confirmed_minimum"])
        self.assertEqual(first["decision"]["canonical_result_hash"], again["decision"]["canonical_result_hash"])
        self.assertEqual(first["execution_trace"], again["execution_trace"])
        base["course_attempts"].append(student(["CDA0016"])["course_attempts"][0] | {"attempt_id": "A-NEW"})
        changed = execute(self.graph, base, query)
        self.assertEqual(6, changed["decision"]["credited_amount"]["confirmed_minimum"])

    def test_graduation_never_eligible_on_partial_manifest(self):
        all_courses = [c["course_id"] for c in self.catalog["courses"] if c["course_id"].startswith("CDA")]
        out = self.run_query(student(all_courses), "GRADUATION_STATUS")
        self.assertEqual("UNKNOWN", out["decision"]["graduation_outcome"])
        self.assertIn("VERIFIED_STUDENT_CATEGORY_AND_EXCEPTIONS", out["decision"]["needs_information"])


class ReviewerCases(BuilderCases):
    """New counterexamples written after reviewing the implementation path."""

    def test_same_course_distinct_attempts_need_repeat_resolution(self):
        state = student(["CDA0143", "CDA0143"])
        out = self.run_query(state)
        self.assertEqual(0, out["decision"]["credited_amount"]["confirmed_minimum"])
        self.assertIn("REPEAT_RESOLUTION:CDA0143", out["decision"]["needs_information"])
        self.assertEqual("NEEDS_INFORMATION", rule(out, "REQUIRED-CREDITS")["status"])

    def test_credit_disagreement_never_uses_catalog_value_silently(self):
        state = student(["CDA0143"])
        state["course_attempts"][0]["earned_credits"] = 6
        out = self.run_query(state)
        self.assertEqual(0, out["decision"]["credited_amount"]["confirmed_minimum"])
        self.assertIn("CREDIT_MISMATCH:A-0", out["decision"]["needs_information"])

    def test_conflicting_same_attempt_id_does_not_select_first_record(self):
        state = student(["CDA0143"])
        conflict = deepcopy(state["course_attempts"][0])
        conflict["course_id"] = "CDA0163"
        state["course_attempts"].append(conflict)
        out = self.run_query(state)
        self.assertEqual(0, out["decision"]["credited_amount"]["confirmed_minimum"])
        self.assertIn("CONFLICTED_ATTEMPT_ID:A-0", out["decision"]["needs_information"])

    def test_2025_admission_with_explicit_2026_policy_is_separate(self):
        state = student(["CDA0143"])
        state["admission_year"] = 2025
        out = self.run_query(state)
        self.assertEqual(3, out["decision"]["credited_amount"]["confirmed_minimum"])

    def test_provenance_chain_uses_executed_graph_relations(self):
        out = self.run_query(student(["CDA0143"]))
        rec = out["decision"]["recognitions"][0]
        returned = {item for event in out["execution_trace"]["events"] if event["event_type"] == "GRAPH_QUERY" for item in event["returned_ids"]}
        self.assertTrue(set(rec["relationship_ids"]).issubset(returned))
        rr = rule(out, "REQUIRED-CREDITS")
        self.assertIn(rec["fact_id"], rr["used_fact_ids"])
        self.assertIn(rec["student_evidence_id"], rr["used_student_evidence_ids"])
        self.assertEqual(out["decision"]["decision_id"], out["execution_trace"]["decision_id"])
        self.assertEqual(out["decision"]["requirement_results"], out["requirement_results"])

    def test_unverified_catalog_row_is_not_credited(self):
        changed = deepcopy(self.catalog)
        next(c for c in changed["courses"] if c["course_id"] == "CDA0143")["verification_status"] = "UNVERIFIED"
        graph = Graph(Path(":memory:"), changed)
        try:
            out = execute(graph, student(["CDA0143"]), {"intent": "CREDIT_SUMMARY"})
            self.assertEqual(0, out["decision"]["credited_amount"]["confirmed_minimum"])
            self.assertIn("CATALOG_VERIFICATION:CDA0143", out["decision"]["needs_information"])
            lookup = execute(graph, student(), {"intent": "COURSE_LOOKUP", "course_id": "CDA0143"})
            self.assertEqual("NEEDS_INFORMATION", lookup["decision"]["lookup_status"])
        finally:
            graph.close()

    def test_decision_hash_remains_valid_after_scenario(self):
        from curriculum_assistant.engine import digest
        out = self.run_query(student(["CDA0143"]), "WHAT_IF", course_id="CDA0163")
        for decision in (out["decision"], out["scenario_decision"]):
            unhashed = {k: v for k, v in decision.items() if k not in {"decision_id", "canonical_result_hash"}}
            self.assertEqual(digest(unhashed), decision["canonical_result_hash"])

    def test_verifier_rejects_invented_relationship(self):
        from curriculum_assistant.verifier import verify_payload
        out = self.run_query(student(["CDA0143"]))
        out["evidence"]["relationships"].append("E-INVENTED")
        with self.assertRaisesRegex(ValueError, "graph edge"):
            verify_payload(out)

    def test_verifier_rejects_credit_event_without_student_evidence(self):
        from curriculum_assistant.verifier import verify_payload
        out = self.run_query(student(["CDA0143"]))
        event = next(e for e in out["execution_trace"]["events"] if e["event_type"] == "CREDIT_RECOGNITION")
        event["input_refs"].remove(out["decision"]["recognitions"][0]["student_evidence_id"])
        with self.assertRaisesRegex(ValueError, "complete execution input"):
            verify_payload(out)


if __name__ == "__main__":
    unittest.main()
