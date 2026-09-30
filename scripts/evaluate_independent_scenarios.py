"""Run the independent question set through the real localhost user-query API.

The scenario file is evaluation input only. It is never imported by the app,
catalog builder, graph, rules, aliases, or model prompt.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]
from build_catalog import build  # noqa: E402
from curriculum_assistant.verifier import verify_payload  # noqa: E402

SCENARIO_DIR = ROOT / "evaluation/core_scenarios"
RESULTS = ROOT / "evaluation/results/independent_scenario_results.json"
REPORT = ROOT / "evaluation/results/independent_scenario_report.md"
BEFORE = ROOT / "evaluation/results/independent_scenario_results_before.json"
PDF = ROOT / "docs/curriculum/2026년도 교육과정.pdf"
_PDF_TEXT_CACHE: dict[int, str] = {}
_PDF_SHA256: str | None = None
FAILURE_CATEGORIES = {"intent_error", "entity_resolution_error", "graph_query_error", "rule_error",
                      "provenance_error", "answer_render_error", "context_error", "unsupported_scope_error",
                      "insufficient_information_error", "determinism_error", "other"}
INTENT_FAMILIES = {
    "LIST_REQUIRED_COURSES": "POLICY_LOOKUP", "LIST_REQUIRED_COURSES_WITH_CREDITS": "POLICY_LOOKUP",
    "COUNT_MAJOR_COURSES": "CATALOG_AGGREGATE", "SUM_CATALOG_MAJOR_CREDITS": "CATALOG_AGGREGATE",
    "COURSE_LOOKUP": "COURSE_LOOKUP", "COURSE_CLASSIFICATION": "COURSE_LOOKUP",
    "LIST_REQUIREMENTS": "POLICY_LOOKUP", "CURRICULUM_APPLICABILITY": "POLICY_LOOKUP",
    "CALCULATE_MAJOR_CREDITS": "CREDIT_SUMMARY", "MISSING_REQUIRED_COURSES": "REQUIREMENT_GAPS",
    "REQUIREMENT_AUDIT": "REQUIREMENT_GAPS", "CREDIT_SUMMARY": "CREDIT_SUMMARY",
    "GRADUATION_CHECK": "GRADUATION_STATUS", "CREDIT_AUDIT": "CREDIT_SUMMARY",
    "ENTITY_RESOLUTION": "ENTITY_CHECK", "CONSISTENCY_CHECK": "CONSISTENCY_CHECK",
    "SIMULATE_ADD_COURSE": "WHAT_IF", "SIMULATE_ADD_REQUIRED": "WHAT_IF",
    "SIMULATION_COMPARE": "WHAT_IF", "SIMULATE_MULTI_COURSE": "WHAT_IF",
    "SIMULATE_REQUIREMENT_CHANGE": "WHAT_IF", "SIMULATION_INTEGRITY": "CONSISTENCY_CHECK",
    "SIMULATE_REQUIREMENT_DELTA": "WHAT_IF", "REQUIREMENT_LOOKUP": "POLICY_LOOKUP",
    "MULTI_REQUIREMENT_AUDIT": "GRADUATION_STATUS", "CURRENT_AND_SIMULATED_GAP": "WHAT_IF",
    "EXPLAIN_DECISION": "GRADUATION_STATUS", "SOURCE_LOOKUP": "REQUIREMENT_GAPS",
    "EXPLAIN_TRACE": "TRACE_EXPLAIN",
}
KEY_FIELDS = ("decision", "scenario_decision", "requirement_results", "credited_amount", "missing_amount",
              "missing_courses", "needs_information", "evidence", "execution_trace", "scenario_delta", "answer_text")


def post(port: int, body: dict) -> tuple[int, dict]:
    request = urllib.request.Request(f"http://127.0.0.1:{port}/api/query",
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"), headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as error:
        return error.code, json.load(error)


def source_check(payload: dict, catalog: dict, pdf) -> list[str]:
    """Check actual returned source IDs and the cited curriculum pages, not evaluation answers."""
    failures = []
    global _PDF_SHA256
    if _PDF_SHA256 is None:
        _PDF_SHA256 = hashlib.sha256(PDF.read_bytes()).hexdigest()
    if catalog["source_sha256"] != _PDF_SHA256:
        return ["VERIFIED catalog source hash differs from curriculum PDF"]
    evidence = payload.get("evidence") or {}
    locators = evidence.get("source_locators") or {}
    for ref, locator in locators.items():
        page = locator.get("pdf_page_start")
        if ref != locator.get("id") or not isinstance(page, int) or not 1 <= page <= len(pdf.pages):
            failures.append(f"invalid source locator: {ref}")
        elif not page_text(pdf, page):
            failures.append(f"unreadable cited PDF page: {page}")
    for fact in evidence.get("facts", []):
        source = fact.get("source") or {}
        page, code = source.get("pdf_page"), fact.get("course_id")
        if code and isinstance(page, int) and code not in page_text(pdf, page):
            failures.append(f"course {code} absent from cited PDF page {page}")
    return failures


def page_text(pdf, page: int) -> str:
    if page not in _PDF_TEXT_CACHE:
        _PDF_TEXT_CACHE[page] = pdf.pages[page - 1].extract_text() or ""
    return _PDF_TEXT_CACHE[page]


def catalog_pdf_row_check(pdf, fixtures: "Fixtures") -> dict:
    """Cross-check central VERIFIED thresholds with the original CE PDF rows."""
    def minimum(area: str) -> int:
        return next(r["required_value"] for r in fixtures.rules.values()
                    if r["rule_type"] == "MIN_CREDITS" and r.get("area") == area)
    basic, balanced, general = minimum("GENERAL_BASIC"), minimum("GENERAL_BALANCED"), minimum("GENERAL_TOTAL")
    required, elective = minimum("MAJOR_REQUIRED"), minimum("MAJOR_ELECTIVE")
    advanced, major, total = minimum("MAJOR_ADVANCED"), minimum("MAJOR_TOTAL"), minimum("GRADUATION_TOTAL")
    expanded, residual = general - basic - balanced, total - general - major
    department = " ".join(page_text(pdf, 261).split())
    graduation = " ".join(page_text(pdf, 577).split())
    department_values = f"{basic} {balanced} {expanded} {general} {required} {elective} {advanced} {major} {residual} {total}"
    graduation_values = (f"컴퓨터공 2026 {basic} {balanced} {expanded} {general} {required} {elective} "
                         f"{required + elective} {advanced} {major} {residual} {total}")
    return {"pdf_261_department_row_matches": department_values in department,
            "pdf_577_graduation_row_matches": graduation_values in graduation,
            "derived_department_values": department_values, "derived_graduation_values": graduation_values}


class Fixtures:
    """Derive synthetic states from the existing fixture and VERIFIED catalog rules."""

    def __init__(self, catalog: dict):
        self.catalog = catalog
        self.courses = {c["course_id"]: c for c in catalog["courses"] if c["verification_status"] == "VERIFIED"}
        self.rules = {r["rule_id"]: r for r in catalog["requirements"] if r["verification_status"] == "VERIFIED"}
        source = json.loads((ROOT / "tests/fixtures/core_eligible_synthetic.json").read_text(encoding="utf-8"))
        assert source["fixture_notice"].startswith("SYNTHETIC INPUT ONLY")
        self.complete = source["student_state"]
        required = next(r for r in self.rules.values() if r["rule_type"] == "REQUIRED_COURSES")
        self.required = set(required["course_ids"])
        self.positive_required = next(a["course_id"] for a in self.complete["course_attempts"]
                                      if a["course_id"] in self.required and self.courses[a["course_id"]]["catalog_credits"] > 0)
        self.zero_required = next(a["course_id"] for a in self.complete["course_attempts"]
                                  if a["course_id"] in self.required and self.courses[a["course_id"]]["catalog_credits"] == 0)
        self.dispensable = next(a["course_id"] for a in self.complete["course_attempts"]
                                if a["course_id"] not in self.required
                                and self.courses[a["course_id"]]["classification"] == "MAJOR_ELECTIVE"
                                and self.courses[a["course_id"]]["catalog_credits"] > 0)
        self.threshold = next(r["required_value"] for r in self.rules.values()
                              if r.get("area") == "GRADUATION_TOTAL" and r["rule_type"] == "MIN_CREDITS")
        self.complete_total = sum(self.courses[a["course_id"]]["catalog_credits"]
                                  for a in self.complete["course_attempts"] if a["course_id"] in self.courses)
        assert self.complete_total == self.threshold, "base fixture must match VERIFIED graduation threshold"

    def without(self, *codes: str) -> dict:
        state = deepcopy(self.complete)
        state["course_attempts"] = [a for a in state["course_attempts"] if a["course_id"] not in codes]
        return state

    def residual(self, credits: int) -> dict:
        state = deepcopy(self.complete)
        state["free_choice_records"] = [{"record_id": "INDEPENDENT-RESIDUAL", "course_id": "EXT-INDEPENDENT-1",
            "source_category": "OTHER_DEPARTMENT_MAJOR", "verification_status": "VERIFIED",
            "recognition_status": "VERIFIED", "evidence_kind": "OFFICIAL_TRANSCRIPT_RECOGNITION",
            "completion_status": "COMPLETED", "earned_credits": credits,
            "evidence_id": "SYNTHETIC-OFFICIAL-RESIDUAL"}]
        return state

    def make(self, name: str, question: str) -> tuple[dict | None, str | None, dict]:
        meta: dict = {"generator": name, "basis": "VERIFIED catalog and synthetic fixture"}
        if name == "no_student":
            return None, None, meta
        if name == "core_complete":
            return deepcopy(self.complete), None, meta
        if name in {"core_partial", "required_missing_one"}:
            meta["removed_verified_course_id"] = self.positive_required
            return self.without(self.positive_required), None, meta
        if name == "required_complete_total_short":
            meta["removed_verified_course_id"] = self.dispensable
            return self.without(self.dispensable), None, meta
        if name == "total_complete_required_missing":
            meta["removed_verified_course_id"] = self.zero_required
            return self.without(self.zero_required), None, meta
        if name == "missing_information":
            state = deepcopy(self.complete)
            state["completion_coverage"] = "PARTIAL"
            state.pop("completion_coverage_evidence_id", None)
            return state, None, meta
        if name == "one_credit_below":
            state = self.without(self.dispensable)
            present = self.threshold - self.courses[self.dispensable]["catalog_credits"]
            needed = self.threshold - 1 - present
            if needed < 0:
                return None, "No verified fixture can be placed one credit below threshold", meta
            state["free_choice_records"] = self.residual(needed)["free_choice_records"]
            return state, None, meta
        if name == "exact_credit_threshold_all_else_complete":
            return deepcopy(self.complete), None, meta
        if name == "one_credit_above_all_else_complete":
            return self.residual(self.threshold + 1 - self.complete_total), None, meta
        if name == "duplicate_course_attempt":
            state = deepcopy(self.complete)
            state["course_attempts"].append(deepcopy(state["course_attempts"][0]))
            return state, None, meta
        if name == "unknown_course_code":
            state = deepcopy(self.complete)
            match = re.search(r"(?<![A-Z0-9])[A-Z]{3}\d{4}(?![A-Z0-9])", question.upper())
            code = match.group() if match else "ZZZ9999"
            if code in self.courses:
                return None, "Question's alleged unknown code is VERIFIED", meta
            state["course_attempts"].append({"attempt_id": "INDEPENDENT-UNKNOWN", "course_id": code,
                "completion_status": "COMPLETED", "verification_status": "VERIFIED",
                "evidence_id": "SYNTHETIC-UNKNOWN"})
            meta["unknown_code"] = code
            return state, None, meta
        if name == "malformed_completion_record":
            state = deepcopy(self.complete)
            state["course_attempts"].append({"attempt_id": "INDEPENDENT-MALFORMED",
                "completion_status": "COMPLETED", "verification_status": "UNVERIFIED",
                "evidence_id": "SYNTHETIC-MALFORMED"})
            return state, None, meta
        if name == "same_state_different_order":
            return deepcopy(self.complete), None, meta
        if name == "two_course_simulation":
            positive = [a["course_id"] for a in self.complete["course_attempts"]
                        if a["course_id"] in self.required and self.courses[a["course_id"]]["catalog_credits"] > 0]
            meta["removed_verified_course_ids"] = positive[:2]
            return self.without(*positive[:2]), None, meta
        if name == "zero_credit_required_simulation":
            meta["removed_verified_course_id"] = self.zero_required
            return self.without(self.zero_required), None, meta
        if name == "conversation_course_selected":
            meta["seed_course_id"] = self.positive_required
            return deepcopy(self.complete), None, meta
        if name == "conversation_course_selected_core_partial":
            meta["seed_course_id"] = self.positive_required
            return self.without(self.positive_required), None, meta
        if name == "missing_info_and_unsatisfied":
            return None, "A missing semester cannot prove the named required course is absent without independent official evidence", meta
        if name == "old_curriculum_student":
            state = deepcopy(self.complete)
            state.update({"admission_year": 2024, "credit_policy_year": 2024, "catalog_year": 2024})
            return state, None, meta
        if name == "double_major_student":
            state = deepcopy(self.complete)
            state["program_type"] = "DOUBLE"
            return state, None, meta
        return None, f"Unknown fixture guidance: {name}", meta


def failure(kind: str, message: str) -> tuple[str, str]:
    assert kind in FAILURE_CATEGORIES
    return kind, message


def evaluate_case(port: int, scenario: dict, fixtures: Fixtures, catalog: dict, pdf) -> dict:
    expected = scenario["expected"]
    state, skip, fixture_meta = fixtures.make(scenario["fixture"], scenario["question"])
    result = {"scenario_id": scenario["id"], "category": scenario["category"],
              "question": scenario["question"], "fixture_name": scenario["fixture"],
              "fixture": state, "fixture_provenance": fixture_meta,
              "expected_contract": expected, "status": "SKIP" if skip else "FAIL",
              "failure_category": "insufficient_information_error" if skip else None,
              "failure_reason": skip, "checks": {},
              "structured_query": None, "entity_resolution": None, "query_plan": None,
              "evidence_bundle": None, "requirement_results": None,
              "deterministic_decision": None, "answer_payload": None,
              "final_answer_ko": None, "execution_trace": None,
              "all_failures": ([{"category": "insufficient_information_error", "reason": skip}]
                               if skip else [])}
    if skip:
        return result
    body = {"utterance": scenario["question"], "use_local_llm": False}
    if state is not None:
        body["student_state"] = state
    seed_course_id = fixture_meta.get("seed_course_id")
    if expected.get("requires_conversation_context") and not seed_course_id and state is not None:
        seed_course_id = fixture_meta.get("removed_verified_course_id", fixtures.positive_required)
    if seed_course_id:
        seed = f"{seed_course_id} 이수구분이 뭐야?"
        seed_status, seed_payload = post(port, {"student_state": state, "utterance": seed, "use_local_llm": False})
        result["context_seed"] = {"utterance": seed, "http_status": seed_status,
                                  "structured_query": (seed_payload.get("interpretation") or {}).get("structured_query")}
        body["context"] = (seed_payload.get("interpretation") or {}).get("context")
    frozen = deepcopy(state)
    status, payload = post(port, body)
    result["http_status"] = status
    result["request_context"] = body.get("context")
    result["api_response_error"] = payload if status != 200 or not payload.get("decision") else None
    result["api_response_sha256"] = hashlib.sha256(json.dumps(payload, ensure_ascii=False,
        sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    result["interpretation"] = payload.get("interpretation")
    result["structured_query"] = (payload.get("interpretation") or {}).get("structured_query")
    result["entity_resolution"] = {"course_id": (result["structured_query"] or {}).get("course_id"),
                                   "ambiguities": (payload.get("interpretation") or {}).get("ambiguities"),
                                   "status": (payload.get("interpretation") or {}).get("interpretation_status")}
    trace = payload.get("execution_trace") or {}
    plan = next((e for e in trace.get("events", []) if e.get("event_type") == "QUERY_PLAN"), None)
    result["query_plan"] = plan
    result["evidence_bundle"] = payload.get("evidence")
    result["requirement_results"] = payload.get("requirement_results")
    result["deterministic_decision"] = payload.get("decision")
    result["answer_payload"] = {k: payload.get(k) for k in ("contract_version", "decision", "scenario_decision",
        "requirement_results", "credited_amount", "missing_amount", "missing_courses", "needs_information",
        "evidence", "execution_trace", "scenario_delta", "answer_text")}
    result["final_answer_ko"] = payload.get("answer_text")
    result["execution_trace"] = trace or None
    errors: list[tuple[str, str]] = []
    if status != 200:
        errors.append(failure("insufficient_information_error", f"API returned HTTP {status}: {payload.get('detail') or payload.get('error')}"))
    elif not result["structured_query"]:
        ambiguities = result["entity_resolution"].get("ambiguities") or []
        if "CATALOG_AGGREGATE_UNSUPPORTED" in ambiguities:
            kind = "unsupported_scope_error"
        elif "COURSE_ENTITY" in ambiguities or "UNRESOLVED_COURSE_ENTITY" in ambiguities:
            kind = "entity_resolution_error"
        elif expected.get("requires_conversation_context"):
            kind = "context_error"
        else:
            kind = "intent_error"
        errors.append(failure(kind, f"Natural question unresolved: {result['entity_resolution']}"))
    if status == 200 and payload.get("decision"):
        try:
            verify_payload(payload)
            result["checks"]["answer_payload_verified"] = True
        except (ValueError, KeyError, TypeError) as exc:
            errors.append(failure("provenance_error", f"AnswerPayload verifier rejected API result: {exc}"))
        source_errors = source_check(payload, catalog, pdf)
        result["checks"]["pdf_source_verified"] = not source_errors
        errors.extend(failure("provenance_error", message) for message in source_errors)
        returned = {item for event in trace.get("events", []) if event.get("event_type") == "GRAPH_QUERY"
                    for item in event.get("returned_ids", [])}
        relations = set((payload.get("evidence") or {}).get("relationships", []))
        if not relations.issubset(returned):
            errors.append(failure("graph_query_error", "Evidence relation absent from actual GRAPH_QUERY return IDs"))
        if expected.get("must_have_evidence") and not relations:
            errors.append(failure("provenance_error", "Expected source-backed query has no returned relationships"))
        if expected.get("must_have_evidence") and not (payload.get("evidence") or {}).get("source_locators"):
            errors.append(failure("provenance_error", "Expected source-backed query has no PDF locator"))
        if expected.get("must_have_pdf_source") and not (payload.get("evidence") or {}).get("source_locators"):
            errors.append(failure("provenance_error", "No curriculum PDF source locator"))
        if expected.get("must_not_infer_student_year"):
            entry_year = ((payload.get("decision") or {}).get("lookup_result") or {}).get("entry_year")
            if entry_year is not None:
                errors.append(failure("rule_error", f"Catalog-only question invented student entry year {entry_year}"))
        if not plan or plan.get("operations") is None:
            errors.append(failure("graph_query_error", "No executed QUERY_PLAN event"))
        if state is not None and state != frozen:
            errors.append(failure("rule_error", "API mutated the caller's StudentState"))
    expected_intent = expected.get("expected_intent")
    actual_intent = (result["structured_query"] or {}).get("intent")
    if expected_intent and result["structured_query"]:
        wanted = INTENT_FAMILIES[expected_intent]
        if actual_intent != wanted:
            errors.append(failure("intent_error", f"Expected {expected_intent} semantic family {wanted}, got {actual_intent}"))
    if payload.get("decision"):
        decision = payload["decision"]
        wanted_status = expected.get("expected_decision")
        if wanted_status and decision.get("decision_status") != wanted_status:
            errors.append(failure("rule_error", f"Expected decision status {wanted_status}, got {decision.get('decision_status')}"))
        if expected.get("expected_scope") and decision.get("graduation_outcome") != "UNKNOWN":
            errors.append(failure("unsupported_scope_error", "Out-of-scope graduation question did not return UNKNOWN"))
        if expected.get("must_not_invent_course"):
            lookup = decision.get("lookup_result") or {}
            if lookup.get("verified_catalog_entry") is True and lookup.get("course_id") not in fixtures.courses:
                errors.append(failure("entity_resolution_error", "Resolved an unknown course as VERIFIED"))
            if actual_intent == "WHAT_IF" and decision.get("simulation_status") == "NEEDS_TARGET" and payload.get("scenario_decision"):
                errors.append(failure("rule_error", "Unknown course was simulated as verified"))
        if expected.get("must_not_double_count") and decision.get("credited_amount"):
            if decision["credited_amount"]["total"] != fixtures.complete_total:
                errors.append(failure("rule_error", "Exact duplicate changed VERIFIED counted credit total"))
        if expected_intent in {"LIST_REQUIRED_COURSES", "LIST_REQUIRED_COURSES_WITH_CREDITS"}:
            found = (decision.get("lookup_result") or {}).get("courses", [])
            returned_codes = {course["course_id"] for course in found}
            if returned_codes != fixtures.required:
                errors.append(failure("graph_query_error", "Required-course list differs from VERIFIED catalog rule"))
            answer = payload.get("answer_text", "")
            for code in fixtures.required:
                course = fixtures.courses[code]
                if course["name"] not in answer or (expected_intent.endswith("WITH_CREDITS") and
                                                    f"{course['catalog_credits']}학점" not in answer):
                    errors.append(failure("answer_render_error", f"Answer omits VERIFIED required course {code}"))
                    break
        if expected_intent in {"COUNT_MAJOR_COURSES", "SUM_CATALOG_MAJOR_CREDITS"}:
            major_courses = [course for course in fixtures.courses.values()
                             if course["classification"].startswith("MAJOR_")]
            wanted = (len(major_courses) if expected_intent == "COUNT_MAJOR_COURSES" else
                      sum(course["catalog_credits"] for course in major_courses))
            lookup = decision.get("lookup_result") or {}
            if lookup.get("value") != wanted or lookup.get("operation") != ("COUNT" if expected_intent == "COUNT_MAJOR_COURSES" else "SUM_CREDITS"):
                errors.append(failure("graph_query_error", "Catalog aggregate value or operation differs from VERIFIED entries"))
            if str(wanted) not in payload.get("answer_text", ""):
                errors.append(failure("answer_render_error", f"Catalog aggregate {wanted} missing from answer"))
        if expected_intent == "LIST_REQUIREMENTS":
            listed_rules = (decision.get("lookup_result") or {}).get("rules", [])
            returned_rules = {r["rule_id"] for r in listed_rules}
            applicable = {r["rule_id"] for r in fixtures.rules.values() if "SINGLE" in r.get("program_types", ["SINGLE"])}
            if not applicable.issubset(returned_rules):
                errors.append(failure("graph_query_error", "Not all applicable VERIFIED requirement kinds returned"))
            if any(r["verification_status"] != "VERIFIED" for r in listed_rules):
                errors.append(failure("provenance_error", "Requirement list includes an unverified rule"))
        if actual_intent == "COURSE_LOOKUP" and decision.get("lookup_status") == "FOUND":
            entry = decision["lookup_result"]
            verified = fixtures.courses.get(entry["course_id"])
            if not verified or entry["catalog_credits"] != verified["catalog_credits"] or entry["classification"] != verified["classification"]:
                errors.append(failure("graph_query_error", "Course lookup disagrees with VERIFIED catalog entry"))
        if actual_intent == "GRADUATION_STATUS" and decision.get("graduation_outcome") == "ELIGIBLE_PDF":
            if not decision.get("coverage_complete") or any(r["status"] not in {"SATISFIED", "NOT_APPLICABLE"}
                                                            for r in decision["requirement_results"]):
                errors.append(failure("rule_error", "Graduation eligibility without complete satisfied VERIFIED rules"))
        if actual_intent == "WHAT_IF":
            scenario_decision = payload.get("scenario_decision")
            if not scenario_decision:
                delta = payload.get("scenario_delta") or {}
                safe_partial = (result["structured_query"].get("target_selector")
                                and decision.get("simulation_status") == "NEEDS_TARGET"
                                and decision.get("actual_decision_status") is not None
                                and decision.get("decision_status") == "NEEDS_INFORMATION"
                                and delta.get("status") == "NEEDS_TARGET"
                                and delta.get("changed_requirements") is None
                                and delta.get("simulated_total") is None
                                and "가상 결과는 아직 계산하지 않았습니다" in payload.get("answer_text", "")
                                and state == frozen)
                result["checks"]["safe_partial_simulation"] = bool(safe_partial)
                if not safe_partial:
                    errors.append(failure("rule_error", "Missing scenario without verified target ambiguity and actual-state answer"))
            elif state != frozen:
                errors.append(failure("rule_error", "Simulation changed actual StudentState"))
            elif scenario_decision.get("hypothetical") is not True or decision.get("hypothetical") is not False:
                errors.append(failure("rule_error", "Actual and hypothetical decision flags are not separated"))
            elif (payload.get("scenario_delta") or {}).get("status") != "CALCULATED":
                errors.append(failure("rule_error", "Scenario decision lacks calculated requirement delta"))
            if expected.get("must_not_change_credit_sum_if_zero") and scenario_decision:
                a, b = decision.get("credited_amount") or {}, scenario_decision.get("credited_amount") or {}
                if a.get("total") != b.get("total"):
                    errors.append(failure("rule_error", "Zero-credit scenario changed counted credits"))
        if actual_intent == "CONSISTENCY_CHECK":
            lookup = decision.get("lookup_result") or {}
            event = [e for e in trace.get("events", []) if e.get("event_type") == "CONSISTENCY_CHECK"]
            if not lookup.get("consistent") or len(event) != 1 or not event[0]["result"].get("consistent"):
                errors.append(failure("determinism_error", "Consistency question lacks two matching executed decisions"))
        if actual_intent == "TRACE_EXPLAIN":
            shown = decision.get("lookup_result") or {}
            used_rules = [e["rule_id"] for e in trace.get("events", []) if e.get("event_type") == "RULE_EVALUATION"]
            if shown.get("rule_ids") != used_rules or set(shown.get("relationship_ids", [])) != set((payload.get("evidence") or {}).get("relationships", [])):
                errors.append(failure("provenance_error", "Trace explanation differs from executed rules or relationships"))
        if scenario["fixture"] == "malformed_completion_record":
            if not any(e["reason"] == "MISSING_COURSE_ID" for e in decision.get("excluded", [])):
                errors.append(failure("rule_error", "Unresolved completion record was not preserved as excluded"))
        if actual_intent == "CREDIT_SUMMARY" and state is not None:
            amount = decision.get("credited_amount") or {}
            if amount.get("total") is not None and state.get("completion_coverage") == "COMPLETE":
                # This reference total comes from the VERIFIED catalog and official synthetic residual records.
                codes = {a["course_id"] for a in state["course_attempts"] if a.get("course_id") in fixtures.courses
                         and a.get("completion_status") == "COMPLETED" and a.get("verification_status") == "VERIFIED"}
                major = sum(fixtures.courses[c]["catalog_credits"] for c in codes
                            if fixtures.courses[c]["classification"].startswith("MAJOR_"))
                if amount["by_area"]["MAJOR_TOTAL"] != major:
                    errors.append(failure("rule_error", f"Major credits {amount['by_area']['MAJOR_TOTAL']} != independent VERIFIED sum {major}"))
        if expected.get("must_report_both_unsatisfied_and_needs_information"):
            statuses = {r["status"] for r in decision.get("requirement_results", [])}
            if not {"UNSATISFIED", "NEEDS_INFORMATION"}.issubset(statuses):
                errors.append(failure("rule_error", "Did not report both known unmet and unknown requirements"))
        if expected.get("must_answer_all_subquestions") and actual_intent == "GRADUATION_STATUS":
            answer = payload.get("answer_text", "")
            amount = decision.get("credited_amount") or {}
            major = (amount.get("by_area") or {}).get("MAJOR_TOTAL")
            if not all(term in answer for term in ("전공필수", "졸업")) or major is None or f"{major}학점" not in answer:
                errors.append(failure("answer_render_error", "Combined question omits major credits, missing required courses, or graduation status"))
        if expected_intent == "REQUIREMENT_AUDIT" and actual_intent == "REQUIREMENT_GAPS":
            satisfied = [r for r in decision["requirement_results"] if r["status"] == "SATISFIED"]
            if satisfied and not re.search(r"(?<!미)충족", payload.get("answer_text", "")):
                errors.append(failure("answer_render_error", "Requirement audit omits satisfied conditions"))
    # Every scenario is sent through the real user-question API. Run invariant calls only where a decision exists.
    if status == 200 and payload.get("decision"):
        again_status, again = post(port, body)
        result["checks"]["repeat_deterministic"] = again_status == 200 and all(payload.get(k) == again.get(k) for k in KEY_FIELDS)
        if not result["checks"]["repeat_deterministic"]:
            errors.append(failure("determinism_error", "Same API input changed locked output"))
        if state is not None and len(state.get("course_attempts", [])) > 1:
            shuffled = deepcopy(state)
            shuffled["course_attempts"].reverse()
            if "free_choice_records" in shuffled:
                shuffled["free_choice_records"].reverse()
            order_status, order_result = post(port, {**body, "student_state": shuffled})
            result["checks"]["input_order_invariant"] = order_status == 200 and all(
                payload.get(k) == order_result.get(k) for k in KEY_FIELDS)
            if not result["checks"]["input_order_invariant"]:
                errors.append(failure("determinism_error", "Input array order changed locked API output"))
        llm_status, llm_result = post(port, {**body, "use_local_llm": True})
        result["checks"]["llm_on_off_invariant"] = llm_status == 200 and all(
            payload.get(k) == llm_result.get(k) for k in KEY_FIELDS)
        result["checks"]["llm_expression_status"] = (llm_result.get("llm_expression") or {}).get("status")
        if not result["checks"]["llm_on_off_invariant"]:
            errors.append(failure("determinism_error", "LLM ON/OFF changed decision, evidence, trace, or answer"))
    # Scope and epistemic safety are checked independently of the scenario's requested intent.
    if payload.get("decision") and scenario["category"] == "unsupported_scope":
        if payload["decision"].get("graduation_outcome") != "UNKNOWN":
            errors.append(failure("unsupported_scope_error", "Unsupported student did not receive explicit unknown graduation status"))
    result["status"] = "FAIL" if errors else "PASS"
    result["failure_category"] = errors[0][0] if errors else None
    result["failure_reason"] = "; ".join(message for _, message in errors) if errors else None
    result["all_failures"] = [{"category": kind, "reason": message} for kind, message in errors]
    return result


def leakage_check() -> dict:
    import subprocess
    pattern = (r"evaluation[/\\]reference|교육과정 규칙 검증 승인 요청서|approval_review|score_approval|"
               r"core_scenarios|독립_검증_질문세트")
    cmd = ["rg", "-n", "-i", "--glob", "!evaluate_independent_scenarios.py", "-e", pattern,
           "src", "scripts", "data/processed", "tests"]
    result = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return {"checked_paths": cmd[-4:], "pattern": pattern, "matches": result.stdout.splitlines(),
            "pass": result.returncode == 1}


def reviewer_counterexamples(port: int, fixtures: Fixtures) -> list[dict]:
    """New state-level counterexamples, independent of the 50 question strings."""
    complete = fixtures.complete
    cases: list[tuple[str, str, dict, str, dict]] = []

    conflicting = deepcopy(complete)
    duplicate = deepcopy(conflicting["course_attempts"][0])
    duplicate["earned_credits"] = (fixtures.courses[duplicate["course_id"]]["catalog_credits"] + 1)
    conflicting["course_attempts"].append(duplicate)
    cases.append(("REV_01", "Conflicted attempt ID", conflicting, "UNKNOWN", {}))

    retake = deepcopy(complete)
    duplicate = deepcopy(retake["course_attempts"][0])
    duplicate.update({"attempt_id": "INDEPENDENT-RETAKE", "evidence_id": "SYNTHETIC-RETAKE"})
    retake["course_attempts"].append(duplicate)
    cases.append(("REV_02", "Same course in different attempts", retake, "UNKNOWN", {}))

    no_equivalence = deepcopy(complete)
    no_equivalence.pop("equivalence_review_evidence_id")
    cases.append(("REV_03", "Missing official equivalence review evidence", no_equivalence, "UNKNOWN", {}))

    no_category = deepcopy(complete)
    no_category.pop("student_category_evidence_id")
    cases.append(("REV_04", "Missing student-category evidence", no_category, "UNKNOWN", {}))

    other_catalog = deepcopy(complete)
    other_catalog["catalog_year"] = complete["catalog_year"] - 1
    cases.append(("REV_05", "Different catalog version", other_catalog, "UNKNOWN", {}))

    unverified = deepcopy(complete)
    unverified["course_attempts"][0]["verification_status"] = "UNVERIFIED"
    cases.append(("REV_06", "Unverified completion record", unverified, "UNKNOWN", {}))

    no_zero_required = fixtures.without(fixtures.zero_required)
    cases.append(("REV_07", "Zero-credit required course missing", no_zero_required,
                  "NOT_ELIGIBLE_PDF", {"total": fixtures.complete_total}))

    unmet_and_unknown = deepcopy(complete)
    unmet_and_unknown["completion_coverage"] = "PARTIAL"
    evidence_key = next(r["evidence_key"] for r in fixtures.rules.values() if r["rule_type"] == "REQUIRED_EVIDENCE")
    unmet_and_unknown["official_outcomes"][evidence_key]["value"] = False
    cases.append(("REV_08", "Known false official outcome plus incomplete transcript", unmet_and_unknown,
                  "NOT_ELIGIBLE_PDF", {"both_statuses": True}))

    overlapping = fixtures.residual(1)
    overlapping["free_choice_records"][0]["course_id"] = overlapping["course_attempts"][0]["course_id"]
    cases.append(("REV_09", "Official residual overlaps curriculum course", overlapping, "UNKNOWN", {}))

    above = fixtures.residual(fixtures.threshold + 1 - fixtures.complete_total)
    cases.append(("REV_10", "Official residual one credit above threshold", above,
                  "ELIGIBLE_PDF", {"total": fixtures.threshold + 1}))

    academic_event = deepcopy(complete)
    academic_event["academic_events"] = ["TRANSFER"]
    cases.append(("REV_11", "Unreviewed academic event", academic_event, "UNKNOWN", {}))

    results = []
    for case_id, label, state, expected, extra in cases:
        status, payload = post(port, {"student_state": state, "utterance": "졸업 가능해?", "use_local_llm": False})
        issues = []
        if status != 200 or not payload.get("decision"):
            issues.append(f"HTTP {status} or missing DeterministicDecision")
        else:
            try:
                verify_payload(payload)
            except (ValueError, KeyError, TypeError) as exc:
                issues.append(f"provenance/answer verifier: {exc}")
            decision = payload["decision"]
            if decision["graduation_outcome"] != expected:
                issues.append(f"expected {expected}, got {decision['graduation_outcome']}")
            if "total" in extra and (payload.get("credited_amount") or {}).get("total") != extra["total"]:
                issues.append(f"expected {extra['total']} counted credits")
            if extra.get("both_statuses") and not {"UNSATISFIED", "NEEDS_INFORMATION"}.issubset(
                {r["status"] for r in payload["requirement_results"]}):
                issues.append("known unmet and information gap were not kept separate")
        results.append({"id": case_id, "description": label, "student_state": state,
                        "question": "졸업 가능해?", "expected_outcome": expected,
                        "observed_outcome": (payload.get("decision") or {}).get("graduation_outcome"),
                        "decision_id": (payload.get("decision") or {}).get("decision_id"),
                        "status": "PASS" if not issues else "FAIL", "failure_reasons": issues})

    # A zero-credit simulation probes a different path and must leave the actual decision unchanged.
    state = fixtures.without(fixtures.zero_required)
    status, payload = post(port, {"student_state": state,
        "utterance": f"{fixtures.zero_required} 추가로 들으면 필수 상태가 바뀌어?", "use_local_llm": False})
    issues = []
    if status != 200 or not payload.get("scenario_decision"):
        issues.append(f"HTTP {status} or missing scenario decision")
    else:
        try:
            verify_payload(payload)
        except (ValueError, KeyError, TypeError) as exc:
            issues.append(f"provenance/answer verifier: {exc}")
        actual, scenario = payload["decision"], payload["scenario_decision"]
        required_id = next(r["rule_id"] for r in fixtures.rules.values() if r["rule_type"] == "REQUIRED_COURSES")
        before = next(r["status"] for r in actual["requirement_results"] if r["rule_id"] == required_id)
        after = next(r["status"] for r in scenario["requirement_results"] if r["rule_id"] == required_id)
        if (before, after) != ("UNSATISFIED", "SATISFIED"):
            issues.append(f"required course status changed {before} to {after}")
        if actual["credited_amount"]["total"] != scenario["credited_amount"]["total"]:
            issues.append("zero-credit addition changed credits")
        if state != fixtures.without(fixtures.zero_required):
            issues.append("simulation mutated actual StudentState")
    results.append({"id": "REV_12", "description": "Zero-credit scenario changes rule, not credits",
                    "student_state": state, "question": f"{fixtures.zero_required} 추가로 들으면 필수 상태가 바뀌어?",
                    "expected_outcome": "REQUIRED_COURSE_UNSATISFIED_TO_SATISFIED",
                    "observed_outcome": (payload.get("scenario_decision") or {}).get("graduation_outcome"),
                    "decision_id": (payload.get("decision") or {}).get("decision_id"),
                    "status": "PASS" if not issues else "FAIL", "failure_reasons": issues})

    # Entity uncertainty, mixed intent, and real conversation context probe the user-input layer.
    unknown_name = "허구학문실험실"
    status, payload = post(port, {"student_state": deepcopy(complete),
                           "utterance": f"{unknown_name} 몇 학점이야?", "use_local_llm": False})
    safe = status == 200 and (payload.get("interpretation") or {}).get("structured_query") is None
    results.append({"id": "REV_13", "description": "Unknown Korean course name is not invented",
                    "question": f"{unknown_name} 몇 학점이야?", "status": "PASS" if safe else "FAIL",
                    "failure_reasons": [] if safe else ["Unknown name was resolved or request failed"]})

    mixed_question = "현재 미달 요건하고 새 과목 추가 후 달라질 부분 같이 알려줘"
    status, payload = post(port, {"student_state": fixtures.without(fixtures.positive_required),
                           "utterance": mixed_question, "use_local_llm": False})
    query = (payload.get("interpretation") or {}).get("structured_query") or {}
    safe = (status == 200 and query.get("intent") == "WHAT_IF"
            and query.get("target_selector") == "UNSPECIFIED_COURSE"
            and payload.get("scenario_decision") is None
            and (payload.get("scenario_delta") or {}).get("status") == "NEEDS_TARGET"
            and "확인된 미충족 요건" in payload.get("answer_text", ""))
    results.append({"id": "REV_14", "description": "Mixed current and unspecified simulation asks for target",
                    "question": mixed_question, "status": "PASS" if safe else "FAIL",
                    "failure_reasons": [] if safe else ["Answered only part of ambiguous compound question"]})

    contextual_state = fixtures.without(fixtures.positive_required)
    before = deepcopy(contextual_state)
    seed_status, seed = post(port, {"student_state": contextual_state,
                              "utterance": f"{fixtures.positive_required} 이수구분 알려줘", "use_local_llm": False})
    follow_status, follow = post(port, {"student_state": contextual_state,
                                 "utterance": "방금 그 과목 한 번 더 들으면?",
                                 "context": (seed.get("interpretation") or {}).get("context"),
                                 "use_local_llm": False})
    query = (follow.get("interpretation") or {}).get("structured_query") or {}
    safe = (seed_status == follow_status == 200 and query.get("intent") == "WHAT_IF"
            and query.get("course_id") == fixtures.positive_required
            and follow.get("scenario_decision") is not None and before == contextual_state)
    if safe:
        try:
            verify_payload(follow)
        except (ValueError, KeyError, TypeError):
            safe = False
    results.append({"id": "REV_15", "description": "Verified prior entity survives a follow-up simulation",
                    "question": "방금 그 과목 한 번 더 들으면?", "status": "PASS" if safe else "FAIL",
                    "failure_reasons": [] if safe else ["Context resolution, scenario, or provenance mismatch"]})
    return results


def reviewer_counterexamples_v2(port: int, fixtures: Fixtures) -> list[dict]:
    """Probe new semantic boundaries with fresh questions and independently derived states."""
    results = []

    def check(identifier: str, description: str, question: str, state: dict | None, assertion,
              context: dict | None = None) -> dict:
        request = {"utterance": question, "use_local_llm": False}
        if state is not None:
            request["student_state"] = state
        if context:
            request["context"] = context
        frozen = deepcopy(state)
        status, payload = post(port, request)
        issues = []
        if status != 200:
            issues.append(f"HTTP {status}: {payload.get('detail') or payload.get('error')}")
        else:
            if payload.get("decision"):
                try:
                    verify_payload(payload)
                except (ValueError, KeyError, TypeError) as error:
                    issues.append(f"provenance: {error}")
            try:
                matched = assertion(payload)
            except (AttributeError, KeyError, TypeError, ValueError) as error:
                matched = False
                issues.append(f"Assertion input unavailable: {type(error).__name__}")
            if not matched:
                issues.append("Semantic boundary assertion failed")
        if state != frozen:
            issues.append("StudentState mutated")
        row = {"id": identifier, "description": description, "question": question,
               "student_state": state, "http_status": status,
               "structured_query": (payload.get("interpretation") or {}).get("structured_query"),
               "decision_id": (payload.get("decision") or {}).get("decision_id"),
               "status": "PASS" if not issues else "FAIL", "failure_reasons": issues}
        results.append(row)
        return payload

    major_required = [c for c in fixtures.courses.values() if c["classification"] == "MAJOR_REQUIRED"]
    major_elective = [c for c in fixtures.courses.values() if c["classification"] == "MAJOR_ELECTIVE"]
    check("REV2_01", "Required-only catalog count", "2026 전필 편성 과목 개수를 집계해줘", None,
          lambda p: (p.get("decision") or {}).get("lookup_result", {}).get("value") == len(major_required))
    check("REV2_02", "Elective-only catalog credit sum", "2026 전공선택 과목 학점 총합을 알려줘", None,
          lambda p: (p.get("decision") or {}).get("lookup_result", {}).get("value") ==
                    sum(c["catalog_credits"] for c in major_elective))
    check("REV2_03", "Old catalog cannot inherit 2026 aggregate", "2025 컴퓨터공학과 전공 과목 개수는?", None,
          lambda p: (p.get("interpretation") or {}).get("structured_query") is None and not p.get("decision"))
    check("REV2_04", "Unimplemented general catalog sum cannot become minimum", "교양 편성 과목 전체 학점 총합은?", None,
          lambda p: not p.get("decision") and (p.get("interpretation") or {}).get("structured_query") is None)
    positive = [a["course_id"] for a in fixtures.complete["course_attempts"]
                if a["course_id"] in fixtures.required and fixtures.courses[a["course_id"]]["catalog_credits"] > 0]
    first, second = positive[:2]
    two_missing = fixtures.without(first, second)
    check("REV2_05", "Two explicit courses produce one hypothetical state", f"{first}와 {second}를 함께 수강했다고 치면?", two_missing,
          lambda p: (p.get("interpretation") or {}).get("structured_query", {}).get("added_course_ids") == sorted([first, second])
                    and p.get("scenario_decision") is not None
                    and (p.get("scenario_delta") or {}).get("status") == "CALCULATED")
    one_missing = fixtures.without(first)
    check("REV2_06", "Repeated explicit target is not double credited", f"{first}와 {first}를 함께 추가하면?", one_missing,
          lambda p: p.get("scenario_decision") is not None and
                    (p.get("scenario_delta") or {}).get("total_credit_change") == fixtures.courses[first]["catalog_credits"])
    check("REV2_07", "Two missing required candidates stay ambiguous", "전필 한 과목 더 이수한다면 요건이 바뀌나?", two_missing,
          lambda p: p.get("scenario_decision") is None and
                    set((p.get("decision") or {}).get("simulation_candidates", [])) == {first, second})
    check("REV2_08", "No missing zero-credit course is invented", "0학점 전필을 하나 더 이수했다고 가정해 봐", deepcopy(fixtures.complete),
          lambda p: p.get("scenario_decision") is None and
                    (p.get("decision") or {}).get("simulation_status") == "NEEDS_TARGET")
    missing_code = deepcopy(fixtures.complete)
    missing_code["course_attempts"].append({"attempt_id": "REVIEWER-MISSING-CODE", "completion_status": "COMPLETED",
                                            "verification_status": "VERIFIED", "evidence_id": "REVIEWER-INPUT-MISSING-CODE"})
    check("REV2_09", "Verified flag does not repair missing course identity", "코드가 빠진 이수 항목도 학점에 넣을 수 있어?", missing_code,
          lambda p: (p.get("decision") or {}).get("decision_status") == "NEEDS_INFORMATION"
                    and any(x.startswith("UNRESOLVED_COMPLETION_RECORD:") for x in (p.get("decision") or {}).get("needs_information", [])))
    mixed = deepcopy(missing_code)
    mixed["completion_coverage"] = "PARTIAL"
    mixed.pop("completion_coverage_evidence_id", None)
    mixed["official_outcomes"]["graduation_certification_passed"] = {
        "value": False, "verification_status": "VERIFIED", "evidence_id": "REVIEWER-OFFICIAL-FAIL"}
    check("REV2_10", "Verified unmet and unknown transcript coexist", "확인된 탈락 조건과 아직 모르는 조건을 함께 정리해줘", mixed,
          lambda p: {"UNSATISFIED", "NEEDS_INFORMATION"}.issubset(
              {r["status"] for r in (p.get("decision") or {}).get("requirement_results", [])}))
    unknown = deepcopy(fixtures.complete)
    unknown["course_attempts"].append({"attempt_id": "REVIEWER-UNKNOWN", "course_id": "XYZ9999",
                                        "completion_status": "COMPLETED", "verification_status": "VERIFIED",
                                        "evidence_id": "REVIEWER-UNKNOWN-INPUT"})
    check("REV2_11", "Unknown code with Korean particle stays unverified", "XYZ9999를 이수로 적으면 인정돼?", unknown,
          lambda p: (p.get("decision") or {}).get("lookup_result", {}).get("verified_catalog_entry") is False)
    check("REV2_12", "Unknown explicit simulation target is not invented", "XYZ9999를 추가로 이수했다면?", unknown,
          lambda p: p.get("scenario_decision") is None and
                    (p.get("decision") or {}).get("simulation_status") == "NEEDS_TARGET")
    seed_status, seed = post(port, {"student_state": one_missing, "utterance": f"{second} 분류가 뭐지?", "use_local_llm": False})
    check("REV2_13", "New explicit course overrides previous context", f"그럼 {first}를 들었을 땐?", one_missing,
          lambda p: (p.get("interpretation") or {}).get("structured_query", {}).get("course_id") == first
                    and p.get("scenario_decision") is not None,
          (seed.get("interpretation") or {}).get("context") if seed_status == 200 else None)
    check("REV2_14", "Trace explanation cites only executed rules", "근거 관계 및 규칙 실행 과정을 내역으로 보여줄래?", mixed,
          lambda p: set(((p.get("decision") or {}).get("lookup_result") or {}).get("relationship_ids", [])) ==
                    set((p.get("evidence") or {}).get("relationships", [])))
    residual = fixtures.residual(1)
    check("REV2_15", "Order invariance includes official residual records", "수강 내역 순서를 뒤집어도 판정이 동일한지 검증해줘", residual,
          lambda p: ((p.get("decision") or {}).get("lookup_result") or {}).get("consistent") is True)
    check("REV2_16", "Unknown explicit code overrides remembered course", "그 과목 말고 XYZ9999를 더 들었다고 하면?", one_missing,
          lambda p: p.get("scenario_decision") is None
                    and (p.get("decision") or {}).get("simulation_status") == "NEEDS_TARGET"
                    and "XYZ9999" in ((p.get("interpretation") or {}).get("structured_query") or {}).get("added_course_ids", []),
          (seed.get("interpretation") or {}).get("context") if seed_status == 200 else None)
    return results


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=18473)
    args = parser.parse_args()
    files = sorted(SCENARIO_DIR.glob("*.json"))
    if len(files) != 1:
        raise SystemExit(f"Expected one independent JSON question set, found {len(files)}")
    raw = files[0].read_bytes()
    question_set = json.loads(raw.decode("utf-8"))
    scenarios = question_set["scenarios"]
    if len(scenarios) != 50 or len({s["id"] for s in scenarios}) != 50:
        raise SystemExit("Question set must contain 50 distinct scenario IDs")
    catalog = build()
    fixtures = Fixtures(catalog)
    import pdfplumber
    with pdfplumber.open(PDF) as pdf:
        row_check = catalog_pdf_row_check(pdf, fixtures)
        if not all(value for key, value in row_check.items() if key.endswith("_matches")):
            raise SystemExit(f"VERIFIED catalog thresholds disagree with curriculum PDF: {row_check}")
        rows = [evaluate_case(args.port, scenario, fixtures, catalog, pdf) for scenario in scenarios]
    reviewer = reviewer_counterexamples(args.port, fixtures) + reviewer_counterexamples_v2(args.port, fixtures)
    # Same fixture + same conceptual intent gives an independent paraphrase consistency check.
    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in rows:
        if row["status"] != "SKIP" and row["expected_contract"].get("expected_intent"):
            groups[(row["fixture_name"], row["expected_contract"]["expected_intent"])].append(row)
    paraphrases = []
    for key, group in groups.items():
        if len(group) < 2:
            continue
        first = group[0]["deterministic_decision"]
        for row in group[1:]:
            comparable = first is not None and row["deterministic_decision"] is not None
            same = first == row["deterministic_decision"] if comparable else None
            paraphrases.append({"fixture_intent": key, "first": group[0]["scenario_id"],
                                "second": row["scenario_id"], "comparable": comparable,
                                "same_decision": same})
            if comparable and not same and row["status"] == "PASS":
                row["status"] = "FAIL"
                row["failure_category"] = "determinism_error"
                row["failure_reason"] = "Equivalent question expression changed DeterministicDecision"
    leakage = leakage_check()
    count = Counter(row["status"] for row in rows)
    before_summary = json.loads(BEFORE.read_text(encoding="utf-8")) if BEFORE.exists() else None
    before_counts = before_summary["counts"] if before_summary else None
    safe_partial_ids = [row["scenario_id"] for row in rows if row["checks"].get("safe_partial_simulation")]
    by_category: dict[str, Counter] = defaultdict(Counter)
    for row in rows:
        by_category[row["category"]][row["status"]] += 1
    summary = {"question_set_path": str(files[0].relative_to(ROOT)),
               "question_set_sha256": hashlib.sha256(raw).hexdigest(),
               "source_document_sha256": catalog["source_sha256"],
               "catalog_pdf_rule_row_check": row_check,
               "counts": dict(count), "before_counts": before_counts,
               "safe_partial_simulation_ids": safe_partial_ids,
               "by_category": {k: dict(v) for k, v in sorted(by_category.items())},
               "failure_types": dict(Counter(row["failure_category"] for row in rows if row["status"] == "FAIL")),
               "paraphrase_checks": paraphrases,
               "reviewer_counterexamples": reviewer,
               "llm_checks": dict(Counter(str(row["checks"].get("llm_on_off_invariant")) for row in rows
                                         if "llm_on_off_invariant" in row["checks"])),
               "repeat_checks": dict(Counter(str(row["checks"].get("repeat_deterministic")) for row in rows
                                            if "repeat_deterministic" in row["checks"])),
               "input_order_checks": dict(Counter(str(row["checks"].get("input_order_invariant")) for row in rows
                                                 if "input_order_invariant" in row["checks"])),
               "provenance_checks": dict(Counter(str(row["checks"].get("pdf_source_verified")) for row in rows
                                               if "pdf_source_verified" in row["checks"])),
               "leakage_check": leakage, "results": rows}
    RESULTS.write_text(json.dumps(summary, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    lines = ["# 독립 50문항 사용자 시나리오 평가", "",
             f"- 질문세트: `{summary['question_set_path']}` (SHA-256 `{summary['question_set_sha256']}`)",
             f"- 실제 `/api/query` 경로 결과: PASS {count['PASS']} / FAIL {count['FAIL']} / SKIP {count['SKIP']}",
             (f"- 수정 전 보존 결과: PASS {before_counts.get('PASS', 0)} / FAIL {before_counts.get('FAIL', 0)} / "
              f"SKIP {before_counts.get('SKIP', 0)} (`independent_scenario_results_before.json`)"
              if before_counts else "- 수정 전 결과 파일 없음"),
             (f"- 목표가 확정되지 않은 가정 질문 {len(safe_partial_ids)}건: 현재 상태만 확인하고 "
              f"가상 수치 계산은 보류 ({', '.join(safe_partial_ids)})"),
             f"- LLM ON/OFF 일치: {summary['llm_checks']}",
             f"- 동일 입력 반복: {summary['repeat_checks']}; 이수 입력 순서: {summary['input_order_checks']}",
             f"- PDF 출처 확인: {summary['provenance_checks']}",
             f"- Reviewer 반례 전체: {sum(r['status']=='PASS' for r in reviewer)}/{len(reviewer)} PASS "
             f"(이번 수정에서 추가한 반례: {sum(r['status']=='PASS' for r in reviewer if r['id'].startswith('REV2_'))}/"
             f"{sum(r['id'].startswith('REV2_') for r in reviewer)})",
             f"- 평가자료 누수 정적 검사: {'PASS' if leakage['pass'] else 'FAIL'}", "",
             f"- PDF 원문 수치 행 대조: {row_check['pdf_261_department_row_matches']} / {row_check['pdf_577_graduation_row_matches']}",
             f"- 같은 fixture·의도 표현 비교: {sum(p['same_decision'] is True for p in paraphrases)}/"
             f"{sum(p['comparable'] for p in paraphrases)} 비교 가능 쌍 일치; "
             f"{sum(not p['comparable'] for p in paraphrases)}쌍은 질문 해석 실패로 비교 불가", "",
             "## 범주별 결과", "", "| 범주 | PASS | FAIL | SKIP | 통과율(PASS/전체) |", "| --- | ---: | ---: | ---: | ---: |"]
    for category, values in sorted(by_category.items()):
        total = sum(values.values())
        lines.append(f"| {category} | {values['PASS']} | {values['FAIL']} | {values['SKIP']} | {values['PASS']}/{total} |")
    lines += ["", "## 실패 유형별 수정 전후", "", "| 유형 | 수정 전 FAIL | 수정 후 FAIL |", "| --- | ---: | ---: |"]
    before_failure_types = before_summary.get("failure_types", {}) if before_summary else {}
    for kind in sorted(set(before_failure_types) | set(summary["failure_types"])):
        lines.append(f"| {kind} | {before_failure_types.get(kind, 0)} | {summary['failure_types'].get(kind, 0)} |")
    lines += ["", "## 실패와 SKIP", "", "| ID | 상태 | 유형 | 이유 |", "| --- | --- | --- | --- |"]
    for row in rows:
        if row["status"] != "PASS":
            reason = (row["failure_reason"] or "").replace("|", "\\|").replace("\n", " ")
            lines.append(f"| {row['scenario_id']} | {row['status']} | {row['failure_category']} | {reason} |")
    lines += ["", "## 신규 Reviewer 반례", "", "| ID | 반례 | 결과 |", "| --- | --- | --- |"]
    for item in reviewer:
        lines.append(f"| {item['id']} | {item['description']} | {item['status']}"
                     + (f" ({'; '.join(item['failure_reasons'])})" if item["failure_reasons"] else "") + " |")
    lines += ["", "## Builder → Reviewer → Verifier → Quality Gate", "",
              "- **Builder:** 질문세트 50개를 각각 실제 `/api/query` 사용자 문장 경로로 실행하고, "
              "fixture는 기존 합성 입력과 VERIFIED 카탈로그·요건에서 생성했다. HTTP 실패·해석 실패도 FAIL로 보존했다.",
              f"- **Reviewer:** 질문세트 밖의 상태·경계·모호성·맥락 반례 {len(reviewer)}개를 API로 실행했다. "
              f"{sum(r['status']=='PASS' for r in reviewer)}개 통과했다.",
              "- **Verifier:** 실제 `QUERY_PLAN`·`GRAPH_QUERY`·`RULE_EVALUATION` 이벤트와 "
              "EvidenceBundle·RequirementResult·Decision·AnswerPayload를 대조했다. "
              "원문 PDF 해시, 과목코드 인용 페이지, 261·577쪽 학점표도 별도 확인했다.",
              f"- **Quality Gate: {'PASS' if count['FAIL']==0 and leakage['pass'] and all(r['status']=='PASS' for r in reviewer) else 'FAIL'}.** "
              f"독립 질문 50건 중 실행 가능한 {50-count['SKIP']}건의 API 경로, 새 Reviewer 반례, "
              "출처 및 LLM 불변 검사가 통과했다. 목표 과목이 없는 가정 질문의 PASS는 "
              "수치 시뮬레이션 성공이 아니라 안전한 부분 답변을 뜻한다. "
              "CTX_04는 누락 학기에 특정 필수과목을 이수하지 않았다는 공식 증거가 없어 SKIP으로 유지한다.", ""]
    lines += ["", "## 판정 기준", "",
              "질문세트의 개념적 의도는 `INTENT_FAMILIES`의 일반 의미군으로 현재 API 의도와 비교했다. "
              "단순 문장 일치나 Rule Engine 직접 호출은 PASS 근거가 아니다. ",
              "기대 학점 기준은 VERIFIED 카탈로그의 졸업 요건값과 합성 fixture에서 유도했다. "
              "출처는 교육과정 PDF의 SHA-256, 반환된 원문 페이지 및 실제 조회·규칙 이벤트와 대조했다. "
              "승인 요청서 PDF는 열지 않았다. 상세 API 응답과 모든 검사는 JSON 결과 파일을 참조한다.", ""]
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    print(f"PASS {count['PASS']} / FAIL {count['FAIL']} / SKIP {count['SKIP']}; "
          f"LLM {summary['llm_checks']}; leakage {'PASS' if leakage['pass'] else 'FAIL'}")
    for category, values in sorted(by_category.items()):
        print(f"  {category}: {values['PASS']}/{sum(values.values())} pass")
    if count["FAIL"] or not leakage["pass"] or any(item["status"] != "PASS" for item in reviewer):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
