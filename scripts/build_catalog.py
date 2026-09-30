"""Build the verified 2026 computer-engineering catalog from the source index.

The scope document is a visually checked transcription of the sole curriculum PDF.
This script refuses to build when that PDF or the 43 indexed rows change.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from curriculum_assistant.authority import core_registry  # noqa: E402
INDEX = ROOT / "data/processed/source_index.json"
SCOPE = ROOT / "docs/design/computer_engineering_scope.md"
OUTPUT = ROOT / "data/processed/computer_engineering_2026.json"
GENERAL = ROOT / "data/processed/general_education_2026.json"


def build() -> dict:
    index = json.loads(INDEX.read_text(encoding="utf-8"))
    source = index["source"]
    pdf = ROOT / source["path"]
    actual_hash = hashlib.sha256(pdf.read_bytes()).hexdigest()
    if actual_hash != source["sha256"]:
        raise ValueError("Curriculum PDF hash differs from the verified source index")
    scope = SCOPE.read_text(encoding="utf-8")
    locators = {r["course_code"]: r for r in index["computer_engineering_focus"]["course_row_locators"]}
    courses = []
    for line in scope.splitlines():
        if not re.match(r"^\| CDA\d{4} \|", line):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) != 7:
            raise ValueError(f"Bad catalog row: {line}")
        code, name, credits, classification, grade_term, minor_mark, page = cells
        locator = locators.get(code)
        if not locator or int(page) != locator["pdf_page"] or locator["verification"] != "visual_cross_check":
            raise ValueError(f"Course locator mismatch: {code}")
        if classification not in {"전공필수", "전공선택"} or minor_mark not in {"", "※"}:
            raise ValueError(f"Unknown classification or footnote: {code}")
        courses.append({
            "course_id": code,
            "name": name,
            "catalog_credits": int(credits),
            "classification": "MAJOR_REQUIRED" if classification == "전공필수" else "MAJOR_ELECTIVE",
            "grade_term": grade_term,
            "minor_required": minor_mark == "※",
            "catalog_year": 2026,
            "department_id": "DEPT-COMPUTER-ENGINEERING",
            "verification_status": "VERIFIED",
            "fact_id": f"CE-2026-COURSE-{code}",
            "source": {
                "document_id": "CURRICULUM-2026",
                "pdf_page": int(page),
                "printed_page": locator["printed_page"],
                "section": "04장 Ⅱ 전공 교과목 편성표",
                "table": locator["source_table_id"],
                "row_order": locator["row_order"],
                "footnote": "※ 표시 과목은 부전공 필수" if minor_mark else None,
            },
        })
    if len(courses) != 43 or len(locators) != 43 or len({c["course_id"] for c in courses}) != 43:
        raise ValueError("Expected 43 unique, indexed course rows")
    if sum(c["catalog_credits"] for c in courses) != 144:
        raise ValueError("Catalog credit checksum mismatch")
    required = [c for c in courses if c["classification"] == "MAJOR_REQUIRED"]
    if len(required) != 9 or sum(c["catalog_credits"] for c in required) != 21:
        raise ValueError("Required-course checksum mismatch")
    if sum(c["minor_required"] for c in courses) != 3:
        raise ValueError("Minor-required footnote checksum mismatch")
    if {c["course_id"] for c in courses} != set(locators):
        raise ValueError("Index and transcription contain different courses")
    locs = {r["id"]: r for r in index["computer_engineering_focus"]["source_locators"]}
    for key in ("CE-CREDITS", "CE-2026-OVERVIEW", "CE-2026-GRAD"):
        if key not in locs or locs[key]["verification"] != "visual_cross_check":
            raise ValueError(f"Credit requirement source missing: {key}")
    requirements = [
        {"rule_id": "R-CE-2026-MAJOR-REQUIRED-CREDITS", "rule_type": "MIN_CREDITS", "area": "MAJOR_REQUIRED", "required_value": 21},
        {"rule_id": "R-CE-2026-MAJOR-ELECTIVE-CREDITS", "rule_type": "MIN_CREDITS", "area": "MAJOR_ELECTIVE", "required_value": 24},
        {"rule_id": "R-CE-2026-MAJOR-TOTAL-CREDITS", "rule_type": "MIN_CREDITS", "area": "MAJOR_TOTAL", "required_value": 78, "program_types": ["SINGLE", "MINOR"]},
        {"rule_id": "R-CE-2026-ADVANCED-CREDITS", "rule_type": "MIN_CREDITS", "area": "MAJOR_ADVANCED", "required_value": 33,
         "base_major_credits": 45, "calculation": "MAX(0, MAJOR_TOTAL - 45)", "program_types": ["SINGLE", "MINOR"]},
        {"rule_id": "R-CE-2026-DOUBLE-MAJOR-MINIMUM", "rule_type": "MIN_CREDITS", "area": "MAJOR_TOTAL", "required_value": 45, "program_types": ["DOUBLE"]},
        {"rule_id": "R-CE-2026-REQUIRED-COURSES", "rule_type": "REQUIRED_COURSES", "course_ids": [c["course_id"] for c in required]},
    ]
    for rule in requirements:
        rule.update({"department_id": "DEPT-COMPUTER-ENGINEERING", "credit_policy_year": 2026,
                     "verification_status": "VERIFIED", "source_refs": ["CE-CREDITS", "CE-2026-OVERVIEW", "CE-2026-GRAD"] if rule["rule_type"] == "MIN_CREDITS" else ["CE-COURSES"]})
    general = json.loads(GENERAL.read_text(encoding="utf-8"))
    if general["source_sha256"] != actual_hash or len(general["courses"]) != 280:
        raise ValueError("Visually checked general-education subset is missing or stale")
    if len({c["course_id"] for c in general["courses"]}) != 280 or any(c["verification_status"] != "VERIFIED" for c in general["courses"]):
        raise ValueError("General-education catalog must contain 280 unique verified rows")
    extra_locs = [
        {"id": "CURRICULUM-APPLICATION-2026", "title": "교육과정 적용과 자유선택", "pdf_page_start": 13, "pdf_page_end": 13,
         "printed_page_start": 5, "printed_page_end": 5, "table_section_note": "01장 2-2 나–바·2-3 가–라", "verification": "visual_cross_check"},
        {"id": "COURSE-REPEAT-2026", "title": "동일·대체과목 이수", "pdf_page_start": 14, "pdf_page_end": 14,
         "printed_page_start": 6, "printed_page_end": 6, "table_section_note": "01장 2-5 가·나", "verification": "visual_cross_check"},
        {"id": "GE-RULES-2026", "title": "교양 이수학점·필수군·상한", "pdf_page_start": 33, "pdf_page_end": 33,
         "printed_page_start": 25, "printed_page_end": 25, "table_section_note": "02장 2-1 가–다·각주", "verification": "visual_cross_check"},
        {"id": "GE-COURSES-2026", "title": "교양 과목 편성표", "pdf_page_start": 34, "pdf_page_end": 45,
         "printed_page_start": 26, "printed_page_end": 37, "table_section_note": "02장 2-2; PDF 34–45 전 페이지 표 행 대조, 코드 충돌 2행 제외", "verification": "all_unambiguous_rows_visual_cross_check"},
        {"id": "GRAD-RULES-2026", "title": "졸업 요건과 논문 수강신청", "pdf_page_start": 565, "pdf_page_end": 565,
         "printed_page_start": 557, "printed_page_end": 557, "table_section_note": "08장 1, 2 가·나", "verification": "visual_cross_check"},
        {"id": "CERT-APPLICABILITY-2026", "title": "졸업인증제 적용·면제", "pdf_page_start": 569, "pdf_page_end": 569,
         "printed_page_start": 561, "printed_page_end": 561, "table_section_note": "08장 3-2", "verification": "visual_cross_check"},
        {"id": "DOUBLE-MAJOR-POLICY-2026", "title": "복수전공 이수와 중복 인정", "pdf_page_start": 476, "pdf_page_end": 476,
         "printed_page_start": 468, "printed_page_end": 468, "table_section_note": "05장 복수전공 1", "verification": "visual_cross_check"},
        {"id": "MINOR-POLICY-2026", "title": "부전공 이수와 중복 인정", "pdf_page_start": 477, "pdf_page_end": 477,
         "printed_page_start": 469, "printed_page_end": 469, "table_section_note": "05장 부전공 2", "verification": "visual_cross_check"},
    ]
    extra_rules = [
        {"rule_id": "R-GE-2026-BASIC-CREDITS", "rule_type": "MIN_CREDITS", "area": "GENERAL_BASIC", "required_value": 9, "source_refs": ["GE-RULES-2026"]},
        {"rule_id": "R-GE-2026-BALANCED-CREDITS", "rule_type": "MIN_CREDITS", "area": "GENERAL_BALANCED", "required_value": 12, "source_refs": ["GE-RULES-2026"]},
        {"rule_id": "R-GE-2026-TOTAL-CREDITS", "rule_type": "MIN_CREDITS", "area": "GENERAL_TOTAL", "required_value": 34, "source_refs": ["GE-RULES-2026", "CE-CREDITS"]},
        {"rule_id": "R-GE-2026-BALANCED-AREAS", "rule_type": "ALL_AREAS", "areas": ["DIGITAL_COMMUNICATION", "HUMANITIES_ARTS", "SOCIETY_CULTURE", "SCIENCE_TECHNOLOGY"], "source_refs": ["GE-RULES-2026"]},
        {"rule_id": "R-GE-2026-FUTURE-DESIGN", "rule_type": "ANY_COURSE", "course_ids": ["GEA8001"], "source_refs": ["GE-RULES-2026", "GE-COURSES-2026"]},
        {"rule_id": "R-GE-2026-AI-FOUNDATION", "rule_type": "ANY_COURSE", "course_ids": ["GEA8810", "GEA8812", "GEA8813", "GEA8814"], "source_refs": ["GE-RULES-2026", "GE-COURSES-2026"]},
        {"rule_id": "R-GE-2026-WRITING", "rule_type": "ANY_COURSE", "course_ids": ["GEA8510", "GEA8511", "GEA8512"], "source_refs": ["GE-RULES-2026", "GE-COURSES-2026"]},
        {"rule_id": "R-GE-2026-ENGLISH", "rule_type": "ANY_COURSE_OR_EXEMPTION", "course_ids": ["GEA8704", "GEA8705"], "source_refs": ["GE-RULES-2026", "GE-COURSES-2026"]},
        {"rule_id": "R-GE-2026-CREDIT-CAP", "rule_type": "CREDIT_CAP", "area": "GENERAL_TOTAL", "required_value": 42, "source_refs": ["GE-RULES-2026"]},
        {"rule_id": "R-GRAD-2026-TOTAL-CREDITS", "rule_type": "MIN_CREDITS", "area": "GRADUATION_TOTAL", "required_value": 130, "source_refs": ["CE-2026-GRAD", "CE-CREDITS"]},
        {"rule_id": "R-GRAD-2026-THESIS-PASSED", "rule_type": "REQUIRED_EVIDENCE", "evidence_key": "thesis_passed", "source_refs": ["GRAD-RULES-2026"]},
        {"rule_id": "R-GRAD-2026-THESIS-ENROLLED", "rule_type": "REQUIRED_EVIDENCE", "evidence_key": "thesis_final_semester_enrollment", "source_refs": ["GRAD-RULES-2026"]},
        {"rule_id": "R-GRAD-2026-CERTIFICATION", "rule_type": "REQUIRED_EVIDENCE", "evidence_key": "graduation_certification_passed", "source_refs": ["GRAD-RULES-2026", "CERT-APPLICABILITY-2026"]},
    ]
    for rule in extra_rules:
        rule.update({"department_id": "DEPT-COMPUTER-ENGINEERING", "credit_policy_year": 2026,
                     "verification_status": "VERIFIED", "program_types": ["SINGLE", "MINOR", "DOUBLE"]})
    policy_facts = [
        {"policy_fact_id": "PF-APPLICATION-ADMISSION", "topic": "APPLICABILITY", "predicate": "DEFAULT_CREDIT_POLICY_BASIS",
         "value": {"basis": "ADMISSION_YEAR", "exception_requires": "LOWER_REVISED_AREA_MINIMUM_OR_COMMITTEE_APPROVAL"},
         "source_refs": ["CURRICULUM-APPLICATION-2026"]},
        {"policy_fact_id": "PF-APPLICATION-COURSES", "topic": "APPLICABILITY", "predicate": "COURSE_TABLE_BASIS",
         "value": {"basis": "REVISED_CURRICULUM", "academic_event_exceptions": ["READMISSION", "DEPARTMENT_TRANSFER"]},
         "source_refs": ["CURRICULUM-APPLICATION-2026"]},
        {"policy_fact_id": "PF-FREE-CHOICE", "topic": "FREE_CHOICE", "predicate": "COUNTS_AS_RESIDUAL",
         "value": {"includes": ["OTHER_DEPARTMENT_MAJOR", "TEACHER_EDUCATION", "LIFELONG_EDUCATOR", "MILITARY", "OTHER_DEPARTMENT_OFFERING"], "counts": True},
         "source_refs": ["CURRICULUM-APPLICATION-2026"]},
        {"policy_fact_id": "PF-REPEAT", "topic": "EQUIVALENCE", "predicate": "SAME_COURSE_REPEAT",
         "value": {"previous_grade_removed": True, "designation_required": True},
         "source_refs": ["COURSE-REPEAT-2026"]},
        {"policy_fact_id": "PF-SUBSTITUTE", "topic": "EQUIVALENCE", "predicate": "REPLACEMENT_COURSE",
         "value": {"designation_required": True, "student_enrollment_choice_required": True,
                   "designation_list_status": "UNVERIFIED"}, "source_refs": ["COURSE-REPEAT-2026"]},
        {"policy_fact_id": "PF-CE-RECOMMENDATIONS", "topic": "RECOMMENDATIONS", "predicate": "RECOMMENDED_NOT_REQUIRED",
         "value": {"courses": [{"course_id": "GEA7260", "name": "컴퓨터개론", "credits": 3, "general_area": "SCIENCE_TECHNOLOGY"},
                                {"course_id": "GEA7261", "name": "컴퓨터프로그래밍", "credits": 3, "general_area": "DIGITAL_COMMUNICATION"},
                                {"course_id": "GEA7301", "name": "공업수학", "credits": 3, "general_area": "SCIENCE_TECHNOLOGY"}],
                   "mandatory": False},
         "source_refs": ["CE-RECOMMENDED"]},
        {"policy_fact_id": "PF-CE-TRANSITION", "topic": "TRANSITION", "predicate": "YEAR_SCOPED_TRANSITION_EXISTS",
         "value": {"applicable_catalog_years": {"min": 2002, "max": 2024}, "automatic_for_2026_entrant": False,
                   "student_specific_review_required": True,
                   "retroactive_credit_bands": [
                       {"first_year": 2002, "last_year": 2010, "general_total": 26, "major_required": 15, "major_elective": 48},
                       {"first_year": 2011, "last_year": 2020, "general_total": 26, "major_required": 21, "major_elective": 48},
                       {"first_year": 2021, "last_year": 2024, "general_total": 26, "major_required": 21,
                        "major_elective": 57, "minimum_major_elective_recognition": 35}],
                   "post_2012_graduation_2002_to_2007_uses_2008_curriculum": True},
         "source_refs": ["CE-TRANSITION"]},
        {"policy_fact_id": "PF-DOUBLE-2026", "topic": "MULTI_PROGRAM", "predicate": "DOUBLE_MAJOR_SCOPE",
         "value": {"program_type": "DOUBLE", "main_and_second_minimum_required": True,
                   "both_required_courses": True, "main_thesis_required": True, "second_thesis_exempt": True,
                   "overlap_limit_from_2025_selection": 9, "overlap_limit_earlier_selection": 21,
                   "overlap_excluded_from_graduation_total": True, "official_selection_required": True},
         "source_refs": ["DOUBLE-MAJOR-POLICY-2026", "CE-2026-OVERVIEW"]},
        {"policy_fact_id": "PF-MINOR-2026", "topic": "MULTI_PROGRAM", "predicate": "MINOR_SCOPE",
         "value": {"program_type": "MINOR", "minor_credit_minimum": 21,
                   "designated_minor_required_courses": True, "overlap_limit": 9,
                   "overlap_excluded_from_graduation_total": True, "official_selection_required": True},
         "source_refs": ["MINOR-POLICY-2026", "CE-2026-OVERVIEW"]},
    ]
    for fact in policy_facts:
        fact.update({"department_id": "DEPT-COMPUTER-ENGINEERING", "verification_status": "VERIFIED"})
    indexed_policy_pages = index["runtime_verification"]["policy_fact_source_pages"]
    all_locators = {r["id"]: r for r in [*locs.values(), *extra_locs]}
    if set(indexed_policy_pages) != {fact["policy_fact_id"] for fact in policy_facts}:
        raise ValueError("Policy fact IDs differ from the source index")
    for fact in policy_facts:
        if indexed_policy_pages[fact["policy_fact_id"]] != all_locators[fact["source_refs"][0]]["pdf_page_start"]:
            raise ValueError(f"Policy fact source page mismatch: {fact['policy_fact_id']}")
    # The historical rows are source facts, not executable 2026 requirements.
    # In particular, they do not supply historical course classifications or exceptions.
    historical_bands = [
        (2006, 2007, 29, 12, 48, 0, 60, 140, "CE-YEAR-GRAD-2006-2012"),
        (2008, 2010, 29, 15, 48, 0, 63, 140, "CE-YEAR-GRAD-2006-2012"),
        (2011, 2012, 29, 21, 48, 0, 69, 140, "CE-YEAR-GRAD-2006-2012"),
        (2013, 2017, 29, 21, 48, 0, 69, 140, "CE-YEAR-GRAD-2013-2019"),
        (2018, 2020, 26, 21, 48, 0, 69, 130, "CE-YEAR-GRAD-2013-2019"),
        (2021, 2024, 26, 21, 57, 0, 78, 130, "CE-YEAR-GRAD-2020-2024"),
        (2025, 2025, 34, 21, 24, 33, 78, 130, "CE-YEAR-GRAD-2025"),
    ]
    historical = []
    for first, last, general_credits, required, elective, advanced, major, graduation, ref in historical_bands:
        for year in range(first, last + 1):
            row_ref = "CE-YEAR-GRAD-2020-2024" if year == 2020 else ref
            values = {"general_total": general_credits, "major_required": required, "major_elective": elective,
                      "major_total": major, "graduation_total": graduation}
            if advanced:
                values["major_advanced"] = advanced
            historical.append({"policy_fact_id": f"PF-CE-HISTORICAL-{year}", "topic": "HISTORICAL_CREDITS",
                               "predicate": "ANNUAL_SINGLE_MAJOR_CREDIT_ROW", "curriculum_id": f"CURRICULUM-CE-{year}",
                               "entry_year": year, "program_types": ["SINGLE"], "value": values,
                               "department_id": "DEPT-COMPUTER-ENGINEERING", "source_refs": [row_ref],
                               "verification_status": "VERIFIED"})
    if len(historical) != 20 or any(row["source_refs"][0] not in all_locators for row in historical):
        raise ValueError("Historical source rows are incomplete")
    catalog = {"schema_version": "1", "source_document_id": "CURRICULUM-2026", "source_sha256": actual_hash,
               "department": {"department_id": "DEPT-COMPUTER-ENGINEERING", "name": "컴퓨터공학과", "source_ref": "CE-SECTION"},
               "curriculum": {"curriculum_id": "CURRICULUM-CE-2026", "year": 2026},
               "source_locators": [*locs.values(), *extra_locs], "courses": [*courses, *general["courses"]],
               "requirements": [*requirements, *extra_rules], "policy_facts": policy_facts,
               "historical_credit_rows": historical,
               "coverage_manifest": {"completeness": "CONDITIONAL", "scope": "2026 computer-engineering single major, domestic regular student, verified transcript and official outcomes",
                                     "missing_families": ["OTHER_MAJOR_IF_APPLICABLE", "HISTORICAL_APPLICABILITY", "UNVERIFIED_EQUIVALENCE_DESIGNATIONS"]}}
    core_registry(catalog, source["path"], actual_hash)
    OUTPUT.write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return catalog


if __name__ == "__main__":
    result = build()
    print(f"Built {len(result['courses'])} sourced course entries at {OUTPUT}")
