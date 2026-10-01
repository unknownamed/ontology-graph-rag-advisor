"""Source-backed curriculum placement, distinct from live offerings and eligibility."""
from __future__ import annotations

import re

TERMS = {"SEMESTER_1": "1학기", "SEMESTER_2": "2학기", "SUMMER": "하계", "WINTER": "동계"}
CLASSES = {"MAJOR_REQUIRED", "MAJOR_ELECTIVE", "GENERAL_BASIC", "GENERAL_BALANCED", "GENERAL_EXPANDED"}


def validate_filter(value: dict) -> None:
    if not isinstance(value, dict) or set(value) - {"grade", "terms", "term_match"}:
        raise ValueError("Placement filter fields are not allowlisted")
    if "grade" in value and (type(value["grade"]) is not int or not 1 <= value["grade"] <= 4):
        raise ValueError("Placement grade must be 1..4")
    terms = value.get("terms", [])
    if not isinstance(terms, list) or len(terms) > 4 or any(t not in TERMS for t in terms):
        raise ValueError("Placement terms are not allowlisted")
    if value.get("term_match", "ANY") not in {"ANY", "ALL"}:
        raise ValueError("Placement term matching must be ANY or ALL")


def normalize_placement(entry: dict) -> dict:
    """Decode only literal table cells; a missing grade never means all grades."""
    raw = entry.get("grade_term")
    term_raw = entry.get("placement_term_raw")
    grade_scope, grades, slots = "MISSING", [], []
    term_status, grade_status = "MISSING", "MISSING"
    groups = []
    if raw:
        # Multiple pairs retain their pairings rather than a fabricated cross product.
        for group in str(raw).split(";"):
            pair = re.fullmatch(r"(전|[1-4](?:[·.,][1-4])*)-(1|2|1,2|하·동|하|동)", group.strip())
            if not pair:
                groups = []
                term_status = grade_status = "UNVERIFIED"
                break
            grade_text, term_text = pair.groups()
            scope = "ALL" if grade_text == "전" else "LIST"
            values = [] if scope == "ALL" else sorted(set(map(int, re.split(r"[·.,]", grade_text))))
            groups.append((scope, values, term_text))
        if groups:
            grade_scope = "ALL" if all(g[0] == "ALL" for g in groups) else "LIST"
            grades = sorted({v for _, values, _ in groups for v in values})
            grade_status = "VERIFIED"
    elif term_raw:
        groups = [("MISSING", [], str(term_raw).replace("\n", "·").replace("하계", "하").replace("동계", "동"))]
    mapping = {"1": ["SEMESTER_1"], "2": ["SEMESTER_2"], "1,2": ["SEMESTER_1", "SEMESTER_2"],
               "하·동": ["SUMMER", "WINTER"], "하": ["SUMMER"], "동": ["WINTER"]}
    if groups:
        if all(text in mapping for _, _, text in groups):
            term_status = "VERIFIED"
            slots = [{"grade": grade, "grade_scope": scope, "term": term}
                     for scope, values, text in groups for grade in (values or [None]) for term in mapping[text]]
        else:
            term_status = "UNVERIFIED"
    status = entry.get("placement_verification_status", entry.get("verification_status", "UNVERIFIED"))
    if entry.get("verification_status", "UNVERIFIED") != "VERIFIED":
        status = entry.get("verification_status", "UNVERIFIED")
    if status != "VERIFIED":
        term_status = status if term_status != "MISSING" else "MISSING"
        grade_status = status if grade_status != "MISSING" else "MISSING"
    return {"normalization_version": "1", "curriculum_id": entry.get('curriculum_id'), "raw_grade_term": raw, "raw_term": term_raw,
            "grade_scope": grade_scope, "grades": grades, "slots": slots,
            "term_verification_status": term_status, "grade_verification_status": grade_status,
            "source": entry["source"], "fact_id": entry["fact_id"],
            "actual_offering_status": "NOT_VERIFIED", "student_eligibility_status": "NOT_VERIFIED"}


def placement_match(placement: dict, filters: dict) -> str:
    validate_filter(filters)
    grade, terms = filters.get("grade"), filters.get("terms", [])
    if placement["term_verification_status"] != "VERIFIED":
        return "NEEDS_VERIFICATION"
    slots = placement["slots"]
    if grade is not None:
        # Known term exclusion is safe even when the table has no grade column.
        available_terms = {s["term"] for s in slots}
        possible = set(terms).issubset(available_terms) if filters.get('term_match', 'ANY') == 'ALL' else bool(set(terms) & available_terms)
        if terms and not possible:
            return "NO_MATCH"
        if placement["grade_verification_status"] != "VERIFIED":
            return "NEEDS_VERIFICATION"
        slots = [s for s in slots if s["grade_scope"] == "ALL" or s["grade"] == grade]
        if not slots:
            return "NO_MATCH"
    available = {s["term"] for s in slots}
    if not terms:
        return "MATCH"
    matches = set(terms).issubset(available) if filters.get("term_match", "ANY") == "ALL" else bool(set(terms) & available)
    return "MATCH" if matches else "NO_MATCH"


def placement_label(placement: dict) -> str:
    if placement["term_verification_status"] != "VERIFIED":
        raw = placement.get("raw_grade_term") or placement.get("raw_term")
        return "편성학기 확인 필요" + (f"(원문: {raw})" if raw else "")
    grouped = {}
    for slot in placement["slots"]:
        grouped.setdefault((slot["grade_scope"], slot["grade"]), []).append(TERMS[slot["term"]])
    return "; ".join(("전 학년 " if scope == "ALL" else f"{grade}학년 " if grade is not None else "학년 미기재 · ")
                     + "·".join(terms) for (scope, grade), terms in grouped.items())


def select_placement(courses: list[dict], filters: dict) -> dict:
    """Return unknown schedules separately; never silently discard them."""
    partition = {"matched_course_ids": [], "needs_verification_course_ids": [], "excluded_course_ids": []}
    keys = {"MATCH": "matched_course_ids", "NEEDS_VERIFICATION": "needs_verification_course_ids", "NO_MATCH": "excluded_course_ids"}
    for course in courses:
        placement = course.get("curriculum_placement") or normalize_placement(course)
        partition[keys[placement_match(placement, filters)]].append(course["course_id"])
    return {"filters": filters, **{key: sorted(ids) for key, ids in partition.items()}}


def group_placement(courses: list[dict]) -> list[dict]:
    groups = {term: [] for term in TERMS}
    groups["NEEDS_VERIFICATION"] = []
    for course in courses:
        p = course["curriculum_placement"]
        terms = {s["term"] for s in p["slots"]} if p["term_verification_status"] == "VERIFIED" else {"NEEDS_VERIFICATION"}
        for term in terms:
            groups[term].append(course["course_id"])
    return [{"term": term, "label": TERMS.get(term, "편성학기 확인 필요"), "course_ids": sorted(ids), "course_count": len(ids)}
            for term, ids in groups.items()]
