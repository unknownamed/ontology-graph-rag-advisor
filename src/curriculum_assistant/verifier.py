"""Check the executed evidence chain before a payload leaves the server."""
from __future__ import annotations

import hashlib
import json


def _digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def verify_payload(payload: dict) -> None:
    decisions = [payload["decision"]]
    if payload.get("scenario_decision"):
        decisions.append(payload["scenario_decision"])
    trace = payload["execution_trace"]
    events = trace["events"]
    if [e["sequence"] for e in events] != list(range(1, len(events) + 1)):
        raise ValueError("Execution trace sequence is not the actual ordered event list")
    if len({e["event_id"] for e in events}) != len(events):
        raise ValueError("Duplicate execution event ID")
    if trace["decision_id"] != payload["decision"]["decision_id"]:
        raise ValueError("Execution trace points to another decision")
    authority = payload["authority"]
    document_set, ruleset = authority["document_set"], authority["ruleset"]
    selected = [event for event in events if event["event_type"] == "QUERY_PLAN"]
    if len(selected) != 1 or any(
        (trace[key], payload["decision"][key], selected[0][key]) != (value, value, value)
        for key, value in (("authoritative_document_set_id", document_set["set_id"]),
                           ("authoritative_document_set_version", document_set["set_version"]),
                           ("ruleset_id", ruleset["ruleset_id"]),
                           ("ruleset_version", ruleset["ruleset_version"]))
    ):
        raise ValueError("Decision, trace and actual RuleSet selection disagree")
    included_documents = set(document_set["included_documents"])
    if (set(selected[0]["document_relation_ids"]) !=
            {relation["relation_id"] for relation in authority["document_relations"]}):
        raise ValueError("Document relations were not selected by the executed QueryPlan")
    loaded_rule_ids = set(authority["rule_sources"])
    if ({doc["document_id"] for doc in authority["documents"]} != included_documents
            or not loaded_rule_ids.issubset(ruleset["included_rule_ids"])):
        raise ValueError("RuleSet document or rule membership differs from its payload")
    missing_loaded = set(ruleset["included_rule_ids"]) - loaded_rule_ids
    if missing_loaded and payload["decision"]["intent"] == "GRADUATION_STATUS":
        if (payload["decision"]["graduation_outcome"] == "ELIGIBLE_PDF"
                or not all(f"RULE_NOT_LOADED:{rid}" in payload["decision"]["needs_information"]
                           for rid in missing_loaded)):
            raise ValueError("Missing pinned RuleSet rule was not reported as incomplete")
    for source in authority["rule_sources"].values():
        if not set(source["source_documents"]).issubset(included_documents):
            raise ValueError("A rule source is outside the official document set")
    query_returned = {item for event in events if event["event_type"] == "GRAPH_QUERY" for item in event["returned_ids"]}
    evidence = payload["evidence"]
    for locator in evidence["source_locators"].values():
        if locator["source_document_id"] not in included_documents:
            raise ValueError("Evidence locator refers to a non-official document")
    fact_ids = {fact["fact_id"] for fact in evidence["facts"]}
    relationship_ids = set(evidence["relationships"])
    details = {edge["id"]: edge for edge in evidence["relationship_details"]}
    node_ids = {node["id"] for node in evidence["nodes"]}
    if set(details) != relationship_ids or any(edge["src"] not in node_ids or edge["dst"] not in node_ids for edge in details.values()):
        raise ValueError("Displayed graph edge lacks a returned endpoint or edge ID")
    student_evidence_ids = set(evidence["student_evidence_refs"])
    if not relationship_ids.issubset(query_returned):
        raise ValueError("Displayed graph relation was not returned by an executed query")
    if any(event["event_type"] == "GRAPH_QUERY" and event["operation"] not in {"FETCH_CATALOG_ENTRY", "FETCH_CATALOG_SET", "FETCH_REQUIREMENTS", "FETCH_POLICY_FACTS", "FETCH_COURSE_REQUIREMENT_LINKS"} for event in events):
        raise ValueError("Unexpected graph operation in trace")
    if payload["decision"]["intent"] == "REMAINING_PLAN":
        decision = payload["decision"]
        summary = decision["remaining_requirements"]
        statuses = {r["rule_id"]: r["status"] for r in decision["requirement_results"]}
        for key, status in (("satisfied_requirements", "SATISFIED"),
                            ("unsatisfied_requirements", "UNSATISFIED"),
                            ("needs_information", "NEEDS_INFORMATION"),
                            ("not_applicable_requirements", "NOT_APPLICABLE")):
            if summary[key] != sorted(rid for rid, observed in statuses.items() if observed == status):
                raise ValueError("Remaining summary differs from executed rule results")
        catalog_queries = [e for e in events if e["event_type"] == "GRAPH_QUERY" and e["operation"] == "FETCH_CATALOG_SET"]
        link_queries = [e for e in events if e["event_type"] == "GRAPH_QUERY" and e["operation"] == "FETCH_COURSE_REQUIREMENT_LINKS"]
        calculations = [e for e in events if e["event_type"] == "REMAINING_CALCULATION"]
        if len(catalog_queries) != 1 or len(link_queries) != 1 or len(calculations) != 1:
            raise ValueError("Remaining plan lacks its actual graph queries or calculation")
        catalog_returned = set(catalog_queries[0]["returned_ids"])
        link_returned = set(link_queries[0]["returned_ids"])
        if any(f"ENTRY-CE-2026-{c['course_id']}" not in catalog_returned for c in decision["candidate_courses"]):
            raise ValueError("Candidate course was not returned by catalog query")
        recognized = {r["course_id"] for r in decision.get("recognitions", [])}
        missing_required = set(decision.get("missing_courses") or [])
        for candidate in decision["candidate_courses"]:
            rid_list = candidate["satisfies_requirement_ids"]
            rel_list = candidate["relationship_ids"]
            if candidate["already_completed"] != (candidate["course_id"] in recognized):
                raise ValueError("Candidate completion differs from recognized attempts")
            if (not set(rel_list).issubset(link_returned & relationship_ids)
                    or any(details[rid]["kind"] != "SATISFIES" or details[rid]["src"] != candidate["provenance"]["entry_id"]
                           or details[rid]["dst"] not in rid_list for rid in rel_list)):
                raise ValueError("Candidate lacks an actually queried SATISFIES relationship")
            if not set(rid_list).issubset({rid for rid, status in statuses.items() if status == "UNSATISFIED"}):
                raise ValueError("Candidate targets a requirement that is not confirmed unmet")
            if candidate["candidate_status"] == "REQUIRED" and candidate["course_id"] not in missing_required:
                raise ValueError("A non-required course was marked REQUIRED")
            if candidate["candidate_status"] in {"REQUIRED", "ELIGIBLE_OPTION"} and (candidate["already_completed"] or not rel_list):
                raise ValueError("An ineligible or completed course was recommended")
            if candidate["candidate_status"] == "ALREADY_COMPLETED" and not candidate["already_completed"]:
                raise ValueError("Already completed classification is inconsistent")
            if candidate["provenance"]["source_document_id"] not in included_documents or not candidate["provenance"]["source"].get("pdf_page"):
                raise ValueError("Candidate source does not lead to an official PDF page")
            if len(rel_list) != len(rid_list) or candidate["provenance"]["rule_source_refs"] != {
                    rid: authority["rule_sources"][rid]["source_refs"] for rid in rid_list}:
                raise ValueError("Candidate rule and relationship provenance are inconsistent")
        count = calculations[0]["result"]["candidate_counts"]
        if count != {status: sum(c["candidate_status"] == status for c in decision["candidate_courses"])
                     for status in ("REQUIRED", "ELIGIBLE_OPTION", "ALREADY_COMPLETED", "NOT_APPLICABLE")}:
            raise ValueError("Displayed candidate counts differ from calculation trace")
    if payload["decision"]["intent"] == "CATALOG_AGGREGATE":
        result = payload["decision"]["lookup_result"]
        aggregation = [event for event in events if event["event_type"] == "CATALOG_AGGREGATION"]
        catalog_queries = [event for event in events if event["event_type"] == "GRAPH_QUERY"
                           and event["operation"] == "FETCH_CATALOG_SET"]
        entries = [fact for fact in evidence["facts"] if fact.get("entry_id")]
        if len(aggregation) != 1 or len(catalog_queries) != 1:
            raise ValueError("Catalog aggregate lacks its executed graph query or calculation")
        if any(entry["verification_status"] != "VERIFIED" or entry["classification_verification_status"] != "VERIFIED"
               for entry in entries):
            raise ValueError("Catalog aggregate used an unverified entry")
        expected = len(entries) if result["operation"] == "COUNT" else sum(entry["catalog_credits"] for entry in entries)
        if (result["value"] != expected or aggregation[0]["result"] != expected
                or set(aggregation[0]["input_refs"]) != {entry["entry_id"] for entry in entries}
                or set(result["course_ids"]) != {entry["course_id"] for entry in entries}):
            raise ValueError("Catalog aggregate differs from returned verified entries")
    for fact in evidence.get("policy_facts", []):
        if fact["policy_fact_id"] not in query_returned or fact["relationship_id"] not in relationship_ids:
            raise ValueError("Policy fact lacks an executed graph query and relation")
        if fact["verification_status"] != "VERIFIED" or not set(fact["source_refs"]).issubset(evidence["source_locators"]):
            raise ValueError("Policy fact lacks verified PDF provenance")
    rule_events = {event["event_id"]: event for event in events if event["event_type"] == "RULE_EVALUATION"}
    for decision in decisions:
        unhashed = {key: value for key, value in decision.items() if key not in {"canonical_result_hash", "decision_id"}}
        if decision["canonical_result_hash"] != _digest(unhashed):
            raise ValueError("Decision content differs from its deterministic hash")
        if decision["decision_id"] != "DEC-" + decision["canonical_result_hash"][:16]:
            raise ValueError("Decision ID does not match content")
        if decision["data_snapshot_id"] != trace["data_snapshot_id"]:
            raise ValueError("Decision and trace use different graph snapshots")
        if (decision["student_state_version"] != selected[0]["student_state_version"]
                or not set(decision["applicable_rule_ids"]).issubset(ruleset["included_rule_ids"])):
            raise ValueError("Decision does not pin the selected applicable RuleSet")
        for recognition in decision.get("recognitions", []):
            if recognition["fact_id"] not in fact_ids:
                raise ValueError("Credit recognition lacks a queried catalog fact")
            if not set(recognition["relationship_ids"]).issubset(relationship_ids):
                raise ValueError("Credit recognition lacks queried relationships")
            if recognition["student_evidence_id"] not in student_evidence_ids:
                raise ValueError("Credit recognition lacks student evidence")
            required_refs = {recognition["attempt_id"], recognition["student_evidence_id"],
                             recognition["fact_id"], *recognition["relationship_ids"]}
            if not any(event["event_type"] == "CREDIT_RECOGNITION"
                       and event["result"]["recognition_id"] == recognition["recognition_id"]
                       and required_refs.issubset(event.get("input_refs", [])) for event in events):
                raise ValueError("Credit recognition has no complete execution input record")
        for result in decision["requirement_results"]:
            source = authority["rule_sources"].get(result["rule_id"])
            if not source or source["source_refs"] != result["source_refs"]:
                raise ValueError("Requirement result differs from its versioned rule evidence")
            if not set(result["used_fact_ids"]).issubset(fact_ids):
                raise ValueError("Rule result cites a fact absent from EvidenceBundle")
            if not set(result["used_relationship_ids"]).issubset(relationship_ids):
                raise ValueError("Rule result cites an unreturned graph relationship")
            if not set(result["used_student_evidence_ids"]).issubset(student_evidence_ids):
                raise ValueError("Rule result cites missing student evidence")
            if not set(result["source_refs"]).issubset(evidence["source_locators"]):
                raise ValueError("Rule result has no PDF source locator")
            if any(eid not in rule_events or rule_events[eid]["rule_id"] != result["rule_id"] or rule_events[eid]["result"] != result["status"] for eid in result["execution_event_ids"]):
                raise ValueError("Rule result has no matching actual calculation event")
    actual = payload["decision"]
    affecting = {c["conflict_id"] for c in authority["unresolved_conflicts"]}
    if set(actual["unresolved_conflict_ids"]) != affecting:
        raise ValueError("Decision conflict list differs from selected RuleSet")
    if affecting and actual["intent"] == "GRADUATION_STATUS":
        observed = {event["conflict_id"] for event in events if event["event_type"] == "RULE_CONFLICT"}
        if (observed != affecting or actual["graduation_outcome"] != "UNKNOWN"
                or actual["decision_status"] != "NEEDS_INFORMATION"):
            raise ValueError("Unresolved official-rule conflict was not safely gated")
    if actual["intent"] == "TRACE_EXPLAIN":
        described = actual["lookup_result"]
        executed_rules = [event["rule_id"] for event in events if event["event_type"] == "RULE_EVALUATION"]
        if described["rule_ids"] != executed_rules or set(described["relationship_ids"]) != relationship_ids:
            raise ValueError("Trace explanation describes unexecuted rules or relationships")
    if payload.get("scenario_delta") is not None:
        comparison = [event for event in events if event["event_type"] == "SCENARIO_COMPARISON"]
        if len(comparison) != 1 or comparison[0]["result"] != payload["scenario_delta"]:
            raise ValueError("Scenario delta differs from its execution event")
        if payload.get("scenario_decision"):
            before = {r["rule_id"]: r["status"] for r in actual["requirement_results"]}
            after = payload["scenario_decision"]
            changed = [{"rule_id": r["rule_id"], "before": before[r["rule_id"]], "after": r["status"]}
                       for r in after["requirement_results"] if r["rule_id"] in before and before[r["rule_id"]] != r["status"]]
            if payload["scenario_delta"]["changed_requirements"] != changed:
                raise ValueError("Scenario requirement delta differs from decisions")
            delta = payload["scenario_delta"]
            before_required = actual.get("missing_courses")
            after_required = after.get("missing_courses")
            completed_required = (sorted(set(before_required) - set(after_required))
                                  if before_required is not None and after_required is not None else None)
            if (delta.get("missing_required_before") != before_required
                    or delta.get("missing_required_after") != after_required
                    or delta.get("completed_required_course_ids") != completed_required):
                raise ValueError("Scenario required course delta differs from decisions")
            first_major = actual["credited_amount"]["by_area"].get("MAJOR_TOTAL")
            last_major = after["credited_amount"]["by_area"].get("MAJOR_TOTAL")
            if (delta["actual_major"] != first_major or delta["simulated_major"] != last_major
                    or delta["major_credit_change"] != (last_major - first_major if first_major is not None and last_major is not None else None)):
                raise ValueError("Scenario major credit delta differs from decisions")
            def projected(value: dict) -> str:
                if value["unresolved_conflict_ids"]:
                    return "UNKNOWN"
                if value["decision_status"] == "UNSATISFIED":
                    return "NOT_ELIGIBLE_PDF"
                return "ELIGIBLE_PDF" if value["decision_status"] == "SATISFIED" and value["coverage_complete"] else "UNKNOWN"
            base_for_preview = (actual["lookup_result"]["underlying_decision"]
                                if actual["intent"] == "CONSISTENCY_CHECK" else actual)
            if (delta["graduation_preview_before"] != projected(base_for_preview)
                    or delta["graduation_preview_after"] != projected(after)):
                raise ValueError("Scenario graduation preview differs from verified rule results")
    if actual["intent"] == "GRADUATION_STATUS":
        coverage_events = [event for event in events if event["event_type"] == "COVERAGE_CHECK"]
        if len(coverage_events) != 1 or coverage_events[0]["result"] != ("COMPLETE" if actual["coverage_complete"] else "INCOMPLETE"):
            raise ValueError("Graduation coverage result differs from actual execution")
        if not set(coverage_events[0]["missing"]).issubset(actual["needs_information"]):
            raise ValueError("Graduation coverage gaps are absent from the decision")
    for key in ("requirement_results", "credited_amount", "missing_amount", "missing_courses", "needs_information"):
        if payload[key] != actual[key]:
            raise ValueError(f"AnswerPayload {key} differs from DeterministicDecision")
    from .render import build_remaining_presentation, render_answer
    if actual["intent"] == "REMAINING_PLAN" and actual.get("remaining_requirements"):
        if payload.get("remaining_presentation") != build_remaining_presentation(payload):
            raise ValueError("Student-facing candidate groups differ from verified decision")
    if payload.get("answer_text") != render_answer(payload):
        raise ValueError("Rendered answer differs from locked decision values")
    if actual["graduation_outcome"] == "ELIGIBLE_PDF" and (
        not actual.get("coverage_complete") or actual["needs_information"]
        or any(result["status"] != "SATISFIED" for result in actual["requirement_results"] if result["status"] != "NOT_APPLICABLE")
    ):
        raise ValueError("Incomplete rule coverage cannot yield graduation eligibility")
