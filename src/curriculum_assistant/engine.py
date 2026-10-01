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
from .placement import CLASSES, group_placement, select_placement, validate_filter
from .scope import YEAR_BASES, policy_targets, question_scope_conflicts, relevant_conditions

INTENTS = {"COURSE_LOOKUP", "CREDIT_SUMMARY", "REQUIREMENT_GAPS", "WHAT_IF", "GRADUATION_STATUS",
           "POLICY_LOOKUP", "CATALOG_AGGREGATE", "ENTITY_CHECK", "CONSISTENCY_CHECK", "TRACE_EXPLAIN",
           "REMAINING_PLAN", "PLACEMENT_LOOKUP"}
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
POLICY_FACT_TOPICS = {"APPLICABILITY", "FREE_CHOICE", "EQUIVALENCE", "RECOMMENDATIONS", "TRANSITION", "MULTI_PROGRAM", "ENGLISH_EXEMPTION"}
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
    targets = query.get('year_targets', [])
    if (not isinstance(targets,list) or len(targets)>32 or any(
        not isinstance(t,dict) or set(t)-{'year','basis','invalid_range'} or
        type(t.get('year')) is not int or not 1900<=t['year']<=2100 or t.get('basis') not in YEAR_BASES
        or ('invalid_range' in t and type(t['invalid_range']) is not bool)
        for t in targets)):
        raise ValueError('Year targets must be bounded typed scopes')
    conditions = query.get('declared_conditions',[])
    if not isinstance(conditions,list) or len(conditions)>8 or not set(conditions).issubset({
        'DISABILITY','STANDARD_DURATION_EXCEEDED','READMISSION','DEPARTMENT_TRANSFER','TRANSFER','LEAVE_OF_ABSENCE'}):
        raise ValueError('Declared applicability conditions are not allowlisted')
    for key in ("placement_requested", "group_by_placement"):
        if key in query and type(query[key]) is not bool:
            raise ValueError("Placement flags must be boolean")
    if query.get("next_term_basis") not in {None, "UNSPECIFIED"}:
        raise ValueError("Next-term basis cannot be inferred from a label")
    if "placement_filter" in query:
        if query["intent"] not in {"PLACEMENT_LOOKUP", "COURSE_LOOKUP", "REMAINING_PLAN"}:
            raise ValueError("Placement filter is not valid for this intent")
        validate_filter(query["placement_filter"])
    if query.get("intent") == "PLACEMENT_LOOKUP":
        if query.get("curriculum_id") != "CURRICULUM-CE-2026" or query.get("department_id") != "DEPT-COMPUTER-ENGINEERING":
            raise ValueError("Placement catalog scope is not verified")
        classes = query.get("classifications")
        if not isinstance(classes, list) or not classes or len(classes) > 5 or not set(classes).issubset(CLASSES):
            raise ValueError("Placement classifications are not allowlisted")
    if query.get("intent") == "REMAINING_PLAN" and "classifications" in query:
        classes = query["classifications"]
        if not isinstance(classes, list) or not classes or len(classes) > 5 or not set(classes).issubset(CLASSES):
            raise ValueError("Remaining placement classifications are not allowlisted")
    if query.get("intent") == "POLICY_LOOKUP":
        claim=query.get('exam_claim')
        if claim is not None and (not isinstance(claim,dict) or set(claim)!={'exam','score'} or
            claim['exam']!='TOEIC' or type(claim['score']) is not int or not 0<=claim['score']<=990):
            raise ValueError('Exam claim must be a typed TOEIC score')
        topics = query.get("topics")
        if not isinstance(topics, list) or not topics or len(topics) > 8 or any(topic not in POLICY_RULE_TOPICS | POLICY_FACT_TOPICS for topic in topics):
            raise ValueError("POLICY_LOOKUP requires allowlisted topics")
        if query.get("program_type", student.get("program_type")) not in PROGRAM_TYPES:
            raise ValueError("POLICY_LOOKUP program_type is invalid")
        if "entry_year" in query and (type(query["entry_year"]) is not int or not 1900 <= query["entry_year"] <= 2100):
            raise ValueError("POLICY_LOOKUP entry_year is invalid")
        if query.get("compared_program_type", "MINOR") not in PROGRAM_TYPES:
            raise ValueError("POLICY_LOOKUP compared program type is invalid")
        if query.get("student_category", "DOMESTIC_REGULAR") not in {"DOMESTIC_REGULAR", "TRANSFER", "NIGHT", "EMPLOYED_ADULT", "CONTRACT"}:
            raise ValueError("POLICY_LOOKUP student category is invalid")
        categories = query.get("student_categories", [])
        if (not isinstance(categories, list) or len(categories) > 5 or
                any(value not in {"TRANSFER", "NIGHT", "EMPLOYED_ADULT", "CONTRACT"} for value in categories)):
            raise ValueError("POLICY_LOOKUP student categories are invalid")
        if query.get("historical_scope_requested", False) not in {True, False}:
            raise ValueError("POLICY_LOOKUP historical scope flag is invalid")
        if query.get("partial_student_information", False) not in {True, False}:
            raise ValueError("POLICY_LOOKUP partial-information flag is invalid")
        earned = query.get("hypothetical_general_earned")
        if earned is not None and (type(earned) is not int or not 0 <= earned <= 1000 or "GENERAL_CREDITS" not in topics):
            raise ValueError("POLICY_LOOKUP hypothetical general credits are invalid")
        requested = query.get("requested_calculations", [])
        if (not isinstance(requested, list) or len(requested) > 3 or
                not set(requested).issubset({"GENERAL_REMAINDER", "GRADUATION_REMAINDER", "MAJOR_ELECTIVE_WITH_ADVANCED"})):
            raise ValueError("POLICY_LOOKUP calculation request is not allowlisted")
        if query.get("policy_focus") not in {None, "DOUBLE_COUNT", "APPLICABILITY_CHOICE",
                                             "GENERAL_AREA_COURSE_CREDITS", "GENERAL_AREA_DOUBLE_COUNT",
                                             "COUNSELING_SCHEDULE"}:
            raise ValueError("POLICY_LOOKUP focus is not allowlisted")
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


def _placement_lookup(graph: Graph, query: dict, trace: list[dict], bundle: dict) -> dict:
    entries = graph.query("FETCH_CATALOG_SET", curriculum_id=query["curriculum_id"], classifications=query["classifications"])
    _event(trace, "GRAPH_QUERY", operation="FETCH_CATALOG_SET",
           filters={"curriculum_id": query["curriculum_id"], "classifications": query["classifications"]},
           returned_ids=[id for entry in entries for id in (entry["entry_id"], entry["classification_id"], *entry["relationship_ids"])])
    for entry in entries:
        _remember_entry(entry, bundle)
    selection = select_placement(entries, query.get("placement_filter", {}))
    selected = set(selection["matched_course_ids"])
    unknown = set(selection["needs_verification_course_ids"])
    result = {"curriculum_id": query["curriculum_id"], "selection": selection,
              "courses": [e for e in entries if e["course_id"] in selected],
              "needs_verification": [e for e in entries if e["course_id"] in unknown],
              "groups": group_placement([e for e in entries if e["course_id"] in selected]),
              "next_term_basis": query.get("next_term_basis")}
    _event(trace, "PLACEMENT_SELECTION", input_refs=[e["entry_id"] for e in entries], result=selection)
    decision = {"contract_version": "1", "intent": "PLACEMENT_LOOKUP", "decision_status": None,
                "graduation_outcome": "NOT_REQUESTED", "lookup_status": "FOUND", "lookup_result": result,
                "requirement_results": [], "credited_amount": None, "missing_amount": None,
                "missing_courses": None, "needs_information": [], "data_snapshot_id": graph.snapshot_id,
                "rule_set_hash": digest(graph.catalog["requirements"])}
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


def _policy_lookup(graph: Graph, student: dict, query: dict, trace: list[dict], bundle: dict,
                   target: dict | None = None, emit_decision: bool = True) -> dict:
    targets = policy_targets(query, student)
    if target is None and len(targets)>1:
        rows=[]
        for t in targets:
            child=_policy_lookup(graph,student,query,trace,bundle,t,False)
            rows.append({'target':t,'lookup_result':child['lookup_result'],
                         'lookup_status':child['lookup_status'],'needs_information':child['needs_information']})
            _event(trace,'POLICY_YEAR_RESULT',target=t,lookup_result=child['lookup_result'],
                   needs_information=child['needs_information'])
        result={'topics':sorted(set(query['topics'])),'program_type':query.get('program_type',student['program_type']),
                'entry_year':None,'year_comparison':rows,'rules':bundle['rules'],
                'policy_facts':bundle['policy_facts'],'courses':[],
                'calculations':[c for row in rows for c in (row['lookup_result'] or {}).get('calculations',[])],
                'rule_applicability':{k:v for row in rows for k,v in (row['lookup_result'] or {}).get('rule_applicability',{}).items()}}
        needs=sorted({n for row in rows for n in row['needs_information']})
        decision={'contract_version':'1','intent':'POLICY_LOOKUP','decision_status':None,
                  'graduation_outcome':'NOT_REQUESTED','lookup_status':'NEEDS_INFORMATION' if needs else 'FOUND',
                  'lookup_result':result,'requirement_results':[],'credited_amount':None,
                  'missing_amount':None,'missing_courses':None,'needs_information':needs,
                  'data_snapshot_id':graph.snapshot_id,'rule_set_hash':digest(graph.catalog['requirements'])}
        _rehash_decision(decision)
        _event(trace,'DECISION',result={'lookup_status':decision['lookup_status']})
        return decision
    target = target or targets[0]
    topics = sorted(set(query["topics"]))
    program_type = query.get("program_type", student["program_type"])
    entry_year = target['year']
    document_unavailable=target['basis']=='DOCUMENT_YEAR' and entry_year!=2026
    year_specific_rules_available = entry_year in (None, 2026) and not target.get('invalid_range') and not query.get("historical_scope_requested", False)
    historical_needed = not year_specific_rules_available and not document_unavailable and bool(set(topics) & {"GRADUATION_CREDITS", "GENERAL_CREDITS", "MAJOR_CREDITS"})
    missing = ["STUDENT_STATE_FOR_PERSONAL_CALCULATION"] if query.get("partial_student_information") else []
    if document_unavailable:
        missing.append(f'OFFICIAL_DOCUMENT_VERSION_NOT_REGISTERED:{entry_year}')
    selected_rules: dict[str, dict] = {}
    selected_facts: dict[str, dict] = {}
    selected_courses: dict[str, dict] = {}
    bundle["nodes"]["CURRICULUM-CE-2026"] = {"id": "CURRICULUM-CE-2026", "kind": "CurriculumVersion", "label": "2026 컴퓨터공학과"}
    lookup_topics = list(topics)
    if not year_specific_rules_available and "APPLICABILITY" not in lookup_topics:
        lookup_topics.append("APPLICABILITY")
    if historical_needed and entry_year is not None and entry_year <= 2024 and "TRANSITION" not in lookup_topics:
        lookup_topics.append("TRANSITION")
    for topic in lookup_topics:
        if topic in POLICY_RULE_TOPICS:
            if not year_specific_rules_available:
                _event(trace, "POLICY_SCOPE_EXCLUDED", topic=topic, entry_year=entry_year,
                       reason="2026_RULES_NOT_VERIFIED_FOR_ENTRY_YEAR")
                continue
            candidate_ids = _policy_rule_ids(graph.catalog, topic)
            if topic == "REQUIRED_COURSES" and program_type == "MINOR":
                # The main-major nine-course list is not the three courses
                # marked for a student minoring in computer engineering.
                candidate_ids = []
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
        facts = (graph.query("FETCH_POLICY_FACTS", curriculum_id="CURRICULUM-CE-2026", topic=topic)
                 if any(fact["topic"] == topic for fact in graph.catalog["policy_facts"]) else [])
        if facts:
            _event(trace, "GRAPH_QUERY", operation="FETCH_POLICY_FACTS", filters={"topic": topic},
                   returned_ids=[f["policy_fact_id"] for f in facts] + [f["relationship_id"] for f in facts])
        for fact in facts:
            if topic == "MULTI_PROGRAM" and fact["value"]["program_type"] not in {program_type, query.get("compared_program_type")}:
                _event(trace, "POLICY_SCOPE_EXCLUDED", topic=topic, policy_fact_id=fact["policy_fact_id"],
                       reason="DIFFERENT_PROGRAM_TYPE")
                continue
            selected_facts[fact["policy_fact_id"]] = fact
            bundle["nodes"][fact["policy_fact_id"]] = {"id": fact["policy_fact_id"], "kind": "PolicyFact", "label": fact["predicate"]}
            bundle["relationships"].add(fact["relationship_id"])
            bundle["relationship_details"][fact["relationship_id"]] = fact["relationship_detail"]
    if "MULTI_PROGRAM" in topics and program_type == "MINOR":
        for course in graph.catalog["courses"]:
            if course.get("minor_required") and course["verification_status"] == "VERIFIED":
                entry = _fetch_entry(graph, course["course_id"], trace, bundle)
                if entry and entry["classification_verification_status"] == "VERIFIED":
                    selected_courses[course["course_id"]] = entry
    if historical_needed and entry_year is not None and program_type == "SINGLE":
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
        missing.append(f"APPLICABLE_CURRICULUM_RULES_FOR_ENTRY_YEAR:{entry_year or 'UNKNOWN'}")
    category = query.get("student_category")
    categories = sorted(set(query.get("student_categories", [])))
    applicability = {}
    exception = next((fact for fact in selected_facts.values()
                      if fact["predicate"] == "GENERAL_AREA_APPLICABILITY_EXCEPTIONS"), None)
    for rule in selected_rules.values():
        reason = "PROGRAM_TYPE_MATCH"
        status = "APPLICABLE"
        if rule["rule_id"].startswith("R-GE-") and categories and exception:
            values = exception["value"]
            possible = []
            for member in categories:
                if member in values["general_obligation_exempt"]:
                    possible.append("NOT_APPLICABLE")
                elif member in values["area_minimum_exempt"] and rule["rule_id"] != "R-GE-2026-CREDIT-CAP":
                    possible.append("NOT_APPLICABLE")
                else:
                    possible.append("APPLICABLE")
            status = possible[0] if len(set(possible)) == 1 else "NEEDS_INFORMATION"
            reason = "MULTIPLE_CATEGORY_SCOPE" if len(set(possible)) > 1 else "CATEGORY_EXCEPTIONS"
        elif rule["rule_id"].startswith("R-GE-") and category and exception:
            values = exception["value"]
            if category in values["general_obligation_exempt"]:
                status, reason = "NOT_APPLICABLE", "TRANSFER_GENERAL_OBLIGATION_EXEMPT"
            elif category in values["area_minimum_exempt"] and rule["rule_id"] != "R-GE-2026-CREDIT-CAP":
                status, reason = "NOT_APPLICABLE", "CATEGORY_AREA_MINIMUM_EXEMPT"
        applicability[rule["rule_id"]] = {"status": status, "reason": reason,
                                            "source_refs": exception["source_refs"] if reason != "PROGRAM_TYPE_MATCH" else rule["source_refs"]}
        _event(trace, "POLICY_APPLICABILITY", rule_id=rule["rule_id"], result=applicability[rule["rule_id"]])
    calculations = []
    by_area = {rule.get("area"): rule for rule in selected_rules.values()
               if rule["rule_type"] == "MIN_CREDITS" and applicability[rule["rule_id"]]["status"] == "APPLICABLE"}
    requested_calculations = set(query.get("requested_calculations", []))
    if "MAJOR_ELECTIVE_WITH_ADVANCED" in requested_calculations and {"MAJOR_ELECTIVE", "MAJOR_ADVANCED"}.issubset(by_area):
        selected = [by_area["MAJOR_ELECTIVE"], by_area["MAJOR_ADVANCED"]]
        value = sum(rule["required_value"] for rule in selected)
        calculations.append({"operation": "SUM_MINIMUM_COMPONENTS", "area": "MAJOR_ELECTIVE_WITH_ADVANCED",
                             "required_amount": value, "earned_amount": None, "recognized_amount": None,
                             "remaining_amount": None, "excess_amount": None, "capped_amount": None,
                             "excluded_amount": None, "source_rule_ids": [rule["rule_id"] for rule in selected]})
    if "GENERAL_REMAINDER" in requested_calculations and {"GENERAL_TOTAL", "GENERAL_BASIC", "GENERAL_BALANCED"}.issubset(by_area):
        selected = [by_area[key] for key in ("GENERAL_TOTAL", "GENERAL_BASIC", "GENERAL_BALANCED")]
        value = selected[0]["required_value"] - selected[1]["required_value"] - selected[2]["required_value"]
        calculations.append({"operation": "REMAINDER_AFTER_REQUIRED_AREAS", "area": "GENERAL_REMAINDER",
                             "required_amount": value, "earned_amount": None, "recognized_amount": None,
                             "remaining_amount": None, "excess_amount": None, "capped_amount": None,
                             "excluded_amount": None, "source_rule_ids": [rule["rule_id"] for rule in selected]})
    if "GRADUATION_REMAINDER" in requested_calculations and "FREE_CHOICE" in topics and {"GRADUATION_TOTAL", "GENERAL_TOTAL", "MAJOR_TOTAL"}.issubset(by_area):
        selected = [by_area[key] for key in ("GRADUATION_TOTAL", "GENERAL_TOTAL", "MAJOR_TOTAL")]
        value = selected[0]["required_value"] - selected[1]["required_value"] - selected[2]["required_value"]
        calculations.append({"operation": "GRADUATION_REMAINDER_STRUCTURE", "area": "GRADUATION_REMAINDER",
                             "required_amount": value, "earned_amount": None, "recognized_amount": None,
                             "remaining_amount": None, "excess_amount": None, "capped_amount": None,
                             "excluded_amount": None, "source_rule_ids": [rule["rule_id"] for rule in selected]})
    cap = next((rule for rule in selected_rules.values() if rule["rule_type"] == "CREDIT_CAP"
                and rule.get("area") == "GENERAL_TOTAL" and applicability[rule["rule_id"]]["status"] == "APPLICABLE"), None)
    earned = query.get("hypothetical_general_earned")
    if cap and earned is not None:
        minimum = by_area.get("GENERAL_TOTAL")
        recognized = min(earned, cap["required_value"])
        calculations.append({"operation": "APPLY_VERIFIED_CREDIT_CAP", "area": "GENERAL_TOTAL",
                             "required_amount": minimum["required_value"] if minimum else None,
                             "earned_amount": earned, "recognized_amount": recognized,
                             "remaining_amount": max((minimum["required_value"] if minimum else 0) - recognized, 0) if minimum else None,
                             "excess_amount": max(earned - recognized, 0), "capped_amount": cap["required_value"],
                             "excluded_amount": earned - recognized,
                             "source_rule_ids": [cap["rule_id"]] + ([minimum["rule_id"]] if minimum else [])})
    for calculation in calculations:
        _event(trace, "POLICY_CALCULATION", operation=calculation["operation"],
               input_refs=calculation["source_rule_ids"], result=calculation)
    bundle['rules']=list({r['rule_id']:r for r in [*bundle['rules'],*selected_rules.values()]}.values())
    bundle['policy_facts']=list({f['policy_fact_id']:f for f in [*bundle['policy_facts'],*selected_facts.values()]}.values())
    result = {"topics": topics, "program_type": program_type, "entry_year": entry_year if target['basis']=='ADMISSION_YEAR' else None,
              'policy_year':entry_year, 'year_target':target,
              'document_scope_available':not document_unavailable,
              "policy_focus": query.get("policy_focus"),
              "student_category": category, "student_categories": categories,
              "historical_scope_requested": query.get("historical_scope_requested", False),
              "compared_program_type": query.get("compared_program_type"),
              "rule_applicability": applicability, "calculations": calculations,
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
    if query.get('exam_claim'):
        fact=next((f for f in selected_facts.values() if f['predicate']=='ENGLISH_COURSE_EXEMPTION'),None)
        if fact:
            criterion=next(c for c in fact['value']['criteria'] if c['exam']==query['exam_claim']['exam'])
            result['exam_criterion_result']={'exam':criterion['exam'],'score':query['exam_claim']['score'],
                'minimum':criterion['minimum'],'meets_score_criterion':query['exam_claim']['score']>=criterion['minimum'],
                'official_exemption_granted':False,'policy_fact_id':fact['policy_fact_id']}
            _event(trace,'POLICY_EXAM_CRITERION',input_refs=[fact['policy_fact_id']],result=result['exam_criterion_result'])
            _rehash_decision(decision)
    if emit_decision:
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


def _evaluate_rules(student: dict, graph: Graph, recognition: dict, trace: list[dict], bundle: dict,
                    query: dict | None = None) -> tuple[list[dict], dict, set[str]]:
    rules = graph.query("FETCH_REQUIREMENTS", curriculum_id="CURRICULUM-CE-2026")
    _event(trace, "GRAPH_QUERY", operation="FETCH_REQUIREMENTS", filters={"curriculum_id": "CURRICULUM-CE-2026"},
           returned_ids=[item["rule_id"] for item in rules] + [item["relationship_id"] for item in rules])
    bundle["rules"] = rules
    bundle["relationships"].update(item["relationship_id"] for item in rules)
    bundle["nodes"]["CURRICULUM-CE-2026"] = {"id": "CURRICULUM-CE-2026", "kind": "CurriculumVersion", "label": "2026 컴퓨터공학과"}
    for item in rules:
        bundle["nodes"][item["rule_id"]] = {"id": item["rule_id"], "kind": "Requirement", "label": item["rule_id"]}
        bundle["relationship_details"][item["relationship_id"]] = item["relationship_detail"]
    conditional_facts = {}
    if graph.catalog.get('coverage_policy'):
        for topic in ('ENGLISH_EXEMPTION','GRADUATION_CONDITIONS','APPLICABILITY'):
            facts=graph.query('FETCH_POLICY_FACTS',curriculum_id='CURRICULUM-CE-2026',topic=topic)
            _event(trace,'GRAPH_QUERY',operation='FETCH_POLICY_FACTS',filters={'topic':topic},
                   returned_ids=[f['policy_fact_id'] for f in facts]+[f['relationship_id'] for f in facts])
            for f in facts:
                conditional_facts[f['policy_fact_id']]=f
                bundle['policy_facts'].append(f)
                bundle['nodes'][f['policy_fact_id']]={'id':f['policy_fact_id'],'kind':'PolicyFact','label':f['predicate']}
                bundle['relationships'].add(f['relationship_id'])
                bundle['relationship_details'][f['relationship_id']]=f['relationship_detail']
    exception_fact = None
    if student.get("student_category") not in {None, "DOMESTIC_REGULAR"}:
        facts = graph.query("FETCH_POLICY_FACTS", curriculum_id="CURRICULUM-CE-2026", topic="GENERAL_AREAS")
        _event(trace, "GRAPH_QUERY", operation="FETCH_POLICY_FACTS", filters={"topic": "GENERAL_AREAS"},
               returned_ids=[fact["policy_fact_id"] for fact in facts] + [fact["relationship_id"] for fact in facts])
        exception_fact = next((fact for fact in facts if fact["predicate"] == "GENERAL_AREA_APPLICABILITY_EXCEPTIONS"), None)
        if exception_fact:
            bundle["policy_facts"].append(exception_fact)
            bundle["nodes"][exception_fact["policy_fact_id"]] = {"id": exception_fact["policy_fact_id"],
                                                               "kind": "PolicyFact", "label": exception_fact["predicate"]}
            bundle["relationships"].add(exception_fact["relationship_id"])
            bundle["relationship_details"][exception_fact["relationship_id"]] = exception_fact["relationship_detail"]
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
        category = student.get("student_category")
        applied_adjustments=[]
        pending_adjustment=False
        exemption_condition=None
        for condition in rule.get('conditional_exemptions',[]):
            raw=student.get(condition['condition_key'])
            mentioned='DISABILITY' in (query or {}).get('declared_conditions',[])
            if raw is not None or mentioned:
                value=raw.get('value') if isinstance(raw,dict) else raw
                verified=isinstance(raw,dict) and raw.get('verification_status')=='VERIFIED' and bool(raw.get('evidence_id'))
                if value is True and verified:
                    exemption_condition={**condition,'status':'NOT_APPLICABLE','evidence_id':raw['evidence_id']}
                elif not verified or (mentioned and value is not True):
                    official=student.get('official_outcomes',{}).get(rule.get('evidence_key'),{})
                    if not (official.get('value') is True and official.get('verification_status')=='VERIFIED' and official.get('evidence_id')):
                        exemption_condition={**condition,'status':'NEEDS_INFORMATION','evidence_id':None}
        verified_category = bool(student.get("student_category_evidence_id"))
        exception_applies = bool(exception_fact and verified_category and rid.startswith("R-GE-") and (
            category in exception_fact["value"]["general_obligation_exempt"] or
            (category in exception_fact["value"]["area_minimum_exempt"] and rid != "R-GE-2026-CREDIT-CAP")))
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
        elif exception_applies:
            result = {"requirement_id": rid, "rule_id": rid, "status": "NOT_APPLICABLE", "observed": None,
                      "required": rule.get("required_value"), "missing_amount": None, "missing_course_ids": None,
                      "used_fact_ids": [], "used_relationship_ids": [rule["relationship_id"], exception_fact["relationship_id"]],
                      "used_student_evidence_ids": [student["student_category_evidence_id"]],
                      "needs_information": [], "source_refs": rule["source_refs"],
                      "applicability_policy_fact_id": exception_fact["policy_fact_id"],
                      "applicability_source_refs": exception_fact["source_refs"],
                      "applicability_reason": ("TRANSFER_GENERAL_OBLIGATION_EXEMPT" if
                                               category in exception_fact["value"]["general_obligation_exempt"] else
                                               "CATEGORY_AREA_MINIMUM_EXEMPT")}
            _event(trace, "RULE_APPLICABILITY", rule_id=rid, input_refs=[exception_fact["policy_fact_id"],
                   student["student_category_evidence_id"]], result=result["applicability_reason"])
        elif general_rule and (student.get("student_category") != "DOMESTIC_REGULAR" or not student.get("student_category_evidence_id")):
            result = {"requirement_id": rid, "rule_id": rid, "status": "NEEDS_INFORMATION", "observed": None,
                      "required": rule.get("required_value"), "missing_amount": None, "missing_course_ids": None,
                      "used_fact_ids": [], "used_relationship_ids": [rule["relationship_id"]],
                      "used_student_evidence_ids": [], "needs_information": ["VERIFIED_STUDENT_CATEGORY_AND_EXCEPTIONS"], "source_refs": rule["source_refs"]}
        elif exemption_condition and rule['verification_status']=='VERIFIED':
            fact=conditional_facts[exemption_condition['policy_fact_id']]
            status=exemption_condition['status']
            result={'requirement_id':rid,'rule_id':rid,'status':status,'observed':None,'required':None,
                    'missing_amount':None,'missing_course_ids':None,'used_fact_ids':[],
                    'used_relationship_ids':[rule['relationship_id'],fact['relationship_id']],
                    'used_student_evidence_ids':[exemption_condition['evidence_id']] if exemption_condition['evidence_id'] else [],
                    'needs_information':[] if status=='NOT_APPLICABLE' else ['VERIFIED_DISABILITY_EXEMPTION_CONDITION'],
                    'source_refs':rule['source_refs'],'applicability_reason':'PDF_CERTIFICATION_DISABILITY_EXEMPTION',
                    'applicability_policy_fact_id':fact['policy_fact_id'],'applicability_source_refs':fact['source_refs'],
                    'evaluation_basis':'VERIFIED_PDF_EXEMPTION' if status=='NOT_APPLICABLE' else 'CONDITION_INFORMATION_REQUIRED'}
            _event(trace,'RULE_APPLICABILITY',rule_id=rid,input_refs=[fact['policy_fact_id'],*result['used_student_evidence_ids']],result=result['applicability_reason'])
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
                for adjustment in rule.get('conditional_adjustments',[]):
                    raw=student.get('official_outcomes',{}).get(adjustment['condition_key'])
                    fact=conditional_facts[adjustment['policy_fact_id']]
                    courses_present=any(r['course_id'] in fact['value']['exempt_course_ids'] for r in recognition['recognitions'])
                    verified=bool(raw and raw.get('verification_status')=='VERIFIED' and raw.get('evidence_id'))
                    if not courses_present and verified and raw.get('value') is adjustment['expected_value']:
                        threshold-=adjustment['amount']
                        applied_adjustments.append({**adjustment,'student_evidence_id':raw['evidence_id'],
                            'base_required_amount':rule['required_value'],'effective_required_amount':threshold,
                            'replacement_general_credits_required':adjustment['amount']})
                        _event(trace,'RULE_CONDITIONAL_ADJUSTMENT',rule_id=rid,
                            input_refs=[fact['policy_fact_id'],raw['evidence_id']],result=applied_adjustments[-1])
                    elif not courses_present and not verified and observed<threshold:
                        pending_adjustment=True
                if observed >= threshold:
                    status = "SATISFIED"
                elif pending_adjustment:
                    status = 'NEEDS_INFORMATION'
                elif recognition["complete"]:
                    status = "UNSATISFIED"
                else:
                    status = "NEEDS_INFORMATION"
                missing = max(0, threshold - observed) if recognition["complete"] and not pending_adjustment else None
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
                elif rule["rule_type"] == "ANY_COURSE_OR_EXEMPTION" and (not exemption or exemption.get("verification_status") != "VERIFIED" or not exemption.get('evidence_id') or type(exemption.get('value')) is not bool):
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
            if graph.catalog.get('coverage_policy'):
                result['evaluation_basis']='OFFICIAL_RESULT_INPUT' if rule['rule_type']=='REQUIRED_EVIDENCE' else 'DIRECT_RULE_CALCULATION'
                if rule['rule_type']=='ANY_COURSE_OR_EXEMPTION' and exempted and not used:
                    fact=conditional_facts[rule['exemption_policy_fact_id']]
                    result['evaluation_basis']='OFFICIAL_EXEMPTION_INPUT'
                    result['used_policy_fact_ids']=[fact['policy_fact_id']]
                    result['used_relationship_ids'].append(fact['relationship_id'])
                    _event(trace,'RULE_EXEMPTION_INPUT',rule_id=rid,
                           input_refs=[fact['policy_fact_id'],exemption['evidence_id']],result='VERIFIED_EXEMPTION')
                if applied_adjustments:
                    result['conditional_adjustments_applied']=applied_adjustments
                    result['used_policy_fact_ids']=[a['policy_fact_id'] for a in applied_adjustments]
                    result['used_relationship_ids']+= [conditional_facts[a['policy_fact_id']]['relationship_id'] for a in applied_adjustments]
                    result['used_student_evidence_ids']+= [a['student_evidence_id'] for a in applied_adjustments]
                if pending_adjustment:
                    result['needs_information']=sorted(set(result['needs_information']+['VERIFIED_ENGLISH_EXEMPTION_OR_COURSE_COMPLETION']))
        if rule["rule_type"] == "MIN_CREDITS" and result["observed"] is not None:
            result["credit_calculation"] = {
                "required_amount": result["required"],
                "earned_amount": None if rule.get("area") == "GRADUATION_TOTAL" else result["observed"],
                "recognized_amount": result["observed"], "remaining_amount": result["missing_amount"],
                "excess_amount": None, "capped_amount": None, "excluded_amount": None,
                "value_status": "COMPLETE" if recognition["complete"] else "CONFIRMED_MINIMUM"}
        elif rule["rule_type"] == "CREDIT_CAP" and result["observed"] is not None:
            counted = min(result["observed"], result["required"])
            result["credit_calculation"] = {
                "required_amount": None, "earned_amount": result["observed"],
                "recognized_amount": counted, "remaining_amount": None,
                "excess_amount": result["observed"] - counted,
                "capped_amount": result["required"], "excluded_amount": result["observed"] - counted,
                "value_status": "COMPLETE" if recognition["complete"] else "CONFIRMED_MINIMUM"}
        result["execution_event_ids"] = [_event(trace, "RULE_EVALUATION", rule_id=rid,
                                                   operands={"observed": result["observed"], "required": result["required"]},
                                                   calculation=rule.get("calculation", rule["rule_type"]),
                                                   calculation_details=result.get("credit_calculation"),
                                                   input_refs=result["used_fact_ids"] + result["used_student_evidence_ids"],
                                                   result=result["status"])]
        results.append(result)
    return results, sums, unsafe_derived


def _one_decision(student: dict, graph: Graph, query: dict, trace: list[dict], bundle: dict, hypothetical: bool = False) -> dict:
    recognition = _recognize(student, graph, trace, bundle, hypothetical)
    results, sums, unsafe_derived = _evaluate_rules(student, graph, recognition, trace, bundle, query)
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
    coverage_details = None
    boundary_needs = []
    if graph.catalog.get('coverage_policy'):
        scope_conflicts = question_scope_conflicts(query, student)
        conditions = relevant_conditions(student, query)
        unhandled = [c for c in conditions if c != 'DISABILITY']
        loaded_complete = not missing_core_rules
        identity_verified = (student['program_type']=='SINGLE' and student.get('student_category')=='DOMESTIC_REGULAR'
                             and bool(student.get('student_category_evidence_id')) and bool(student.get('applicability_evidence_id')))
        inputs_confirmed = recognition['complete'] and bool(student.get('completion_coverage_evidence_id')) and not any(
            r['status']=='NEEDS_INFORMATION' for r in results)
        boundary_needs = scope_conflicts + [f'UNHANDLED_APPLICABILITY_CONDITION:{c}' for c in unhandled]
        if student['program_type']!='SINGLE':
            boundary_needs.append('SECOND_PROGRAM_RULE_COVERAGE')
        if not identity_verified:
            boundary_needs.append('VERIFIED_STUDENT_CATEGORY_AND_APPLICABILITY')
        if not student.get('completion_coverage_evidence_id'):
            boundary_needs.append('COMPLETE_VERIFIED_TRANSCRIPT_EVIDENCE')
        coverage_details = {
            'loaded_rules_executed':loaded_complete,
            'applicable_conditions_identified':identity_verified and not unhandled and not scope_conflicts,
            'unhandled_conditions':unhandled,'question_scope_conflicts':scope_conflicts,
            'unverified_rule_ids':[r['rule_id'] for r in bundle['rules'] if r['verification_status']!='VERIFIED'],
            'required_student_inputs_confirmed':bool(inputs_confirmed),
            'directly_calculated_rule_ids':[r['rule_id'] for r in results if r.get('evaluation_basis')=='DIRECT_RULE_CALCULATION'],
            'official_result_rule_ids':[r['rule_id'] for r in results if r.get('evaluation_basis')=='OFFICIAL_RESULT_INPUT'],
            'exempted_rule_ids':[r['rule_id'] for r in results if r.get('evaluation_basis')=='VERIFIED_PDF_EXEMPTION'],
            'certification_subrules_computed':False,
            'equivalence_review_required':any('equivalence' in c or 'replacement' in c for c in unhandled),
            'source_scope':'REGISTERED_CORE_RULES_WITH_OFFICIAL_FINAL_OUTCOMES',
            'applicability_source_refs':['CURRICULUM-APPLICATION-2026'],
            'condition_source_refs':{c:(['GRAD-RULES-2026'] if c=='STANDARD_DURATION_EXCEEDED' else
                ['CURRICULUM-APPLICATION-2026'] if c in {'READMISSION','DEPARTMENT_TRANSFER','TRANSFER'} else []) for c in unhandled},
            'credit_policy_year':student.get('credit_policy_year'),'catalog_year':student.get('catalog_year'),
            'admission_year':student.get('admission_year')}
        coverage_complete = loaded_complete and coverage_details['applicable_conditions_identified'] and inputs_confirmed
        needs.extend(boundary_needs)
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
        if not graph.catalog.get('coverage_policy') and (student.get("equivalence_review_status") != "VERIFIED" or not student.get("equivalence_review_evidence_id")):
            coverage_gaps.append("OFFICIAL_EQUIVALENCE_REVIEW")
        coverage_gaps.extend(boundary_needs)
        _event(trace, "COVERAGE_CHECK", result="COMPLETE" if coverage_complete else "INCOMPLETE",
               missing=coverage_gaps, **({'details':coverage_details} if coverage_details else {}))
        if coverage_details and coverage_details['question_scope_conflicts']:
            graduation='UNKNOWN'
            decision_status='NEEDS_INFORMATION'
        elif decision_status == "UNSATISFIED":
            graduation = "NOT_ELIGIBLE_PDF"
        elif decision_status == "SATISFIED" and coverage_complete:
            graduation = "ELIGIBLE_PDF"
        else:
            graduation = "UNKNOWN"
            if boundary_needs and decision_status == 'SATISFIED':
                decision_status='NEEDS_INFORMATION'
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
    if coverage_details is not None:
        decision['coverage_details']=coverage_details
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
        targets = policy_targets(query, student)
        scoped_rule_topics = topics & POLICY_RULE_TOPICS if any(t['year'] in (None,2026) for t in targets) and not query.get("historical_scope_requested") else set()
        operations = ([] if not scoped_rule_topics else ["FETCH_REQUIREMENTS"])
        if "REQUIRED_COURSES" in scoped_rule_topics or ("MULTI_PROGRAM" in topics and query.get("program_type", student["program_type"]) == "MINOR"):
            operations.append("FETCH_CATALOG_ENTRY")
        if topics & POLICY_FACT_TOPICS or bool(topics & {"GENERAL_CREDITS", "GENERAL_AREAS"}) or (not scoped_rule_topics and bool(topics & POLICY_RULE_TOPICS)):
            operations.append("FETCH_POLICY_FACTS")
    elif query["intent"] == "CATALOG_AGGREGATE":
        operations = ["FETCH_CATALOG_SET", "AGGREGATE_" + query["aggregate"]]
    elif query["intent"] == "PLACEMENT_LOOKUP":
        operations = ["FETCH_CATALOG_SET", "FILTER_CURRICULUM_PLACEMENT", "GROUP_CURRICULUM_PLACEMENT"]
    elif query["intent"] == "REMAINING_PLAN":
        operations = ["FETCH_CATALOG_ENTRY", "FETCH_REQUIREMENTS", "FETCH_CATALOG_SET",
                      "FETCH_COURSE_REQUIREMENT_LINKS", "SUMMARIZE_REMAINING", "CLASSIFY_CANDIDATES"]
        if "placement_filter" in query or query.get("group_by_placement"):
            operations += ["FILTER_CURRICULUM_PLACEMENT", "GROUP_CURRICULUM_PLACEMENT"]
    else:
        operations = ["FETCH_CATALOG_ENTRY"] if query["intent"] == "COURSE_LOOKUP" else ["FETCH_CATALOG_ENTRY", "FETCH_REQUIREMENTS"]
    if graph.catalog.get('coverage_policy') and query['intent'] not in {'COURSE_LOOKUP','POLICY_LOOKUP','CATALOG_AGGREGATE','PLACEMENT_LOOKUP','ENTITY_CHECK'}:
        operations.append('FETCH_POLICY_FACTS')
    _event(trace, "QUERY_PLAN", intent=query["intent"], operations=operations, input_hash=input_id,
           authoritative_document_set_id=document_set["set_id"],
           authoritative_document_set_version=document_set["set_version"],
           ruleset_id=ruleset["ruleset_id"], ruleset_version=ruleset["ruleset_version"],
           student_state_version=student_version, candidate_rule_ids=ruleset["included_rule_ids"],
           placement_filter=query.get("placement_filter"),
           requested_year_targets=query.get('year_targets',[]), declared_conditions=query.get('declared_conditions',[]),
           placement_classifications=query.get("classifications") if query["intent"] in {"PLACEMENT_LOOKUP", "REMAINING_PLAN"} else None,
           document_relation_ids=[r["relation_id"] for r in graph.catalog["document_relations"]])
    scenario_decision = None
    requested_catalog_scopes=[t for t in query.get('year_targets',[]) if
        t['basis'] in {'CATALOG_YEAR','CREDIT_POLICY_YEAR'} and (t['year']!=2026 or t.get('invalid_range'))]
    if query["intent"] == "POLICY_LOOKUP":
        decision = _policy_lookup(graph, student, query, trace, bundle)
    elif requested_catalog_scopes and query['intent'] in {'COURSE_LOOKUP','CATALOG_AGGREGATE','PLACEMENT_LOOKUP','ENTITY_CHECK'}:
        needs=[f"REQUESTED_CATALOG_SCOPE_UNAVAILABLE:{t['basis']}:{t['year']}" for t in requested_catalog_scopes]
        decision={'contract_version':'1','intent':query['intent'],'decision_status':'NEEDS_INFORMATION',
            'graduation_outcome':'NOT_REQUESTED','lookup_status':'NEEDS_INFORMATION','lookup_result':None,
            'requirement_results':[],'credited_amount':None,'missing_amount':None,'missing_courses':None,
            'needs_information':needs,'data_snapshot_id':graph.snapshot_id,'rule_set_hash':digest(graph.catalog['requirements'])}
        _rehash_decision(decision)
        _event(trace,'APPLICABILITY',result='NEEDS_INFORMATION',missing=needs)
        _event(trace,'DECISION',result={'lookup_status':'NEEDS_INFORMATION'})
    elif query["intent"] == "CATALOG_AGGREGATE":
        decision = _catalog_aggregate(graph, query, trace, bundle)
    elif query["intent"] == "PLACEMENT_LOOKUP":
        decision = _placement_lookup(graph, query, trace, bundle)
    elif (student["applicability_status"] != "VERIFIED" or student.get("credit_policy_year") != 2026 or student.get("catalog_year") != 2026) and not (
        query["intent"] == "COURSE_LOOKUP" and query.get("placement_requested")
    ):
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
            if "placement_filter" in query or query.get("group_by_placement"):
                active = [c for c in candidates if c["candidate_status"] in {"REQUIRED", "ELIGIBLE_OPTION"}
                          and (not query.get("classifications") or c["course_classification"] in query["classifications"])]
                selection = select_placement(active, query.get("placement_filter", {}))
                selected = set(selection["matched_course_ids"])
                decision["placement_view"] = {"selection": selection,
                    "groups": group_placement([c for c in active if c["course_id"] in selected]),
                    "next_term_basis": query.get("next_term_basis")}
                _event(trace, "PLACEMENT_SELECTION", input_refs=[c["provenance"]["entry_id"] for c in active], result=selection)
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
            conflict=next((c for c in graph.catalog.get('catalog_conflicts',[]) if c['course_id']==query['course_id']),None)
            if conflict:
                decision['lookup_result']['catalog_conflict']=deepcopy(conflict)
                decision['lookup_status']='CONFLICTED'
                _event(trace,'CATALOG_CONFLICT_LOOKUP',source_document_id=graph.catalog['source_document_id'],
                       source_hash=graph.catalog['source_sha256'],result=deepcopy(conflict))
            if not found:
                decision["decision_status"] = "NEEDS_INFORMATION"
                decision["needs_information"] = sorted(set([*decision["needs_information"],
                                                             f"CATALOG_CLASSIFICATION:{query['course_id']}"]))
            _rehash_decision(decision)
            prior = next(e for e in reversed(trace) if e["event_type"] == "DECISION")
            prior["result"].update({"decision_id": decision["decision_id"],
                                    "status": decision["decision_status"]})
            _event(trace, "ENTITY_RESOLUTION", course_id=query["course_id"],
                   result="VERIFIED" if found else "CONFLICTED" if conflict else "NOT_FOUND")
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
                                              | ({student['disability_status']['evidence_id']} if isinstance(student.get('disability_status'),dict) and student['disability_status'].get('evidence_id') else set())
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
