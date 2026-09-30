"""Deterministic 2026 computer-engineering vertical slice.

Only the graph provides catalog facts. Student evidence is never written into it.
"""
from __future__ import annotations

import hashlib
from collections import Counter
from copy import deepcopy

from .authority import scope_applies, scope_status
from .graph import Graph, canonical
from .remaining import candidate_courses, summarize_remaining

INTENTS = {"COURSE_LOOKUP", "CREDIT_SUMMARY", "REQUIREMENT_GAPS", "WHAT_IF", "GRADUATION_STATUS",
           "POLICY_LOOKUP", "CATALOG_AGGREGATE", "ENTITY_CHECK", "CONSISTENCY_CHECK", "TRACE_EXPLAIN",
           "REMAINING_PLAN"}
CORE_SINGLE_RULE_IDS = frozenset({
    "R-CE-2026-ADVANCED-CREDITS", "R-CE-2026-MAJOR-ELECTIVE-CREDITS",
    "R-CE-2026-MAJOR-REQUIRED-CREDITS", "R-CE-2026-MAJOR-TOTAL-CREDITS",
    "R-CE-2026-REQUIRED-COURSES", "R-GE-2026-AI-FOUNDATION",
    "R-GE-2026-BALANCED-AREAS", "R-GE-2026-BALANCED-CREDITS",
    "R-GE-2026-BASIC-CREDITS", "R-GE-2026-CREDIT-CAP",
    "R-GE-2026-ENGLISH", "R-GE-2026-FUTURE-DESIGN",
    "R-GE-2026-TOTAL-CREDITS", "R-GE-2026-WRITING",
    "R-GRAD-2026-CERTIFICATION", "R-GRAD-2026-THESIS-ENROLLED",
    "R-GRAD-2026-THESIS-PASSED", "R-GRAD-2026-TOTAL-CREDITS",
})
POLICY_RULE_TOPICS = {"GRADUATION_CREDITS", "GENERAL_CREDITS", "GENERAL_AREAS", "MAJOR_CREDITS",
                      "REQUIRED_COURSES", "GRADUATION_CONDITIONS", "ALL_REQUIREMENTS"}
POLICY_FACT_TOPICS = {"APPLICABILITY", "FREE_CHOICE", "EQUIVALENCE", "RECOMMENDATIONS", "TRANSITION", "MULTI_PROGRAM"}
STATUSES = {"VERIFIED", "UNVERIFIED", "CONFLICTED", "MISSING"}
PROGRAM_TYPES = {"SINGLE", "MINOR", "DOUBLE"}
FREE_CHOICE_CATEGORIES = {"OTHER_DEPARTMENT_MAJOR", "TEACHER_EDUCATION", "LIFELONG_EDUCATOR",
                          "MILITARY", "OTHER_DEPARTMENT_OFFERING"}


def digest(value: object) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def _event(trace: list[dict], event_type: str, **fields: object) -> str:
    eid = f"EV-{len(trace) + 1:04d}"
    trace.append({"event_id": eid, "sequence": len(trace) + 1, "event_type": event_type, **fields})
    return eid


def _validate(student: dict, query: dict) -> None:
    if not isinstance(student, dict) or not isinstance(query, dict):
        raise ValueError("StudentState and StructuredQuery must be objects")
    if not isinstance(student.get("student_state_id"), str) or not student["student_state_id"].strip():
        raise ValueError("student_state_id is required")
    for year_key in ("admission_year", "credit_policy_year", "catalog_year"):
        year = student.get(year_key)
        if year is not None and (type(year) is not int or not 1900 <= year <= 2100):
            raise ValueError(f"{year_key} must be a year or null")
    if query.get("intent") not in INTENTS:
        raise ValueError("Unsupported StructuredQuery intent")
    if query.get("intent") == "POLICY_LOOKUP":
        topics = query.get("topics")
        if not isinstance(topics, list) or not topics or len(topics) > 8 or any(topic not in POLICY_RULE_TOPICS | POLICY_FACT_TOPICS for topic in topics):
            raise ValueError("POLICY_LOOKUP requires allowlisted topics")
        if query.get("program_type", student.get("program_type")) not in PROGRAM_TYPES:
            raise ValueError("POLICY_LOOKUP program_type is invalid")
        if "entry_year" in query and (type(query["entry_year"]) is not int or not 1900 <= query["entry_year"] <= 2100):
            raise ValueError("POLICY_LOOKUP entry_year is invalid")
    if query.get("intent") == "CATALOG_AGGREGATE":
        if query.get("aggregate") not in {"COUNT", "SUM_CREDITS"}:
            raise ValueError("Catalog aggregate operation is not allowlisted")
        if query.get("department_id") != "DEPT-COMPUTER-ENGINEERING" or query.get("curriculum_id") != "CURRICULUM-CE-2026":
            raise ValueError("Catalog aggregate scope is not verified")
        classes = query.get("classifications")
        if not isinstance(classes, list) or not classes or len(classes) > 2 or not set(classes).issubset({"MAJOR_ELECTIVE", "MAJOR_REQUIRED"}):
            raise ValueError("Catalog aggregate classifications are not allowlisted")
    if query.get("intent") == "CONSISTENCY_CHECK" and query.get("operation") not in {"REPEAT", "INPUT_ORDER", "SIMULATION_IMMUTABILITY"}:
        raise ValueError("Consistency operation is not allowlisted")
    if query.get("intent") == "REMAINING_PLAN" and query.get("focus", "ALL") not in {"ALL", "MAJOR", "GENERAL", "MAJOR_REQUIRED"}:
        raise ValueError("Remaining plan focus is not allowlisted")
    if query.get("intent") == "COURSE_LOOKUP" and not query.get("course_id"):
        raise ValueError("course_id is required for this intent")
    if query.get("intent") == "WHAT_IF":
        added = query.get("added_course_ids", [query["course_id"]] if query.get("course_id") else [])
        if not isinstance(added, list) or len(added) > 10 or any(not isinstance(code, str) or not code for code in added):
            raise ValueError("Scenario course IDs must be a bounded list")
        if not added and query.get("target_selector") not in {"MISSING_REQUIRED_ONE", "MISSING_ZERO_CREDIT_REQUIRED_ONE",
                                                              "UNSPECIFIED_COURSE", "UNSPECIFIED_TWO_COURSES",
                                                              "CONTEXT_COURSE", "UNKNOWN_STUDENT_COURSE"}:
            raise ValueError("Scenario target or selector is required")
    if query.get("intent") == "WHAT_IF" and query.get("assumed_completion", "SUCCESS") != "SUCCESS":
        raise ValueError("Only successful hypothetical completion is supported")
    if "area" in query and (query["intent"] != "CREDIT_SUMMARY" or query["area"] not in {"MAJOR_TOTAL", "GENERAL_TOTAL", "GRADUATION_TOTAL"}):
        raise ValueError("CREDIT_SUMMARY area is not allowlisted")
    if student.get("program_type") not in PROGRAM_TYPES:
        raise ValueError("program_type must be SINGLE, MINOR, or DOUBLE")
    if student.get("completion_coverage") not in {"COMPLETE", "PARTIAL"}:
        raise ValueError("completion_coverage must be COMPLETE or PARTIAL")
    if student.get("applicability_status") not in STATUSES:
        raise ValueError("applicability_status is required")
    if student.get("department_id") != "DEPT-COMPUTER-ENGINEERING":
        raise ValueError("This prototype supports the computer-engineering department only")
    attempts = student.get("course_attempts")
    if not isinstance(attempts, list) or len(attempts) > 3000:
        raise ValueError("course_attempts must be a list")
    for attempt in attempts:
        if not isinstance(attempt, dict):
            raise ValueError("CourseAttempt must be an object")
        if not all(k in attempt for k in ("attempt_id", "completion_status", "verification_status", "evidence_id")):
            raise ValueError("CourseAttempt lacks required identity, status, or student evidence")
        if any(not isinstance(attempt[k], str) or not attempt[k].strip() for k in ("attempt_id", "evidence_id")):
            raise ValueError("CourseAttempt IDs and evidence must be nonempty strings")
        if attempt.get("course_id") is not None and (not isinstance(attempt["course_id"], str) or not attempt["course_id"].strip()):
            raise ValueError("CourseAttempt course_id must be a nonempty string or unresolved")
        if attempt["verification_status"] not in STATUSES:
            raise ValueError("Invalid CourseAttempt verification status")
        if attempt["completion_status"] not in {"COMPLETED", "IN_PROGRESS", "FAILED", "UNKNOWN"}:
            raise ValueError("Invalid CourseAttempt completion status")
        earned = attempt.get("earned_credits")
        if earned is not None and (type(earned) is not int or earned < 0):
            raise ValueError("earned_credits must be a nonnegative integer or null")
    free_records = student.get("free_choice_records", [])
    if not isinstance(free_records, list) or len(free_records) > 3000:
        raise ValueError("free_choice_records must be a list")
    for record in free_records:
        if not isinstance(record, dict) or any(not isinstance(record.get(key), str) or not record[key].strip()
                                                for key in ("record_id", "course_id", "evidence_id")):
            raise ValueError("Free-choice record needs identity, course, and evidence IDs")
        if record.get("source_category") not in FREE_CHOICE_CATEGORIES:
            raise ValueError("Free-choice source category is not allowed by the curriculum PDF")
        if record.get("verification_status") not in STATUSES:
            raise ValueError("Free-choice verification status is invalid")
        if record.get("recognition_status") not in STATUSES:
            raise ValueError("Free-choice official recognition status is required")
        if record.get("evidence_kind") != "OFFICIAL_TRANSCRIPT_RECOGNITION":
            raise ValueError("Free-choice credits require official transcript recognition evidence")
        if record.get("completion_status") not in {"COMPLETED", "IN_PROGRESS", "FAILED"}:
            raise ValueError("Free-choice completion status is required")
        if type(record.get("earned_credits")) is not int or record["earned_credits"] < 0:
            raise ValueError("Free-choice earned_credits must be nonnegative integer")


def _fetch_entry(graph: Graph, code: str, trace: list[dict], bundle: dict) -> dict | None:
    entry = graph.query("FETCH_CATALOG_ENTRY", curriculum_id="CURRICULUM-CE-2026", course_id=code)
    _event(trace, "GRAPH_QUERY", operation="FETCH_CATALOG_ENTRY", filters={"course_id": code, "curriculum_id": "CURRICULUM-CE-2026"},
           returned_ids=[] if not entry else [entry["entry_id"], entry["classification_id"], *entry["relationship_ids"]])
    if entry:
        _remember_entry(entry, bundle)
    return entry


def _remember_entry(entry: dict, bundle: dict) -> None:
    bundle["facts"][entry["entry_id"]] = entry
    bundle["nodes"]["CURRICULUM-CE-2026"] = {"id": "CURRICULUM-CE-2026", "kind": "CurriculumVersion", "label": "2026 컴퓨터공학과"}
    bundle["nodes"][entry["course_id"]] = {"id": entry["course_id"], "kind": "Course", "label": entry["name"]}
    bundle["nodes"][entry["entry_id"]] = {"id": entry["entry_id"], "kind": "CatalogEntry", "label": entry["course_id"] + " 편성행"}
    bundle["nodes"][entry["classification_id"]] = {"id": entry["classification_id"], "kind": "CourseClassification", "label": entry["classification"]}
    for relation in entry["relationship_ids"]:
        bundle["relationships"].add(relation)
    for relation in entry["relationship_details"]:
        bundle["relationship_details"][relation["id"]] = relation


def _catalog_aggregate(graph: Graph, query: dict, trace: list[dict], bundle: dict) -> dict:
    entries = graph.query("FETCH_CATALOG_SET", curriculum_id=query["curriculum_id"],
                          classifications=query["classifications"])
    assert isinstance(entries, list)
    _event(trace, "GRAPH_QUERY", operation="FETCH_CATALOG_SET",
           filters={"curriculum_id": query["curriculum_id"], "department_id": query["department_id"],
                    "classifications": query["classifications"], "verification_status": "VERIFIED"},
           returned_ids=[id for entry in entries for id in
                         (entry["entry_id"], entry["classification_id"], *entry["relationship_ids"])])
    for entry in entries:
        _remember_entry(entry, bundle)
    value = len(entries) if query["aggregate"] == "COUNT" else sum(entry["catalog_credits"] for entry in entries)
    _event(trace, "CATALOG_AGGREGATION", operation=query["aggregate"],
           input_refs=[entry["entry_id"] for entry in entries], result=value)
    result = {"operation": query["aggregate"], "value": value,
              "curriculum_id": query["curriculum_id"], "department_id": query["department_id"],
              "classifications": query["classifications"],
              "course_ids": [entry["course_id"] for entry in entries]}
    decision = {"contract_version": "1", "intent": "CATALOG_AGGREGATE", "decision_status": None,
                "graduation_outcome": "NOT_REQUESTED", "lookup_status": "FOUND",
                "lookup_result": result, "requirement_results": [], "credited_amount": None,
                "missing_amount": None, "missing_courses": None, "needs_information": [],
                "data_snapshot_id": graph.snapshot_id, "rule_set_hash": digest(graph.catalog["requirements"])}
    decision["canonical_result_hash"] = digest(decision)
    decision["decision_id"] = "DEC-" + decision["canonical_result_hash"][:16]
    _event(trace, "DECISION", result={"decision_id": decision["decision_id"], "lookup_status": "FOUND"})
    return decision


def _policy_rule_ids(catalog: dict, topic: str) -> list[str]:
    rules = catalog["requirements"]
    if topic == "ALL_REQUIREMENTS":
        return [r["rule_id"] for r in rules if r["verification_status"] == "VERIFIED"]
    if topic == "GRADUATION_CREDITS":
        return [r["rule_id"] for r in rules if r.get("area") == "GRADUATION_TOTAL"]
    if topic == "GENERAL_CREDITS":
        return [r["rule_id"] for r in rules if r["rule_id"].startswith("R-GE-") and r["rule_type"] in {"MIN_CREDITS", "CREDIT_CAP"}]
    if topic == "GENERAL_AREAS":
        return [r["rule_id"] for r in rules if r["rule_type"] == "ALL_AREAS"]
    if topic == "MAJOR_CREDITS":
        return [r["rule_id"] for r in rules if r["rule_id"].startswith("R-CE-") and r["rule_type"] == "MIN_CREDITS"]
    if topic == "REQUIRED_COURSES":
        return [r["rule_id"] for r in rules if r["rule_type"] == "REQUIRED_COURSES"]
    if topic == "GRADUATION_CONDITIONS":
        return [r["rule_id"] for r in rules if r["rule_type"] == "REQUIRED_EVIDENCE"]
    return []


def _policy_lookup(graph: Graph, student: dict, query: dict, trace: list[dict], bundle: dict) -> dict:
    topics = sorted(set(query["topics"]))
    program_type = query.get("program_type", student["program_type"])
    entry_year = query.get("entry_year", student.get("admission_year"))
    year_specific_rules_available = entry_year in (None, 2026)
    historical_needed = not year_specific_rules_available and bool(set(topics) & {"GRADUATION_CREDITS", "GENERAL_CREDITS", "MAJOR_CREDITS"})
    missing = []
    selected_rules: dict[str, dict] = {}
    selected_facts: dict[str, dict] = {}
    selected_courses: dict[str, dict] = {}
    bundle["nodes"]["CURRICULUM-CE-2026"] = {"id": "CURRICULUM-CE-2026", "kind": "CurriculumVersion", "label": "2026 컴퓨터공학과"}
    lookup_topics = list(topics)
    if not year_specific_rules_available and "APPLICABILITY" not in lookup_topics:
        lookup_topics.append("APPLICABILITY")
    if historical_needed and entry_year <= 2024 and "TRANSITION" not in lookup_topics:
        lookup_topics.append("TRANSITION")
    for topic in lookup_topics:
        if topic in POLICY_RULE_TOPICS:
            if not year_specific_rules_available:
                _event(trace, "POLICY_SCOPE_EXCLUDED", topic=topic, entry_year=entry_year,
                       reason="2026_RULES_NOT_VERIFIED_FOR_ENTRY_YEAR")
                continue
            candidate_ids = _policy_rule_ids(graph.catalog, topic)
            ids = [rule["rule_id"] for rule in graph.catalog["requirements"]
                   if rule["rule_id"] in candidate_ids and program_type in rule.get("program_types", PROGRAM_TYPES)
                   and (topic != "ALL_REQUIREMENTS" or rule["verification_status"] == "VERIFIED")]
            rules = graph.query("FETCH_REQUIREMENTS", curriculum_id="CURRICULUM-CE-2026", rule_ids=ids)
            _event(trace, "GRAPH_QUERY", operation="FETCH_REQUIREMENTS", filters={"topic": topic, "rule_ids": ids},
                   returned_ids=[r["rule_id"] for r in rules] + [r["relationship_id"] for r in rules])
            for rule in rules:
                selected_rules[rule["rule_id"]] = rule
                bundle["nodes"][rule["rule_id"]] = {"id": rule["rule_id"], "kind": "Requirement", "label": rule["rule_id"]}
                bundle["relationships"].add(rule["relationship_id"])
                bundle["relationship_details"][rule["relationship_id"]] = rule["relationship_detail"]
                if rule["rule_type"] == "REQUIRED_COURSES":
                    for code in rule["course_ids"]:
                        entry = _fetch_entry(graph, code, trace, bundle)
                        if entry and entry["verification_status"] == "VERIFIED":
                            selected_courses[code] = entry
        else:
            facts = graph.query("FETCH_POLICY_FACTS", curriculum_id="CURRICULUM-CE-2026", topic=topic)
            _event(trace, "GRAPH_QUERY", operation="FETCH_POLICY_FACTS", filters={"topic": topic},
                   returned_ids=[f["policy_fact_id"] for f in facts] + [f["relationship_id"] for f in facts])
            for fact in facts:
                if topic == "MULTI_PROGRAM" and fact["value"]["program_type"] != program_type:
                    _event(trace, "POLICY_SCOPE_EXCLUDED", topic=topic, policy_fact_id=fact["policy_fact_id"],
                           reason="DIFFERENT_PROGRAM_TYPE")
                    continue
                selected_facts[fact["policy_fact_id"]] = fact
                bundle["nodes"][fact["policy_fact_id"]] = {"id": fact["policy_fact_id"], "kind": "PolicyFact", "label": fact["predicate"]}
                bundle["relationships"].add(fact["relationship_id"])
                bundle["relationship_details"][fact["relationship_id"]] = fact["relationship_detail"]
    if historical_needed and program_type == "SINGLE":
        cid = f"CURRICULUM-CE-{entry_year}"
        facts = graph.query("FETCH_POLICY_FACTS", curriculum_id=cid, topic="HISTORICAL_CREDITS")
        _event(trace, "GRAPH_QUERY", operation="FETCH_POLICY_FACTS", filters={"topic": "HISTORICAL_CREDITS", "curriculum_id": cid},
               returned_ids=[f["policy_fact_id"] for f in facts] + [f["relationship_id"] for f in facts])
        for fact in facts:
            selected_facts[fact["policy_fact_id"]] = fact
            bundle["nodes"][cid] = {"id": cid, "kind": "CurriculumVersion", "label": f"{entry_year} 컴퓨터공학과"}
            bundle["nodes"][fact["policy_fact_id"]] = {"id": fact["policy_fact_id"], "kind": "PolicyFact", "label": fact["predicate"]}
            bundle["relationships"].add(fact["relationship_id"])
            bundle["relationship_details"][fact["relationship_id"]] = fact["relationship_detail"]
    if not year_specific_rules_available and set(topics) & POLICY_RULE_TOPICS and not any(
        fact["topic"] == "HISTORICAL_CREDITS" for fact in selected_facts.values()
    ):
        missing.append(f"APPLICABLE_CURRICULUM_RULES_FOR_ENTRY_YEAR:{entry_year}")
    bundle["rules"] = list(selected_rules.values())
    bundle["policy_facts"] = list(selected_facts.values())
    result = {"topics": topics, "program_type": program_type, "entry_year": entry_year,
              "rules": list(selected_rules.values()),
              "policy_facts": list(selected_facts.values()), "courses": list(selected_courses.values())}
    found = bool(selected_rules or selected_facts)
    decision = {"contract_version": "1", "intent": "POLICY_LOOKUP", "decision_status": None,
                "graduation_outcome": "NOT_REQUESTED", "lookup_status": "NEEDS_INFORMATION" if missing else "FOUND" if found else "NOT_FOUND",
                "lookup_result": result if found or missing else None, "requirement_results": [], "credited_amount": None,
                "missing_amount": None, "missing_courses": None, "needs_information": missing or ([] if found else ["VERIFIED_POLICY_TOPIC"]),
                "data_snapshot_id": graph.snapshot_id, "rule_set_hash": digest(graph.catalog["requirements"])}
    decision["canonical_result_hash"] = digest(decision)
    decision["decision_id"] = "DEC-" + decision["canonical_result_hash"][:16]
    _event(trace, "DECISION", result={"lookup_status": decision["lookup_status"]})
    return decision


def _recognize(student: dict, graph: Graph, trace: list[dict], bundle: dict, hypothetical: bool = False) -> dict:
    attempts = sorted(student["course_attempts"], key=lambda a: (a["attempt_id"], canonical(a)))
    unique = {}
    seen_ids = {}
    exclusions = []
    unknown = []
    for attempt in attempts:
        aid = attempt["attempt_id"]
        if aid in seen_ids:
            if attempt == seen_ids[aid]:
                exclusions.append({"attempt_id": aid, "reason": "DUPLICATE_RECORD_ID"})
            else:
                unique.pop(aid, None)
                unknown.append(f"CONFLICTED_ATTEMPT_ID:{aid}")
                exclusions.append({"attempt_id": aid, "reason": "CONFLICTED_RECORD_ID"})
            continue
        seen_ids[aid] = attempt
        if not attempt.get("course_id"):
            unknown.append(f"UNRESOLVED_COMPLETION_RECORD:{aid}:course_id")
            exclusions.append({"attempt_id": aid, "reason": "MISSING_COURSE_ID"})
            continue
        if attempt["completion_status"] == "UNKNOWN":
            unknown.append(f"COMPLETION_STATUS:{aid}")
            exclusions.append({"attempt_id": aid, "reason": "COMPLETION_STATUS_UNKNOWN"})
            continue
        if attempt["completion_status"] != "COMPLETED":
            exclusions.append({"attempt_id": aid, "reason": "NOT_COMPLETED"})
            continue
        unique[aid] = attempt
    counts = Counter(a["course_id"] for a in unique.values())
    credited = []
    completed_ids = set()
    for attempt in unique.values():
        code = attempt["course_id"]
        aid = attempt["attempt_id"]
        if counts[code] > 1:
            unknown.append(f"REPEAT_RESOLUTION:{code}")
            exclusions.append({"attempt_id": aid, "reason": "REPEAT_RESOLUTION_UNKNOWN"})
            continue
        if attempt["verification_status"] != "VERIFIED":
            unknown.append(f"STUDENT_EVIDENCE:{aid}")
            exclusions.append({"attempt_id": aid, "reason": "STUDENT_EVIDENCE_NOT_VERIFIED"})
            continue
        entry = _fetch_entry(graph, code, trace, bundle)
        if not entry:
            unknown.append(f"CATALOG_CLASSIFICATION:{code}")
            exclusions.append({"attempt_id": aid, "reason": "COURSE_NOT_IN_VERIFIED_2026_CATALOG"})
            continue
        if entry["verification_status"] != "VERIFIED" or entry["classification_verification_status"] != "VERIFIED":
            unknown.append(f"CATALOG_VERIFICATION:{code}")
            exclusions.append({"attempt_id": aid, "reason": "CATALOG_FACT_NOT_VERIFIED"})
            continue
        if entry["eligible_scope"] != "GENERAL":
            eligible = entry["eligible_scope"] == "FOREIGN_ONLY" and student.get("student_category") == "FOREIGN"
            if not eligible:
                unknown.append(f"COURSE_ELIGIBILITY:{code}")
                exclusions.append({"attempt_id": aid, "reason": "COURSE_SCOPE_NEEDS_OFFICIAL_REVIEW"})
                continue
        earned = attempt.get("earned_credits")
        if earned is not None and earned != entry["catalog_credits"]:
            unknown.append(f"CREDIT_MISMATCH:{aid}")
            exclusions.append({"attempt_id": aid, "reason": "STUDENT_CREDIT_DIFFERS_FROM_CATALOG"})
            continue
        recognition = {"recognition_id": f"REC-{aid}", "attempt_id": aid, "course_id": code,
                       "credits": entry["catalog_credits"], "classification": entry["classification"],
                       "general_area": entry["general_area"],
                       "fact_id": entry["fact_id"], "entry_id": entry["entry_id"],
                       "relationship_ids": entry["relationship_ids"], "student_evidence_id": attempt["evidence_id"],
                       "hypothetical": hypothetical and aid.startswith("SCENARIO-")}
        credited.append(recognition)
        completed_ids.add(code)
        _event(trace, "CREDIT_RECOGNITION", input_refs=[aid, attempt["evidence_id"], entry["fact_id"], *entry["relationship_ids"]],
               result={"recognition_id": recognition["recognition_id"], "credits": recognition["credits"],
                       "classification": recognition["classification"], "hypothetical": recognition["hypothetical"]})
    free_records = sorted(student.get("free_choice_records", []), key=lambda r: (r["record_id"], canonical(r)))
    if free_records:
        facts = graph.query("FETCH_POLICY_FACTS", curriculum_id="CURRICULUM-CE-2026", topic="FREE_CHOICE")
        _event(trace, "GRAPH_QUERY", operation="FETCH_POLICY_FACTS", filters={"topic": "FREE_CHOICE"},
               returned_ids=[f["policy_fact_id"] for f in facts] + [f["relationship_id"] for f in facts])
        fact = next((f for f in facts if f["predicate"] == "COUNTS_AS_RESIDUAL" and f["verification_status"] == "VERIFIED"), None)
        if fact:
            bundle["nodes"]["CURRICULUM-CE-2026"] = {"id": "CURRICULUM-CE-2026", "kind": "CurriculumVersion", "label": "2026 컴퓨터공학과"}
            bundle["nodes"][fact["policy_fact_id"]] = {"id": fact["policy_fact_id"], "kind": "PolicyFact", "label": fact["predicate"]}
            bundle["relationships"].add(fact["relationship_id"])
            bundle["relationship_details"][fact["relationship_id"]] = fact["relationship_detail"]
            if not any(item["policy_fact_id"] == fact["policy_fact_id"] for item in bundle["policy_facts"]):
                bundle["policy_facts"].append(fact)
            bundle["facts"][fact["policy_fact_id"]] = {"fact_id": fact["policy_fact_id"],
                                                       "source_refs": fact["source_refs"],
                                                       "verification_status": fact["verification_status"]}
        else:
            unknown.append("VERIFIED_FREE_CHOICE_POLICY")
        record_counts = Counter(r["record_id"] for r in free_records)
        course_counts = Counter(r["course_id"] for r in free_records if r["completion_status"] == "COMPLETED")
        known_codes = {c["course_id"] for c in graph.catalog["courses"]}
        all_attempt_codes = {a.get("course_id") for a in student["course_attempts"] if a.get("course_id")}
        for record in free_records:
            rid, code = record["record_id"], record["course_id"]
            if record["completion_status"] != "COMPLETED":
                exclusions.append({"attempt_id": rid, "reason": "FREE_CHOICE_NOT_COMPLETED"})
                continue
            if rid in seen_ids or record_counts[rid] > 1 or course_counts[code] > 1 or code in all_attempt_codes or code in known_codes or code.startswith(("CDA", "GEA")):
                unknown.append(f"FREE_CHOICE_DUPLICATE_OR_CLASSIFICATION:{code}")
                exclusions.append({"attempt_id": rid, "reason": "FREE_CHOICE_OVERLAP_NEEDS_REVIEW"})
                continue
            if record["verification_status"] != "VERIFIED" or record["recognition_status"] != "VERIFIED":
                unknown.append(f"OFFICIAL_FREE_CHOICE_RECOGNITION:{rid}")
                exclusions.append({"attempt_id": rid, "reason": "FREE_CHOICE_EVIDENCE_NOT_VERIFIED"})
                continue
            if not fact or record["source_category"] not in fact["value"]["includes"]:
                unknown.append(f"FREE_CHOICE_POLICY_SCOPE:{rid}")
                exclusions.append({"attempt_id": rid, "reason": "FREE_CHOICE_POLICY_NOT_VERIFIED"})
                continue
            recognition = {"recognition_id": f"REC-{rid}", "attempt_id": rid, "course_id": code,
                           "credits": record["earned_credits"], "classification": "FREE_CHOICE", "general_area": None,
                           "fact_id": fact["policy_fact_id"], "entry_id": None,
                           "relationship_ids": [fact["relationship_id"]],
                           "student_evidence_id": record["evidence_id"], "hypothetical": False}
            credited.append(recognition)
            _event(trace, "CREDIT_RECOGNITION", input_refs=[rid, record["evidence_id"], fact["policy_fact_id"], fact["relationship_id"]],
                   result={"recognition_id": recognition["recognition_id"], "credits": recognition["credits"],
                           "classification": "FREE_CHOICE", "hypothetical": False})
    for exclusion in exclusions:
        _event(trace, "CANDIDATE_EXCLUDED", **exclusion)
    if student["completion_coverage"] != "COMPLETE":
        unknown.append("COMPLETE_STUDENT_TRANSCRIPT")
    return {"recognitions": credited, "completed_ids": completed_ids,
            "needs_information": sorted(set(unknown)), "excluded": exclusions,
            "complete": student["completion_coverage"] == "COMPLETE" and not unknown}


def _evaluate_rules(student: dict, graph: Graph, recognition: dict, trace: list[dict], bundle: dict) -> tuple[list[dict], dict, set[str]]:
    rules = graph.query("FETCH_REQUIREMENTS", curriculum_id="CURRICULUM-CE-2026")
    _event(trace, "GRAPH_QUERY", operation="FETCH_REQUIREMENTS", filters={"curriculum_id": "CURRICULUM-CE-2026"},
           returned_ids=[item["rule_id"] for item in rules] + [item["relationship_id"] for item in rules])
    bundle["rules"] = rules
    bundle["relationships"].update(item["relationship_id"] for item in rules)
    bundle["nodes"]["CURRICULUM-CE-2026"] = {"id": "CURRICULUM-CE-2026", "kind": "CurriculumVersion", "label": "2026 컴퓨터공학과"}
    for item in rules:
        bundle["nodes"][item["rule_id"]] = {"id": item["rule_id"], "kind": "Requirement", "label": item["rule_id"]}
        bundle["relationship_details"][item["relationship_id"]] = item["relationship_detail"]
    sums = {"MAJOR_REQUIRED": 0, "MAJOR_ELECTIVE": 0, "MAJOR_TOTAL": 0,
            "GENERAL_BASIC": 0, "GENERAL_BALANCED": 0, "GENERAL_EXPANDED": 0, "GENERAL_TOTAL": 0,
            "MAJOR_ADVANCED": 0, "FREE_CHOICE": 0, "GRADUATION_TOTAL": 0}
    for rec in recognition["recognitions"]:
        sums[rec["classification"]] += rec["credits"]
        if rec["classification"].startswith("MAJOR_"):
            sums["MAJOR_TOTAL"] += rec["credits"]
        if rec["classification"].startswith("GENERAL_"):
            sums["GENERAL_TOTAL"] += rec["credits"]
    advanced_rule = next((rule for rule in rules if rule.get("area") == "MAJOR_ADVANCED"), None)
    cap_rule = next((rule for rule in rules if rule["rule_type"] == "CREDIT_CAP" and rule["area"] == "GENERAL_TOTAL"), None)
    base_major = advanced_rule["base_major_credits"] if advanced_rule else 0
    general_cap = cap_rule["required_value"] if cap_rule else 0
    unsafe_derived = set()
    if not advanced_rule or advanced_rule["verification_status"] != "VERIFIED":
        unsafe_derived.add("MAJOR_ADVANCED")
    if not cap_rule or cap_rule["verification_status"] != "VERIFIED":
        unsafe_derived.add("GRADUATION_TOTAL")
    sums["MAJOR_ADVANCED"] = max(0, sums["MAJOR_TOTAL"] - base_major)
    sums["GRADUATION_TOTAL"] = sums["MAJOR_TOTAL"] + min(general_cap, sums["GENERAL_TOTAL"]) + sums["FREE_CHOICE"]
    if cap_rule and cap_rule["verification_status"] == "VERIFIED" and sums["GENERAL_TOTAL"] > general_cap:
        _event(trace, "CREDIT_CAP", rule_id=cap_rule["rule_id"], operands={"raw_general": sums["GENERAL_TOTAL"], "cap": general_cap},
               result={"graduation_counted_general": general_cap, "excluded_credits": sums["GENERAL_TOTAL"] - general_cap})
    results = []
    for rule in rules:
        rid = rule["rule_id"]
        applicability = scope_status(rule.get("effective_scope", {}), student)
        applies = applicability != "NOT_APPLICABLE" and student["program_type"] in rule.get("program_types", PROGRAM_TYPES)
        general_rule = rid.startswith("R-GE-") or rid.startswith("R-GRAD-")
        if not applies:
            result = {"requirement_id": rid, "rule_id": rid, "status": "NOT_APPLICABLE", "observed": None,
                      "required": rule.get("required_value"), "missing_amount": None, "missing_course_ids": None,
                      "used_fact_ids": [], "used_relationship_ids": [rule["relationship_id"]],
                      "used_student_evidence_ids": [], "needs_information": [], "source_refs": rule["source_refs"]}
        elif applicability == "NEEDS_INFORMATION":
            result = {"requirement_id": rid, "rule_id": rid, "status": "NEEDS_INFORMATION", "observed": None,
                      "required": rule.get("required_value"), "missing_amount": None, "missing_course_ids": None,
                      "used_fact_ids": [], "used_relationship_ids": [rule["relationship_id"]],
                      "used_student_evidence_ids": [], "needs_information": [f"RULE_APPLICABILITY:{rid}"], "source_refs": rule["source_refs"]}
        elif general_rule and (student.get("student_category") != "DOMESTIC_REGULAR" or not student.get("student_category_evidence_id")):
            result = {"requirement_id": rid, "rule_id": rid, "status": "NEEDS_INFORMATION", "observed": None,
                      "required": rule.get("required_value"), "missing_amount": None, "missing_course_ids": None,
                      "used_fact_ids": [], "used_relationship_ids": [rule["relationship_id"]],
                      "used_student_evidence_ids": [], "needs_information": ["VERIFIED_STUDENT_CATEGORY_AND_EXCEPTIONS"], "source_refs": rule["source_refs"]}
        elif rule["verification_status"] != "VERIFIED" or rule.get("area") in unsafe_derived:
            result = {"requirement_id": rid, "rule_id": rid, "status": "NEEDS_INFORMATION", "observed": None,
                      "required": rule.get("required_value"), "missing_amount": None, "missing_course_ids": None,
                      "used_fact_ids": [], "used_relationship_ids": [rule["relationship_id"]],
                      "used_student_evidence_ids": [], "needs_information": [f"RULE_VERIFICATION:{rid}"], "source_refs": rule["source_refs"]}
        else:
            if rule["rule_type"] == "MIN_CREDITS":
                area = rule["area"]
                used = [r for r in recognition["recognitions"] if
                        (area in {"MAJOR_TOTAL", "MAJOR_ADVANCED"} and r["classification"].startswith("MAJOR_"))
                        or (area in {"GENERAL_TOTAL", "GRADUATION_TOTAL"} and (r["classification"].startswith("GENERAL_") or area == "GRADUATION_TOTAL"))
                        or r["classification"] == area]
                observed = sums[area]
                threshold = rule["required_value"]
                if observed >= threshold:
                    status = "SATISFIED"
                elif recognition["complete"]:
                    status = "UNSATISFIED"
                else:
                    status = "NEEDS_INFORMATION"
                missing = max(0, threshold - observed) if recognition["complete"] else None
                missing_ids = None
            elif rule["rule_type"] == "REQUIRED_COURSES":
                used = [r for r in recognition["recognitions"] if r["course_id"] in rule["course_ids"]]
                missing_ids = sorted(set(rule["course_ids"]) - recognition["completed_ids"])
                observed = len(rule["course_ids"]) - len(missing_ids)
                threshold = len(rule["course_ids"])
                if not missing_ids:
                    status = "SATISFIED"
                elif recognition["complete"]:
                    status = "UNSATISFIED"
                else:
                    status = "NEEDS_INFORMATION"
                if not recognition["complete"]:
                    missing_ids = None
                missing = None
            elif rule["rule_type"] in {"ANY_COURSE", "ANY_COURSE_OR_EXEMPTION"}:
                used = [r for r in recognition["recognitions"] if r["course_id"] in rule["course_ids"]]
                observed = len(used)
                threshold = 1
                exemption = student.get("official_outcomes", {}).get("english_course_exemption") if rule["rule_type"] == "ANY_COURSE_OR_EXEMPTION" else None
                exempted = bool(exemption and exemption.get("verification_status") == "VERIFIED" and exemption.get("value") is True and exemption.get("evidence_id"))
                if used or exempted:
                    status = "SATISFIED"
                elif rule["rule_type"] == "ANY_COURSE_OR_EXEMPTION" and (not exemption or exemption.get("verification_status") != "VERIFIED"):
                    status = "NEEDS_INFORMATION"
                elif recognition["complete"]:
                    status = "UNSATISFIED"
                else:
                    status = "NEEDS_INFORMATION"
                missing_ids = None if status == "NEEDS_INFORMATION" else [] if status == "SATISFIED" else rule["course_ids"]
                missing = None
            elif rule["rule_type"] == "ALL_AREAS":
                used = [r for r in recognition["recognitions"] if r["general_area"] in rule["areas"]]
                present = {r["general_area"] for r in used}
                observed = len(present)
                threshold = len(rule["areas"])
                status = "SATISFIED" if observed == threshold else "UNSATISFIED" if recognition["complete"] else "NEEDS_INFORMATION"
                missing_ids = None
                missing = None
            elif rule["rule_type"] == "CREDIT_CAP":
                used = [r for r in recognition["recognitions"] if r["classification"].startswith("GENERAL_")]
                observed = sums["GENERAL_TOTAL"]
                threshold = rule["required_value"]
                status = "SATISFIED" if recognition["complete"] else "NEEDS_INFORMATION"
                missing_ids = None
                missing = None
            elif rule["rule_type"] == "REQUIRED_EVIDENCE":
                used = []
                evidence = student.get("official_outcomes", {}).get(rule["evidence_key"])
                observed = evidence.get("value") if evidence and evidence.get("verification_status") == "VERIFIED" and evidence.get("evidence_id") else None
                threshold = True
                status = "SATISFIED" if observed is True else "UNSATISFIED" if observed is False else "NEEDS_INFORMATION"
                missing_ids = None
                missing = None
            else:
                raise ValueError(f"Unsupported verified rule type: {rule['rule_type']}")
            result = {"requirement_id": rid, "rule_id": rid, "status": status, "observed": observed,
                      "required": threshold, "missing_amount": missing, "missing_course_ids": missing_ids,
                      "used_fact_ids": [r["fact_id"] for r in used],
                      "used_relationship_ids": [rule["relationship_id"], *[e for r in used for e in r["relationship_ids"]]],
                      "used_student_evidence_ids": [r["student_evidence_id"] for r in used] +
                          ([evidence["evidence_id"]] if rule["rule_type"] == "REQUIRED_EVIDENCE" and evidence and evidence.get("verification_status") == "VERIFIED" and evidence.get("evidence_id") else []) +
                          ([exemption["evidence_id"]] if rule["rule_type"] == "ANY_COURSE_OR_EXEMPTION" and exempted and exemption.get("evidence_id") else []),
                      "needs_information": [] if status != "NEEDS_INFORMATION" else recognition["needs_information"] or [f"RULE_INPUT:{rid}"],
                      "source_refs": rule["source_refs"]}
        result["execution_event_ids"] = [_event(trace, "RULE_EVALUATION", rule_id=rid,
                                                   operands={"observed": result["observed"], "required": result["required"]},
                                                   calculation=rule.get("calculation", rule["rule_type"]),
                                                   input_refs=result["used_fact_ids"] + result["used_student_evidence_ids"],
                                                   result=result["status"])]
        results.append(result)
    return results, sums, unsafe_derived


def _one_decision(student: dict, graph: Graph, query: dict, trace: list[dict], bundle: dict, hypothetical: bool = False) -> dict:
    recognition = _recognize(student, graph, trace, bundle, hypothetical)
    results, sums, unsafe_derived = _evaluate_rules(student, graph, recognition, trace, bundle)
    missing_codes = {code for result in results for code in (result["missing_course_ids"] or [])}
    for code in sorted(missing_codes):
        _fetch_entry(graph, code, trace, bundle)
    applicable = [r for r in results if r["status"] != "NOT_APPLICABLE"]
    if any(r["status"] == "UNSATISFIED" for r in applicable):
        decision_status = "UNSATISFIED"
    elif any(r["status"] == "NEEDS_INFORMATION" for r in applicable):
        decision_status = "NEEDS_INFORMATION"
    else:
        decision_status = "SATISFIED"
    needs = sorted(set(recognition["needs_information"] + [n for r in results for n in r["needs_information"]]))
    missing_core_rules = sorted(CORE_SINGLE_RULE_IDS - {r["rule_id"] for r in results})
    coverage_complete = (student["program_type"] == "SINGLE"
                         and student.get("student_category") == "DOMESTIC_REGULAR"
                         and bool(student.get("student_category_evidence_id"))
                         and bool(student.get("applicability_evidence_id"))
                         and bool(student.get("completion_coverage_evidence_id"))
                         and not student.get("academic_events")
                         and recognition["complete"]
                         and not missing_core_rules
                         and student.get("equivalence_review_status") == "VERIFIED"
                         and bool(student.get("equivalence_review_evidence_id")))
    if query["intent"] == "GRADUATION_STATUS":
        coverage_gaps = []
        if student["program_type"] != "SINGLE":
            coverage_gaps.append("SECOND_PROGRAM_RULE_COVERAGE")
        coverage_gaps.extend(f"RULE_NOT_LOADED:{rule_id}" for rule_id in missing_core_rules)
        if student.get("student_category") != "DOMESTIC_REGULAR" or not student.get("student_category_evidence_id"):
            coverage_gaps.append("VERIFIED_STUDENT_CATEGORY_AND_EXCEPTIONS")
        if not student.get("applicability_evidence_id"):
            coverage_gaps.append("VERIFIED_APPLICABILITY_EVIDENCE")
        if student["completion_coverage"] != "COMPLETE" or not student.get("completion_coverage_evidence_id"):
            coverage_gaps.append("COMPLETE_VERIFIED_TRANSCRIPT_EVIDENCE")
        if student.get("academic_events"):
            coverage_gaps.append("ACADEMIC_EVENT_APPLICABILITY_REVIEW")
        if student.get("equivalence_review_status") != "VERIFIED" or not student.get("equivalence_review_evidence_id"):
            coverage_gaps.append("OFFICIAL_EQUIVALENCE_REVIEW")
        _event(trace, "COVERAGE_CHECK", result="COMPLETE" if coverage_complete else "INCOMPLETE",
               missing=coverage_gaps)
        if decision_status == "UNSATISFIED":
            graduation = "NOT_ELIGIBLE_PDF"
        elif decision_status == "SATISFIED" and coverage_complete:
            graduation = "ELIGIBLE_PDF"
        else:
            graduation = "UNKNOWN"
        if not coverage_complete:
            needs.append("COMPLETE_VERIFIED_SINGLE_MAJOR_RULE_COVERAGE")
            needs.extend(coverage_gaps)
        if student["program_type"] != "SINGLE":
            needs.extend(f"RULE_FAMILY:{family}" for family in graph.catalog["coverage_manifest"]["missing_families"])
    else:
        graduation = "NOT_REQUESTED"
    decision = {"contract_version": "1", "intent": query["intent"], "decision_status": decision_status,
                "graduation_outcome": graduation, "requirement_results": results,
                "requested_area": query.get("area") if query["intent"] == "CREDIT_SUMMARY" else None,
                "credited_amount": {"total": sums["GRADUATION_TOTAL"] if recognition["complete"] and "GRADUATION_TOTAL" not in unsafe_derived else None,
                                    "confirmed_minimum": sums["MAJOR_TOTAL"] if "GRADUATION_TOTAL" in unsafe_derived else sums["GRADUATION_TOTAL"],
                                    "status": "COMPLETE" if recognition["complete"] and "GRADUATION_TOTAL" not in unsafe_derived else "PARTIAL",
                                    "by_area": {**sums, **{area: None for area in unsafe_derived}}},
                "missing_amount": {r["rule_id"]: r["missing_amount"] for r in applicable if r["rule_id"].endswith("CREDITS") or r["rule_id"].endswith("MINIMUM")},
                "missing_courses": next((r["missing_course_ids"] for r in results if r["rule_id"] == "R-CE-2026-REQUIRED-COURSES"), None),
                "needs_information": sorted(set(needs)),
                "recognitions": recognition["recognitions"], "excluded": recognition["excluded"],
                "data_snapshot_id": graph.snapshot_id, "rule_set_hash": digest(graph.catalog["requirements"]),
                "hypothetical": hypothetical, "coverage_complete": coverage_complete}
    decision["canonical_result_hash"] = digest(decision)
    decision["decision_id"] = "DEC-" + decision["canonical_result_hash"][:16]
    _event(trace, "DECISION", result={"decision_id": decision["decision_id"], "status": decision_status,
                                       "graduation_outcome": graduation})
    return decision


def _rehash_decision(decision: dict) -> None:
    decision.pop("canonical_result_hash", None)
    decision.pop("decision_id", None)
    decision["canonical_result_hash"] = digest(decision)
    decision["decision_id"] = "DEC-" + decision["canonical_result_hash"][:16]


def _pin_ruleset(decision: dict, graph: Graph, student_version: str, student: dict) -> None:
    document_set = graph.catalog["authoritative_document_set"]
    ruleset = graph.catalog["curriculum_ruleset"]
    decision.update({"student_state_version": student_version,
                     "authoritative_document_set_id": document_set["set_id"],
                     "authoritative_document_set_version": document_set["set_version"],
                     "ruleset_id": ruleset["ruleset_id"], "ruleset_version": ruleset["ruleset_version"],
                     "applicable_rule_ids": sorted(rule["rule_id"] for rule in graph.catalog["requirements"]
                                                   if scope_applies(rule.get("effective_scope", {}), student)),
                     "unresolved_conflict_ids": sorted(c["conflict_id"] for c in ruleset["unresolved_conflicts"]
                                                       if scope_applies(c["affected_scope"], student))})
    _rehash_decision(decision)


def _scenario_targets(student: dict, graph: Graph, query: dict, actual: dict,
                      trace: list[dict], bundle: dict) -> tuple[list[str], list[str], str | None]:
    explicit = query.get("added_course_ids", [query["course_id"]] if query.get("course_id") else [])
    if explicit:
        targets = sorted(set(explicit))
        unknown = []
        for code in targets:
            entry = _fetch_entry(graph, code, trace, bundle)
            if not entry or entry["verification_status"] != "VERIFIED" or entry["classification_verification_status"] != "VERIFIED":
                unknown.append(code)
        return (targets, [], None) if not unknown else ([], unknown, "VERIFIED_SIMULATION_COURSE_REQUIRED")
    selector = query.get("target_selector")
    missing = actual.get("missing_courses")
    if selector in {"MISSING_REQUIRED_ONE", "MISSING_ZERO_CREDIT_REQUIRED_ONE"}:
        if missing is None:
            return [], [], "COMPLETE_STUDENT_TRANSCRIPT_FOR_TARGET_RESOLUTION"
        candidates = missing
        if selector == "MISSING_ZERO_CREDIT_REQUIRED_ONE":
            candidates = [code for code in missing if
                          (entry := _fetch_entry(graph, code, trace, bundle)) and
                          entry["verification_status"] == "VERIFIED" and entry["catalog_credits"] == 0]
        if len(candidates) == 1:
            return candidates, candidates, None
        return [], candidates, "SIMULATION_TARGET_AMBIGUOUS" if candidates else "NO_MISSING_REQUIRED_TARGET"
    if selector == "UNKNOWN_STUDENT_COURSE":
        known = {c["course_id"] for c in graph.catalog["courses"] if c["verification_status"] == "VERIFIED"}
        candidates = sorted({a.get("course_id") for a in student["course_attempts"] if a.get("course_id") and a["course_id"] not in known})
        for code in candidates:
            _fetch_entry(graph, code, trace, bundle)
        return [], candidates, "VERIFIED_SIMULATION_COURSE_REQUIRED"
    if selector == "CONTEXT_COURSE":
        return [], [], "PRIOR_COURSE_REFERENCE_REQUIRED"
    candidates = missing if isinstance(missing, list) else []
    return [], candidates, "SIMULATION_TARGET_COURSE_IDS_REQUIRED"


def _consistency_check(graph: Graph, student: dict, query: dict) -> dict:
    """Run the real decision path twice; report only observed equality."""
    operation = query["operation"]
    probe_course = None
    if operation == "SIMULATION_IMMUTABILITY":
        audit = execute(graph, student, {"intent": "REQUIREMENT_GAPS"})
        candidates = audit["decision"].get("missing_courses") or []
        if len(candidates) == 1:
            probe_course = candidates[0]
        else:
            verified = sorted(c["course_id"] for c in graph.catalog["courses"]
                              if c["verification_status"] == "VERIFIED"
                              and c["course_id"] not in {a.get("course_id") for a in student["course_attempts"]})
            probe_course = verified[0] if verified else None
        base_query = {"intent": "WHAT_IF", "course_id": probe_course,
                      "assumed_completion": "SUCCESS"} if probe_course else {"intent": "REQUIREMENT_GAPS"}
    else:
        base_query = {"intent": "GRADUATION_STATUS"}
    unchanged = deepcopy(student)
    first = execute(graph, student, base_query)
    second_state = deepcopy(student)
    if operation == "INPUT_ORDER":
        second_state["course_attempts"].reverse()
        second_state["free_choice_records"] = list(reversed(second_state.get("free_choice_records", [])))
    second = execute(graph, second_state, base_query)
    consistent = (student == unchanged and first["decision"] == second["decision"]
                  and first.get("scenario_decision") == second.get("scenario_decision")
                  and first["evidence"] == second["evidence"]
                  and first["execution_trace"]["events"] == second["execution_trace"]["events"])
    payload = deepcopy(first)
    decision = payload["decision"]
    first_id, second_id = first["decision"]["decision_id"], second["decision"]["decision_id"]
    underlying = {key: decision[key] for key in ("decision_status", "coverage_complete", "unresolved_conflict_ids")}
    decision.update({"intent": "CONSISTENCY_CHECK", "graduation_outcome": "NOT_REQUESTED",
                     "decision_status": "SATISFIED" if consistent and probe_course is not None or
                                        consistent and operation != "SIMULATION_IMMUTABILITY" else "NEEDS_INFORMATION",
                     "lookup_status": "FOUND" if consistent else "NEEDS_INFORMATION",
                     "lookup_result": {"operation": operation, "consistent": consistent,
                                       "first_decision_id": first_id, "second_decision_id": second_id,
                                       "probe_course_id": probe_course, "student_state_unchanged": student == unchanged,
                                       "underlying_decision": underlying},
                     "needs_information": ([] if consistent and (operation != "SIMULATION_IMMUTABILITY" or probe_course)
                                           else ["CONSISTENCY_PROBE_COURSE_REQUIRED" if probe_course is None else "CONSISTENCY_CHECK_FAILED"])})
    _rehash_decision(decision)
    trace = payload["execution_trace"]
    trace["decision_id"] = decision["decision_id"]
    for event in trace["events"]:
        if event["event_type"] == "DECISION" and not event.get("hypothetical"):
            event["result"]["decision_id"] = decision["decision_id"]
            if "status" in event["result"]:
                event["result"]["status"] = decision["decision_status"]
            break
    canonical_student = {**student,
                         "course_attempts": sorted(student["course_attempts"], key=lambda a: (a["attempt_id"], canonical(a))),
                         "free_choice_records": sorted(student.get("free_choice_records", []),
                                                       key=lambda r: (r["record_id"], canonical(r)))}
    trace["execution_id"] = "EX-" + digest({"student": canonical_student, "query": query,
                                               "snapshot": graph.snapshot_id})[:16]
    plan = next(e for e in trace["events"] if e["event_type"] == "QUERY_PLAN")
    plan["intent"] = "CONSISTENCY_CHECK"
    plan["operations"] = [*plan["operations"], "COMPARE_DECISIONS"]
    _event(trace["events"], "CONSISTENCY_CHECK", operation=operation,
           input_refs=[first_id, second_id], result={"consistent": consistent,
                                                    "student_state_unchanged": student == unchanged,
                                                    "probe_course_id": probe_course})
    payload["needs_information"] = decision["needs_information"]
    from .render import render_answer
    from .verifier import verify_payload
    payload["answer_text"] = render_answer(payload)
    verify_payload(payload)
    return payload


def execute(graph: Graph, student: dict, query: dict) -> dict:
    """Run a validated StructuredQuery; never accepts free SQL/Cypher or rule values."""
    _validate(student, query)
    if query["intent"] == "CONSISTENCY_CHECK":
        return _consistency_check(graph, student, query)
    trace: list[dict] = []
    bundle: dict = {"facts": {}, "relationships": set(), "relationship_details": {}, "nodes": {},
                    "rules": [], "policy_facts": [], "source_locators": {}, "student_evidence_refs": []}
    # Transcript and official residual records are sets of identified records;
    # their JSON array order must not change an execution identifier.
    canonical_student = {**student,
                         "course_attempts": sorted(student["course_attempts"],
                                                   key=lambda a: (a["attempt_id"], canonical(a))),
                         "free_choice_records": sorted(student.get("free_choice_records", []),
                                                       key=lambda r: (r["record_id"], canonical(r)))}
    canonical_query = {**query}
    if "added_course_ids" in canonical_query:
        canonical_query["added_course_ids"] = sorted(set(canonical_query["added_course_ids"]))
    input_id = digest({"student": canonical_student, "query": canonical_query, "snapshot": graph.snapshot_id})[:16]
    student_version = digest(canonical_student)
    document_set = graph.catalog["authoritative_document_set"]
    ruleset = graph.catalog["curriculum_ruleset"]
    if query["intent"] == "POLICY_LOOKUP":
        topics = set(query["topics"])
        entry_year = query.get("entry_year", student.get("admission_year"))
        scoped_rule_topics = topics & POLICY_RULE_TOPICS if entry_year in (None, 2026) else set()
        operations = ([] if not scoped_rule_topics else ["FETCH_REQUIREMENTS"])
        if "REQUIRED_COURSES" in scoped_rule_topics:
            operations.append("FETCH_CATALOG_ENTRY")
        if topics & POLICY_FACT_TOPICS or (not scoped_rule_topics and bool(topics & POLICY_RULE_TOPICS)):
            operations.append("FETCH_POLICY_FACTS")
    elif query["intent"] == "CATALOG_AGGREGATE":
        operations = ["FETCH_CATALOG_SET", "AGGREGATE_" + query["aggregate"]]
    elif query["intent"] == "REMAINING_PLAN":
        operations = ["FETCH_CATALOG_ENTRY", "FETCH_REQUIREMENTS", "FETCH_CATALOG_SET",
                      "FETCH_COURSE_REQUIREMENT_LINKS", "SUMMARIZE_REMAINING", "CLASSIFY_CANDIDATES"]
    else:
        operations = ["FETCH_CATALOG_ENTRY"] if query["intent"] == "COURSE_LOOKUP" else ["FETCH_CATALOG_ENTRY", "FETCH_REQUIREMENTS"]
    _event(trace, "QUERY_PLAN", intent=query["intent"], operations=operations, input_hash=input_id,
           authoritative_document_set_id=document_set["set_id"],
           authoritative_document_set_version=document_set["set_version"],
           ruleset_id=ruleset["ruleset_id"], ruleset_version=ruleset["ruleset_version"],
           student_state_version=student_version, candidate_rule_ids=ruleset["included_rule_ids"],
           document_relation_ids=[r["relation_id"] for r in graph.catalog["document_relations"]])
    scenario_decision = None
    if query["intent"] == "POLICY_LOOKUP":
        decision = _policy_lookup(graph, student, query, trace, bundle)
    elif query["intent"] == "CATALOG_AGGREGATE":
        decision = _catalog_aggregate(graph, query, trace, bundle)
    elif student["applicability_status"] != "VERIFIED" or student.get("credit_policy_year") != 2026 or student.get("catalog_year") != 2026:
        needs = ["VERIFIED_2026_CREDIT_AND_CATALOG_APPLICABILITY"]
        decision = {"contract_version": "1", "intent": query["intent"], "decision_status": "NEEDS_INFORMATION",
                    "graduation_outcome": "UNKNOWN" if query["intent"] == "GRADUATION_STATUS" else "NOT_REQUESTED",
                    "requirement_results": [], "credited_amount": None, "missing_amount": None,
                    "missing_courses": None, "needs_information": needs,
                    "data_snapshot_id": graph.snapshot_id, "rule_set_hash": digest(graph.catalog["requirements"])}
        if query["intent"] == "GRADUATION_STATUS":
            decision["coverage_complete"] = False
            _event(trace, "COVERAGE_CHECK", result="INCOMPLETE", missing=needs)
        decision["canonical_result_hash"] = digest(decision)
        decision["decision_id"] = "DEC-" + decision["canonical_result_hash"][:16]
        _event(trace, "APPLICABILITY", result="NEEDS_INFORMATION", missing=needs)
        _event(trace, "DECISION", result={"decision_id": decision["decision_id"],
                                           "status": "NEEDS_INFORMATION",
                                           "graduation_outcome": decision["graduation_outcome"]})
    elif query["intent"] == "COURSE_LOOKUP":
        entry = _fetch_entry(graph, query["course_id"], trace, bundle)
        verified_entry = entry and entry["verification_status"] == "VERIFIED" and entry["classification_verification_status"] == "VERIFIED"
        lookup_status = "FOUND" if verified_entry else "NEEDS_INFORMATION" if entry else "NOT_FOUND"
        decision = {"contract_version": "1", "intent": "COURSE_LOOKUP", "decision_status": None,
                    "graduation_outcome": "NOT_REQUESTED", "lookup_status": lookup_status,
                    "lookup_result": entry if verified_entry else None, "requirement_results": [], "credited_amount": None,
                    "missing_amount": None, "missing_courses": None, "needs_information": [] if not entry or verified_entry else [f"CATALOG_VERIFICATION:{query['course_id']}"],
                    "data_snapshot_id": graph.snapshot_id, "rule_set_hash": digest(graph.catalog["requirements"])}
        decision["canonical_result_hash"] = digest(decision)
        decision["decision_id"] = "DEC-" + decision["canonical_result_hash"][:16]
        _event(trace, "DECISION", result={"lookup_status": decision["lookup_status"]})
    else:
        decision = _one_decision(student, graph, query, trace, bundle)
        if query["intent"] == "REMAINING_PLAN":
            rules = bundle["rules"]
            summary = summarize_remaining(decision, rules)
            entries = graph.query("FETCH_CATALOG_SET", curriculum_id="CURRICULUM-CE-2026",
                                  classifications=["MAJOR_REQUIRED", "MAJOR_ELECTIVE", "GENERAL_BASIC",
                                                   "GENERAL_BALANCED", "GENERAL_EXPANDED"])
            _event(trace, "GRAPH_QUERY", operation="FETCH_CATALOG_SET",
                   filters={"curriculum_id": "CURRICULUM-CE-2026", "verification_status": "VERIFIED"},
                   returned_ids=[item for entry in entries for item in
                                 (entry["entry_id"], entry["classification_id"], *entry["relationship_ids"])])
            unmet_ids = [r["rule_id"] for r in decision["requirement_results"] if r["status"] == "UNSATISFIED"]
            links = graph.query("FETCH_COURSE_REQUIREMENT_LINKS", curriculum_id="CURRICULUM-CE-2026",
                                course_ids=[entry["course_id"] for entry in entries], rule_ids=unmet_ids)
            _event(trace, "GRAPH_QUERY", operation="FETCH_COURSE_REQUIREMENT_LINKS",
                   filters={"curriculum_id": "CURRICULUM-CE-2026", "rule_ids": unmet_ids},
                   returned_ids=[link["relationship_id"] for link in links])
            candidates = candidate_courses(decision, rules, entries, links, query.get("focus"))
            active_ids = {c["course_id"] for c in candidates if c["candidate_status"] in {"REQUIRED", "ELIGIBLE_OPTION"}}
            for entry in entries:
                if entry["course_id"] in active_ids:
                    _remember_entry(entry, bundle)
            for link in links:
                if link["course_id"] in active_ids:
                    bundle["relationships"].add(link["relationship_id"])
                    bundle["relationship_details"][link["relationship_id"]] = link["relationship_detail"]
            decision["remaining_requirements"] = summary
            decision["candidate_courses"] = candidates
            decision["requested_course_id"] = query.get("course_id")
            _rehash_decision(decision)
            prior = next(e for e in reversed(trace) if e["event_type"] == "DECISION")
            prior["result"]["decision_id"] = decision["decision_id"]
            _event(trace, "REMAINING_CALCULATION", input_refs=[r["rule_id"] for r in decision["requirement_results"]],
                   result={"satisfied": len(summary["satisfied_requirements"]),
                           "unsatisfied": len(summary["unsatisfied_requirements"]),
                           "needs_information": len(summary["needs_information"]),
                           "candidate_counts": {status: sum(c["candidate_status"] == status for c in candidates)
                                                for status in ("REQUIRED", "ELIGIBLE_OPTION", "ALREADY_COMPLETED", "NOT_APPLICABLE")}})
        if query["intent"] == "ENTITY_CHECK":
            entry = _fetch_entry(graph, query["course_id"], trace, bundle)
            found = bool(entry and entry["verification_status"] == "VERIFIED"
                         and entry["classification_verification_status"] == "VERIFIED")
            decision["lookup_status"] = "FOUND" if found else "NOT_FOUND"
            decision["lookup_result"] = {"course_id": query["course_id"],
                                         "verified_catalog_entry": found,
                                         "matching_student_attempt_ids": sorted(a["attempt_id"] for a in student["course_attempts"]
                                                                                if a.get("course_id") == query["course_id"])}
            if not found:
                decision["decision_status"] = "NEEDS_INFORMATION"
                decision["needs_information"] = sorted(set([*decision["needs_information"],
                                                             f"CATALOG_CLASSIFICATION:{query['course_id']}"]))
            _rehash_decision(decision)
            prior = next(e for e in reversed(trace) if e["event_type"] == "DECISION")
            prior["result"].update({"decision_id": decision["decision_id"],
                                    "status": decision["decision_status"]})
            _event(trace, "ENTITY_RESOLUTION", course_id=query["course_id"],
                   result="VERIFIED" if found else "NOT_FOUND")
        if query["intent"] == "TRACE_EXPLAIN":
            decision["lookup_result"] = {"relationship_ids": sorted(bundle["relationships"]),
                                         "rule_ids": [e["rule_id"] for e in trace if e["event_type"] == "RULE_EVALUATION"],
                                         "calculation_event_ids": [e["event_id"] for e in trace
                                                                   if e["event_type"] in {"RULE_EVALUATION", "CREDIT_CAP"}]}
            _rehash_decision(decision)
            trace[-1]["result"]["decision_id"] = decision["decision_id"]
            _event(trace, "TRACE_SUMMARY", input_refs=decision["lookup_result"]["calculation_event_ids"],
                   result={"relationship_count": len(decision["lookup_result"]["relationship_ids"]),
                           "rule_count": len(decision["lookup_result"]["rule_ids"])})
        if query["intent"] == "WHAT_IF":
            targets, candidates, reason = _scenario_targets(student, graph, query, decision, trace, bundle)
            _event(trace, "SCENARIO_TARGET_RESOLUTION", selector=query.get("target_selector", "EXPLICIT"),
                   candidate_course_ids=candidates, resolved_course_ids=targets, reason=reason)
            if reason:
                decision["actual_decision_status"] = decision["decision_status"]
                decision["decision_status"] = "NEEDS_INFORMATION"
                decision["simulation_status"] = "NEEDS_TARGET"
                decision["simulation_candidates"] = candidates
                decision["needs_information"] = sorted(set([*decision["needs_information"], reason]))
                _rehash_decision(decision)
                prior = next(e for e in reversed(trace) if e["event_type"] == "DECISION")
                prior["result"].update({"decision_id": decision["decision_id"],
                                        "status": decision["decision_status"]})
            else:
                simulated = deepcopy(student)
                occupied = {a["attempt_id"] for a in simulated["course_attempts"]}
                for code in targets:
                    scenario_attempt_id = f"SCENARIO-{code}"
                    while scenario_attempt_id in occupied:
                        scenario_attempt_id += "-NEXT"
                    occupied.add(scenario_attempt_id)
                    simulated["course_attempts"].append({"attempt_id": scenario_attempt_id,
                                                         "course_id": code, "completion_status": "COMPLETED",
                                                         "verification_status": "VERIFIED", "evidence_id": f"HYPOTHETICAL:{code}",
                                                         "earned_credits": None})
                _event(trace, "SCENARIO_DELTA", proposed_course_ids=targets,
                       base_student_state_id=student.get("student_state_id"))
                scenario_decision = _one_decision(simulated, graph, query, trace, bundle, hypothetical=True)
    affecting_conflicts = [c for c in ruleset["unresolved_conflicts"] if scope_applies(c["affected_scope"], student)]
    if query["intent"] == "GRADUATION_STATUS" and affecting_conflicts:
        conflict_needs = [f"RULE_CONFLICT:{c['conflict_id']}" for c in affecting_conflicts]
        decision["decision_status"] = "NEEDS_INFORMATION"
        decision["graduation_outcome"] = "UNKNOWN"
        decision["coverage_complete"] = False
        decision["needs_information"] = sorted(set([*decision["needs_information"], *conflict_needs]))
        for event in trace:
            if event["event_type"] == "COVERAGE_CHECK":
                event["result"] = "INCOMPLETE"
                event["missing"] = sorted(set([*event["missing"], *conflict_needs]))
        for conflict in affecting_conflicts:
            _event(trace, "RULE_CONFLICT", conflict_id=conflict["conflict_id"],
                   input_refs=conflict["rule_candidates"] + conflict["source_refs"],
                   source_document_ids=conflict["source_documents"], result="UNRESOLVED")
    _pin_ruleset(decision, graph, student_version, student)
    if scenario_decision:
        _pin_ruleset(scenario_decision, graph, student_version, student)
    decision_events = [event for event in trace if event["event_type"] == "DECISION"]
    for event, pinned in zip(decision_events, [decision, *([scenario_decision] if scenario_decision else [])]):
        event["result"]["decision_id"] = pinned["decision_id"]
        if "status" in event["result"]:
            event["result"]["status"] = pinned["decision_status"]
        if "graduation_outcome" in event["result"]:
            event["result"]["graduation_outcome"] = pinned["graduation_outcome"]
    used_refs = set()
    for fact in bundle["facts"].values():
        if fact.get("source_refs"):
            used_refs.update(fact["source_refs"])
        else:
            used_refs.add(fact["fact_id"])
            used_refs.add("CE-COURSES")
    for rule in bundle["rules"]:
        used_refs.update(rule["source_refs"])
    for fact in bundle["policy_facts"]:
        used_refs.update(fact["source_refs"])
    for conflict in affecting_conflicts:
        used_refs.update(conflict["source_refs"])
    locators = {r["id"]: r for r in graph.catalog["source_locators"]}
    bundle["source_locators"] = {k: locators[k] for k in used_refs if k in locators}
    bundle["relationships"] = sorted(bundle["relationships"])
    bundle["relationship_details"] = [bundle["relationship_details"][rid] for rid in bundle["relationships"]]
    bundle["nodes"] = [bundle["nodes"][nid] for nid in sorted(bundle["nodes"])]
    bundle["facts"] = list(bundle["facts"].values())
    bundle["student_evidence_refs"] = sorted({a["evidence_id"] for a in student["course_attempts"]}
                                              | {r["evidence_id"] for r in student.get("free_choice_records", [])}
                                              | {e["evidence_id"] for e in student.get("official_outcomes", {}).values()
                                                 if e.get("evidence_id")}
                                              | ({student["equivalence_review_evidence_id"]} if student.get("equivalence_review_evidence_id") else set())
                                              | {student[key] for key in ("student_category_evidence_id", "applicability_evidence_id", "completion_coverage_evidence_id") if student.get(key)}
                                              | {r["student_evidence_id"] for d in (decision, scenario_decision) if d
                                                 for r in d.get("recognitions", [])})
    scenario_delta = None
    if query["intent"] == "WHAT_IF":
        if scenario_decision:
            before = {r["rule_id"]: r["status"] for r in decision["requirement_results"]}
            changed = [{"rule_id": r["rule_id"], "before": before[r["rule_id"]], "after": r["status"]}
                       for r in scenario_decision["requirement_results"]
                       if r["rule_id"] in before and before[r["rule_id"]] != r["status"]]
            actual_total = decision["credited_amount"]["total"]
            simulated_total = scenario_decision["credited_amount"]["total"]
            actual_major = decision["credited_amount"]["by_area"].get("MAJOR_TOTAL")
            simulated_major = scenario_decision["credited_amount"]["by_area"].get("MAJOR_TOTAL")
            required_before = decision.get("missing_courses")
            required_after = scenario_decision.get("missing_courses")
            completed_required = (sorted(set(required_before) - set(required_after))
                                  if required_before is not None and required_after is not None else None)
            def graduation_preview(value: dict) -> str:
                if value["unresolved_conflict_ids"]:
                    return "UNKNOWN"
                if value["decision_status"] == "UNSATISFIED":
                    return "NOT_ELIGIBLE_PDF"
                if value["decision_status"] == "SATISFIED" and value["coverage_complete"]:
                    return "ELIGIBLE_PDF"
                return "UNKNOWN"
            scenario_delta = {"status": "CALCULATED", "changed_requirements": changed,
                              "missing_required_before": required_before,
                              "missing_required_after": required_after,
                              "completed_required_course_ids": completed_required,
                              "actual_total": actual_total, "simulated_total": simulated_total,
                              "total_credit_change": (simulated_total - actual_total if actual_total is not None
                                                      and simulated_total is not None else None),
                              "actual_major": actual_major, "simulated_major": simulated_major,
                              "major_credit_change": (simulated_major - actual_major if actual_major is not None
                                                      and simulated_major is not None else None),
                              "graduation_preview_before": graduation_preview(decision),
                              "graduation_preview_after": graduation_preview(scenario_decision)}
        else:
            scenario_delta = {"status": "NEEDS_TARGET", "changed_requirements": None,
                              "missing_required_before": decision.get("missing_courses"),
                              "missing_required_after": None,
                              "completed_required_course_ids": None,
                              "actual_total": (decision.get("credited_amount") or {}).get("total"),
                              "simulated_total": None, "total_credit_change": None,
                              "actual_major": (decision.get("credited_amount") or {}).get("by_area", {}).get("MAJOR_TOTAL"),
                              "simulated_major": None, "major_credit_change": None,
                              "graduation_preview_before": None, "graduation_preview_after": None,
                              "candidate_course_ids": decision.get("simulation_candidates", [])}
        _event(trace, "SCENARIO_COMPARISON", result=scenario_delta)
    execution = {"contract_version": "1", "execution_id": "EX-" + input_id, "decision_id": decision["decision_id"],
                 "events": trace, "data_snapshot_id": graph.snapshot_id,
                 "authoritative_document_set_id": document_set["set_id"],
                 "authoritative_document_set_version": document_set["set_version"],
                 "ruleset_id": ruleset["ruleset_id"], "ruleset_version": ruleset["ruleset_version"]}
    authority = {"document_set": document_set, "ruleset": ruleset,
                 "document_relations": graph.catalog["document_relations"],
                 "documents": [{key: doc[key] for key in ("document_id", "title", "document_type", "source_file", "source_hash")}
                               for doc in graph.catalog["authoritative_documents"]
                               if doc["document_id"] in document_set["included_documents"]],
                 "rule_sources": {rule["rule_id"]: {"rule_version": rule["rule_version"],
                                                     "source_documents": rule["source_documents"],
                                                     "supersedes": rule["supersedes"],
                                                     "source_refs": rule["source_refs"]}
                                  for rule in graph.catalog["requirements"]},
                 "unresolved_conflicts": affecting_conflicts}
    payload = {"contract_version": "1", "decision": decision, "scenario_decision": scenario_decision,
               "requirement_results": decision["requirement_results"],
               "credited_amount": decision["credited_amount"], "missing_amount": decision["missing_amount"],
               "missing_courses": decision["missing_courses"], "needs_information": decision["needs_information"],
               "evidence": bundle, "execution_trace": execution, "scenario_delta": scenario_delta,
               "authority": authority}
    from .render import build_remaining_presentation, render_answer
    if decision["intent"] == "REMAINING_PLAN" and decision.get("remaining_requirements"):
        payload["remaining_presentation"] = build_remaining_presentation(payload)
    payload["answer_text"] = render_answer(payload)
    from .verifier import verify_payload
    verify_payload(payload)
    return payload
