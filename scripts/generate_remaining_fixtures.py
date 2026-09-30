"""Generate synthetic StudentStates and independent RuleSet-v1 expectations.

Grade labels are metadata only. No real upload or evaluation answer is read.
"""
from __future__ import annotations

import json
import sys
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]
from generate_mock_2026_transcripts import catalog_v1, oracle, select_complete_courses  # noqa: E402

DEST = ROOT / "evaluation" / "fixtures" / "remaining_2026"


def _basis(course: dict, rule: dict) -> bool:
    """Fixture-side Rule IR interpretation, independent of graph candidate code."""
    cls = course["classification"]
    if rule["rule_type"] in {"REQUIRED_COURSES", "ANY_COURSE", "ANY_COURSE_OR_EXEMPTION"}:
        return course["course_id"] in rule["course_ids"]
    if rule["rule_type"] == "ALL_AREAS":
        return cls == "GENERAL_BALANCED" and course.get("general_area") in rule["areas"]
    if rule["rule_type"] != "MIN_CREDITS" or course["catalog_credits"] == 0:
        return False
    area = rule["area"]
    return ((area == "GRADUATION_TOTAL" and cls.startswith(("GENERAL_", "MAJOR_")))
            or (area in {"MAJOR_TOTAL", "MAJOR_ADVANCED"} and cls.startswith("MAJOR_"))
            or (area == "GENERAL_TOTAL" and cls.startswith("GENERAL_"))
            or area == cls)


def _expected_candidates(selected: set[str], catalog: dict, expected: dict) -> dict[str, str]:
    rules = {rule["rule_id"]: rule for rule in catalog["requirements"]}
    unmet = {rid for rid, status in expected["expected_requirement_results"].items() if status == "UNSATISFIED"}
    required = set(rules["R-CE-2026-REQUIRED-COURSES"]["course_ids"]) - selected
    present_areas = {course.get("general_area") for course in catalog["courses"] if course["course_id"] in selected}
    general_cap = next(r["required_value"] for r in rules.values() if r["rule_type"] == "CREDIT_CAP")
    general_count = sum(c["catalog_credits"] for c in catalog["courses"] if c["course_id"] in selected and c["classification"].startswith("GENERAL_"))
    result = {}
    for course in catalog["courses"]:
        if course["verification_status"] != "VERIFIED" or course.get("eligible_scope", "GENERAL") != "GENERAL":
            result[course["course_id"]] = "NOT_APPLICABLE"
            continue
        code = course["course_id"]
        if code in selected:
            result[code] = "ALREADY_COMPLETED"
            continue
        relevant = []
        for rid in unmet:
            rule = rules[rid]
            if not _basis(course, rule):
                continue
            if rule["rule_type"] == "ALL_AREAS" and course.get("general_area") in present_areas:
                continue
            if rule.get("area") == "GRADUATION_TOTAL" and course["classification"].startswith("GENERAL_") and general_count >= general_cap:
                continue
            relevant.append(rid)
        result[code] = "REQUIRED" if code in required and relevant else "ELIGIBLE_OPTION" if relevant else "NOT_APPLICABLE"
    return result


def _state(codes: list[str], fixture_id: str, template: dict) -> dict:
    state = deepcopy(template)
    state["student_state_id"] = f"TEST-REMAINING-{fixture_id}"
    state["student_id"] = f"TEST-{fixture_id}"
    state["official_outcomes"]["english_course_exemption"] = {
        "value": False, "verification_status": "VERIFIED",
        "evidence_id": f"TEST-FIXTURE:{fixture_id}:ENGLISH_EXEMPTION_REVIEW"}
    if fixture_id.startswith(("year1_", "year2_", "year3_", "year4_early")):
        for key in ("thesis_passed", "thesis_final_semester_enrollment", "graduation_certification_passed"):
            state["official_outcomes"][key] = {
                "value": False, "verification_status": "VERIFIED",
                "evidence_id": f"TEST-FIXTURE:{fixture_id}:{key}:NOT_YET_COMPLETED"}
    state["course_attempts"] = [
        {"attempt_id": f"TEST-{fixture_id}-{code}", "course_id": code,
         "completion_status": "COMPLETED", "verification_status": "VERIFIED",
         "evidence_id": f"TEST-FIXTURE:{fixture_id}:{code}", "earned_credits": None}
        for code in sorted(codes)]
    return state


def _oracle_with_student_evidence(codes: list[str], catalog: dict, state: dict) -> dict:
    expected = oracle(codes, catalog)
    for rule in catalog["requirements"]:
        if rule["rule_type"] != "REQUIRED_EVIDENCE":
            continue
        evidence = state["official_outcomes"].get(rule["evidence_key"])
        expected["expected_requirement_results"][rule["rule_id"]] = (
            "SATISFIED" if evidence and evidence["verification_status"] == "VERIFIED" and evidence["value"] is True
            else "UNSATISFIED" if evidence and evidence["verification_status"] == "VERIFIED" and evidence["value"] is False
            else "NEEDS_INFORMATION")
    statuses = expected["expected_requirement_results"].values()
    expected["expected_final_decision"] = (
        "NOT_ELIGIBLE_PDF" if "UNSATISFIED" in statuses else
        "UNKNOWN" if "NEEDS_INFORMATION" in statuses else "ELIGIBLE_PDF")
    return expected


def make_fixtures() -> list[dict]:
    catalog = catalog_v1()
    by_code = {course["course_id"]: course for course in catalog["courses"]}
    complete = select_complete_courses(catalog)
    majors = sorted((code for code in complete if by_code[code]["classification"].startswith("MAJOR_")),
                    key=lambda code: (by_code[code].get("grade_term") or "9-9", code))
    generals = sorted((code for code in complete if by_code[code]["classification"].startswith("GENERAL_")),
                      key=lambda code: ({"GENERAL_BASIC": 0, "GENERAL_BALANCED": 1,
                                         "GENERAL_EXPANDED": 2}[by_code[code]["classification"]], code))
    # Interleave tested general and major completions. Grade/term fields are never eligibility rules.
    ordered = []
    while majors or generals:
        ordered.extend(majors[:2])
        del majors[:2]
        if generals:
            ordered.append(generals.pop(0))
    required = next(r for r in catalog["requirements"] if r["rule_type"] == "REQUIRED_COURSES")
    zero_required = next(code for code in required["course_ids"] if by_code[code]["catalog_credits"] == 0)
    general_drop = next(code for code in reversed(complete)
                        if by_code[code]["classification"] == "GENERAL_EXPANDED"
                        and all(code not in r.get("course_ids", []) for r in catalog["requirements"]))
    profiles = [(f"year{year}_{phase}", ordered[:count], f"{year}학년 {phase}")
                for year, phase, count in ((1, "early", 3), (1, "late", 8), (2, "early", 13),
                                           (2, "late", 19), (3, "early", 25), (3, "late", 31),
                                           (4, "early", 37), (4, "late", len(complete)))]
    profiles.extend([("required_missing", [c for c in complete if c != zero_required], "전필 누락 반례"),
                     ("credit_or_general_short", [c for c in complete if c != general_drop], "교양 부족 반례")])
    template = json.loads((ROOT / "tests/fixtures/core_eligible_synthetic.json").read_text(encoding="utf-8"))["student_state"]
    fixtures = []
    for fixture_id, codes, grade_label in profiles:
        state = _state(codes, fixture_id, template)
        expected = _oracle_with_student_evidence(codes, catalog, state)
        selected = set(codes)
        status_map = _expected_candidates(selected, catalog, expected)
        candidate = next((code for code in required["course_ids"] if status_map[code] == "REQUIRED"), None)
        candidate = candidate or next((code for code in sorted(status_map) if status_map[code] == "ELIGIBLE_OPTION"), None)
        candidate = candidate or next((code for code in sorted(status_map) if code not in selected
                                       and by_code[code]["classification"] == "MAJOR_ELECTIVE"
                                       and by_code[code]["catalog_credits"] > 0), None)
        if candidate is None:
            raise ValueError("No verified unused course available for simulation fixture")
        fixture = {"fixture_id": fixture_id, "notice": "SYNTHETIC TEST DATA ONLY / 실제 학생 자료 아님",
                   "grade_label_metadata_only": grade_label,
                   "ruleset_id": catalog["curriculum_ruleset"]["ruleset_id"],
                   "ruleset_version": catalog["curriculum_ruleset"]["ruleset_version"],
                   "student_state": state,
                   "expected": {**expected, "course_count": len(codes),
                                "candidate_status_by_course": status_map,
                                "simulation_course_id": candidate,
                                "simulation_expected": _oracle_with_student_evidence(sorted(selected | {candidate}), catalog, state)}}
        fixtures.append(fixture)
    return fixtures


def main() -> None:
    DEST.mkdir(parents=True, exist_ok=True)
    for fixture in make_fixtures():
        (DEST / f"{fixture['fixture_id']}.json").write_text(json.dumps(fixture, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Generated {len(make_fixtures())} synthetic remaining-requirement fixtures in {DEST}")


if __name__ == "__main__":
    main()
