"""Independent RuleSet lifecycle and conflict counterexamples using synthetic notices only."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]
from build_catalog import build  # noqa: E402
from curriculum_assistant.authority import (CORE_SCOPE, RuleSetStore, compare_decisions,
                                            find_rule_candidates, publish_revision,
                                            stage_document, verify_staged_document)  # noqa: E402
from curriculum_assistant.engine import execute  # noqa: E402
from curriculum_assistant.graph import Graph  # noqa: E402
from curriculum_assistant.verifier import verify_payload  # noqa: E402


class OfficialVersionCases(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.core = build()
        cls.student = json.loads((ROOT / "tests/fixtures/core_eligible_synthetic.json").read_text(
            encoding="utf-8"))["student_state"]

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.source = self.directory / "TEST_FIXTURE_notice.txt"
        self.source.write_text("TEST FIXTURE ONLY: synthetic official notice for RuleSet lifecycle tests.\n",
                               encoding="utf-8")
        staged = stage_document(self.source, document_id="TEST-FIXTURE-NOTICE-V2",
                                title="TEST FIXTURE synthetic notice", document_type="OFFICIAL_NOTICE",
                                authority_status="AUTHORITATIVE", effective_from="2026-09-29")
        self.staged = staged
        self.document = verify_staged_document(staged, authority_evidence="TEST_FIXTURE:synthetic authority review")
        self.locator = {"id": "TEST-FIXTURE-LOCATOR", "source_document_id": self.document["document_id"],
                        "source_hash": self.document["source_hash"], "pdf_page_start": None,
                        "title": "TEST FIXTURE", "table_section_note": "synthetic test notice",
                        "verification": "TEST_FIXTURE", "verification_status": "VERIFIED"}

    def relation(self, kind: str, scope: dict | None = None) -> dict:
        return {"relation_type": kind, "source_document_id": self.document["document_id"],
                "target_document_id": "CURRICULUM-2026", "affected_scope": scope or CORE_SCOPE,
                "verification_status": "VERIFIED", "source_refs": [self.locator["id"]],
                "revision_basis": "TEST_FIXTURE: explicit amendment clause" if kind in {"OVERRIDES", "SUPERSEDES"} else None}

    def full_rule_scope(self, rid: str) -> dict:
        return deepcopy(next(r for r in self.core["requirements"] if r["rule_id"] == rid)["effective_scope"])

    def revise(self, kind: str | None = None, changes: list[dict] | None = None,
               scope: dict | None = None, relations: list[dict] | None = None) -> dict:
        return publish_revision(self.core, self.document, document_scope=scope or CORE_SCOPE,
                                relations=relations if relations is not None else ([self.relation(kind)] if kind else []),
                                new_locators=[self.locator], changes=changes or [],
                                created_at="TEST_FIXTURE:2026-09-29")

    def decide(self, catalog: dict, student: dict | None = None) -> dict:
        graph = Graph(Path(":memory:"), catalog)
        try:
            payload = execute(graph, student or self.student, {"intent": "GRADUATION_STATUS"})
            verify_payload(payload)
            return payload
        finally:
            graph.close()

    def test_core_pdf_is_only_official_document_and_v1_is_pinned(self):
        result = self.decide(self.core)
        decision = result["decision"]
        self.assertEqual("ELIGIBLE_PDF", decision["graduation_outcome"])
        self.assertEqual(1, decision["ruleset_version"])
        self.assertEqual(["CURRICULUM-2026"], self.core["authoritative_document_set"]["included_documents"])
        self.assertEqual(self.core["source_sha256"], self.core["authoritative_documents"][0]["source_hash"])
        self.assertIsNone(self.core["authoritative_documents"][0]["issuer"])
        self.assertEqual(len(self.core["requirements"]), len(decision["applicable_rule_ids"]) + 1)

    def test_extracted_text_only_suggests_unverified_rule_candidates(self):
        candidate = deepcopy(self.staged)
        candidate["extracted_text"] = "TEST FIXTURE: 졸업 요건과 논문 조건을 명시한 가상 공문"
        related = find_rule_candidates(candidate, self.core)
        self.assertTrue(related)
        self.assertTrue(all(item["candidate_status"] == "UNVERIFIED"
                            and item["relation_type"] is None for item in related))
        self.assertEqual("VERIFIED", next(r for r in self.core["requirements"]
                                           if r["rule_id"] == "R-GRAD-2026-THESIS-PASSED")["verification_status"])

    def test_unrelated_official_document_creates_v2_without_changing_core_outcome(self):
        unrelated = {"department_id": "DEPT-OTHER", "credit_policy_year": 2026,
                     "catalog_year": 2026, "program_types": ["SINGLE"]}
        revised = self.revise(scope=unrelated)
        before, after = self.decide(self.core), self.decide(revised)
        self.assertEqual(before["decision"]["graduation_outcome"], after["decision"]["graduation_outcome"])
        self.assertEqual(before["credited_amount"], after["credited_amount"])
        self.assertEqual(2, after["decision"]["ruleset_version"])

    def test_supplement_keeps_old_rule_and_adds_new_requirement(self):
        rid = "TEST-FIXTURE-NEW-EVIDENCE"
        rule = {"rule_id": rid, "rule_type": "REQUIRED_EVIDENCE", "evidence_key": "synthetic_notice_passed",
                "department_id": CORE_SCOPE["department_id"], "credit_policy_year": 2026,
                "program_types": ["SINGLE"], "verification_status": "VERIFIED",
                "source_refs": [self.locator["id"]]}
        revised = self.revise("SUPPLEMENTS", [{"change_type": "ADD", "rule_id": rid,
                                               "effective_scope": CORE_SCOPE, "rule": rule}])
        result = self.decide(revised)
        self.assertIn(rid, revised["curriculum_ruleset"]["included_rule_ids"])
        self.assertEqual("UNKNOWN", result["decision"]["graduation_outcome"])
        self.assertEqual("NEEDS_INFORMATION", next(r["status"] for r in result["requirement_results"] if r["rule_id"] == rid))
        student = deepcopy(self.student)
        student["official_outcomes"]["synthetic_notice_passed"] = {
            "value": True, "verification_status": "VERIFIED", "evidence_id": "TEST-FIXTURE-OUTCOME"}
        self.assertEqual("ELIGIBLE_PDF", self.decide(revised, student)["decision"]["graduation_outcome"])

    def test_clarification_preserves_value_and_extends_document_provenance(self):
        rid = "R-GRAD-2026-TOTAL-CREDITS"
        scope = self.full_rule_scope(rid)
        revised = self.revise(changes=[{"change_type": "CLARIFY", "rule_id": rid,
                                        "additional_source_refs": [self.locator["id"]]}],
                              scope=scope, relations=[self.relation("CLARIFIES", scope)])
        old = next(r for r in self.core["requirements"] if r["rule_id"] == rid)
        new = next(r for r in revised["requirements"] if r["rule_id"] == rid)
        self.assertEqual(old["required_value"], new["required_value"])
        self.assertEqual(2, new["rule_version"])
        self.assertEqual({"CURRICULUM-2026", self.document["document_id"]}, set(new["source_documents"]))
        result = self.decide(revised)
        self.assertEqual("ELIGIBLE_PDF", result["decision"]["graduation_outcome"])
        self.assertIn(self.locator["id"], result["evidence"]["source_locators"])

    def test_verified_override_only_changes_v2(self):
        rid = "R-GRAD-2026-TOTAL-CREDITS"
        scope = self.full_rule_scope(rid)
        revised = self.revise(changes=[{"change_type": "OVERRIDE", "rule_id": rid,
                                        "replacement": {"required_value": 131,
                                                        "source_refs": [self.locator["id"]]}}],
                              scope=scope, relations=[self.relation("OVERRIDES", scope)])
        before, after = self.decide(self.core), self.decide(revised)
        self.assertEqual("ELIGIBLE_PDF", before["decision"]["graduation_outcome"])
        self.assertEqual("NOT_ELIGIBLE_PDF", after["decision"]["graduation_outcome"])
        self.assertEqual(130, before["credited_amount"]["total"])
        self.assertEqual(130, after["credited_amount"]["total"])
        self.assertEqual("R-GRAD-2026-TOTAL-CREDITS@v1", next(r for r in revised["requirements"]
                         if r["rule_id"] == rid)["supersedes"])
        comparison = compare_decisions(before, after, self.core, revised)
        self.assertIn(rid, comparison["changed_rule_ids"])
        self.assertTrue(any(x["rule_id"] == rid for x in comparison["changed_requirement_results"]))
        self.assertIn(self.document["document_id"], comparison["source_documents_for_changed_rules"][rid])

    def test_issue_date_alone_cannot_override(self):
        relation = self.relation("OVERRIDES")
        relation["revision_basis"] = None
        with self.assertRaisesRegex(ValueError, "revision relation"):
            self.revise(relations=[relation], changes=[{"change_type": "OVERRIDE",
                "rule_id": "R-GRAD-2026-TOTAL-CREDITS",
                "replacement": {"required_value": 131, "source_refs": [self.locator["id"]]}}])

    def test_partial_scope_override_cannot_erase_rule_for_other_students(self):
        with self.assertRaisesRegex(ValueError, "Partial-scope override"):
            self.revise("OVERRIDES", [{"change_type": "OVERRIDE",
                "rule_id": "R-GRAD-2026-TOTAL-CREDITS",
                "replacement": {"required_value": 131, "source_refs": [self.locator["id"]]}}])

    def test_unverified_relation_cannot_publish(self):
        relation = self.relation("CLARIFIES")
        relation["verification_status"] = "UNVERIFIED"
        with self.assertRaisesRegex(ValueError, "verified evidence"):
            self.revise(relations=[relation], changes=[{"change_type": "CLARIFY",
                "rule_id": "R-GRAD-2026-TOTAL-CREDITS",
                "additional_source_refs": [self.locator["id"]]}])

    def test_unverified_locator_cannot_back_a_rule(self):
        locator = deepcopy(self.locator)
        locator["verification_status"] = "UNVERIFIED"
        with self.assertRaisesRegex(ValueError, "evidence locator"):
            publish_revision(self.core, self.document, document_scope=CORE_SCOPE,
                             relations=[], new_locators=[locator], changes=[],
                             created_at="TEST_FIXTURE:2026-09-29")

    def test_relation_must_cite_the_new_document(self):
        relation = self.relation("SUPPLEMENTS")
        relation["source_refs"] = ["CE-CREDITS"]
        with self.assertRaisesRegex(ValueError, "new document evidence"):
            self.revise(relations=[relation])

    def test_new_rule_cannot_claim_verification_with_mismatched_scope(self):
        rid = "TEST-FIXTURE-WRONG-SCOPE"
        rule = {"rule_id": rid, "rule_type": "REQUIRED_EVIDENCE",
                "evidence_key": "synthetic_notice_passed", "department_id": "DEPT-OTHER",
                "credit_policy_year": 2026, "program_types": ["SINGLE"],
                "verification_status": "VERIFIED", "source_refs": [self.locator["id"]]}
        with self.assertRaisesRegex(ValueError, "identity or evaluator"):
            self.revise("SUPPLEMENTS", [{"change_type": "ADD", "rule_id": rid,
                                          "effective_scope": CORE_SCOPE, "rule": rule}])

    def test_supplement_relation_for_another_scope_cannot_add_core_rule(self):
        other = {"department_id": "DEPT-OTHER", "credit_policy_year": 2026,
                 "catalog_year": 2026, "program_types": ["SINGLE"]}
        rule = {"rule_id": "TEST-FIXTURE-OTHER-SCOPE", "rule_type": "REQUIRED_EVIDENCE",
                "evidence_key": "synthetic_notice_passed", "department_id": CORE_SCOPE["department_id"],
                "credit_policy_year": 2026, "program_types": ["SINGLE"],
                "verification_status": "VERIFIED", "source_refs": [self.locator["id"]]}
        with self.assertRaisesRegex(ValueError, "SUPPLEMENTS"):
            self.revise(relations=[self.relation("SUPPLEMENTS", other)],
                        changes=[{"change_type": "ADD", "rule_id": rule["rule_id"],
                                  "effective_scope": CORE_SCOPE, "rule": rule}])

    def test_unresolved_conflict_never_confirms_graduation(self):
        rid = "R-GRAD-2026-TOTAL-CREDITS"
        revised = self.revise("CONFLICTS_WITH", [{"change_type": "CONFLICT", "rule_id": rid,
                                                  "candidate_source_refs": [self.locator["id"]]}])
        result = self.decide(revised)
        self.assertEqual("UNKNOWN", result["decision"]["graduation_outcome"])
        self.assertEqual("NEEDS_INFORMATION", result["decision"]["decision_status"])
        self.assertEqual(1, len(result["authority"]["unresolved_conflicts"]))
        self.assertTrue(any(e["event_type"] == "RULE_CONFLICT" for e in result["execution_trace"]["events"]))

    def test_conflict_preserves_independent_known_shortfall(self):
        rid = "R-GRAD-2026-TOTAL-CREDITS"
        revised = self.revise("CONFLICTS_WITH", [{"change_type": "CONFLICT", "rule_id": rid,
                                                  "candidate_source_refs": [self.locator["id"]]}])
        short = deepcopy(self.student)
        short["course_attempts"] = [a for a in short["course_attempts"] if a["course_id"] != "CDA0163"]
        result = self.decide(revised, short)
        self.assertEqual("UNKNOWN", result["decision"]["graduation_outcome"])
        self.assertIn("UNSATISFIED", {r["status"] for r in result["requirement_results"]})
        self.assertTrue(result["decision"]["unresolved_conflict_ids"])

    def test_unrelated_conflict_scope_does_not_poison_core(self):
        other = {"department_id": CORE_SCOPE["department_id"], "credit_policy_year": 2026,
                 "catalog_year": 2026, "program_types": ["DOUBLE"]}
        revised = self.revise("CONFLICTS_WITH", [{"change_type": "CONFLICT",
            "rule_id": "R-GRAD-2026-TOTAL-CREDITS", "effective_scope": other,
            "candidate_source_refs": [self.locator["id"]]}], scope=other,
            relations=[self.relation("CONFLICTS_WITH", other)])
        self.assertEqual("ELIGIBLE_PDF", self.decide(revised)["decision"]["graduation_outcome"])

    def test_store_keeps_v1_after_v2_activation_and_reproduces_decision(self):
        store = RuleSetStore(self.directory / "snapshots")
        self.assertEqual(1, store.initialize(self.core)["curriculum_ruleset"]["ruleset_version"])
        revised = self.revise()
        store.activate(revised)
        self.assertEqual(2, store.load_active()["curriculum_ruleset"]["ruleset_version"])
        replayed = self.decide(store.load_version(1))
        newer = self.decide(store.load_version(2))
        old_archive = store.archive_decision(replayed)
        new_archive = store.archive_decision(newer)
        self.assertNotEqual(old_archive, new_archive)
        self.assertEqual(1, json.loads(old_archive.read_text(encoding="utf-8"))["decision"]["ruleset_version"])
        self.assertEqual(2, json.loads(new_archive.read_text(encoding="utf-8"))["decision"]["ruleset_version"])
        self.assertEqual(self.decide(self.core)["decision"], replayed["decision"])
        self.assertEqual(1, replayed["decision"]["ruleset_version"])

    def test_store_detects_changed_new_official_source(self):
        store = RuleSetStore(self.directory / "snapshots")
        store.initialize(self.core)
        store.activate(self.revise())
        self.source.write_text("TEST FIXTURE changed after publication", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "missing or changed"):
            store.load_active()

    def test_historical_snapshot_tampering_cannot_replay(self):
        store = RuleSetStore(self.directory / "snapshots")
        store.initialize(self.core)
        path = next(store.directory.glob("ruleset-v1-*.json"))
        edited = json.loads(path.read_text(encoding="utf-8"))
        edited["requirements"][0]["required_value"] = 999
        path.write_text(json.dumps(edited, ensure_ascii=False), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "snapshot hash"):
            store.load_version(1)

    def test_evaluation_only_and_evaluation_directory_are_rejected(self):
        registry = json.loads((ROOT / "evaluation/document_registry.json").read_text(encoding="utf-8"))
        self.assertTrue(all(d["authority_status"] == "EVALUATION_ONLY" for d in registry["documents"]))
        self.assertTrue({d["document_id"] for d in registry["documents"]}.isdisjoint(
            self.core["authoritative_document_set"]["included_documents"]))
        with self.assertRaises(ValueError):
            stage_document(self.source, document_id="TEST-FIXTURE-EVAL", title="TEST FIXTURE",
                           document_type="OTHER", authority_status="EVALUATION_ONLY")
        outside = self.directory / "evaluation" / "reference"
        outside.mkdir(parents=True)
        copy = outside / "TEST_FIXTURE.txt"
        copy.write_text("TEST FIXTURE ONLY", encoding="utf-8")
        with self.assertRaises(ValueError):
            stage_document(copy, document_id="TEST-FIXTURE-SPOOF", title="TEST FIXTURE",
                           document_type="OTHER", authority_status="AUTHORITATIVE")


if __name__ == "__main__":
    unittest.main()
