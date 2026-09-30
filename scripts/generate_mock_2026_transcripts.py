"""Generate clearly synthetic 2026 CE PDF upload fixtures from pinned RuleSet v1.

Only verified catalog course fields and verified RuleSet thresholds determine the
course selection. Synthetic student attestations are marked as test assumptions.
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]

from curriculum_assistant.authority import RuleSetStore  # noqa: E402

DEST = ROOT / "evaluation" / "fixtures" / "student_records"
NOTICE = "테스트용 모의 성적표 / 실제 학생 자료 아님"
PROFILE_IDS = ("mock_2026_complete", "mock_2026_partial", "mock_2026_boundary", "mock_2026_missing_info")
CLASS_LABELS = {"MAJOR_REQUIRED": "전공필수", "MAJOR_ELECTIVE": "전공선택",
                "GENERAL_BASIC": "기초교양", "GENERAL_BALANCED": "균형교양",
                "GENERAL_EXPANDED": "확대교양"}


def catalog_v1() -> dict:
    catalog = RuleSetStore(ROOT / "data/processed/ruleset_versions").load_version(1)
    ruleset = catalog["curriculum_ruleset"]
    if ruleset["ruleset_id"] != "CRS-CE-2026-CORE" or ruleset["ruleset_version"] != 1:
        raise ValueError("Pinned 2026 computer-engineering Core RuleSet v1 is required")
    if catalog["authoritative_document_set"]["included_documents"] != ["CURRICULUM-2026"]:
        raise ValueError("Unexpected authoritative document set for Core v1")
    included = set(ruleset["included_rule_ids"])
    rules = {rule["rule_id"]: rule for rule in catalog["requirements"]}
    if included != set(rules) or any(rules[rule_id]["verification_status"] != "VERIFIED"
                                     for rule_id in included):
        raise ValueError("Core fixture requires exactly the pinned VERIFIED RuleSet rules")
    return catalog


def _eligible(course: dict) -> bool:
    return course["verification_status"] == "VERIFIED" and course.get("eligible_scope", "GENERAL") == "GENERAL"


def _sum(selected: set[str], by_code: dict, prefix: str) -> int:
    return sum(by_code[code]["catalog_credits"] for code in selected
               if by_code[code]["classification"].startswith(prefix))


def select_complete_courses(catalog: dict) -> list[str]:
    """Select actual catalog rows using only requirements and deterministic ordering."""
    by_code = {course["course_id"]: course for course in catalog["courses"] if _eligible(course)}
    rules = {rule["rule_id"]: rule for rule in catalog["requirements"]}
    selected = set(rules["R-CE-2026-REQUIRED-COURSES"]["course_ids"])
    for name in ("FUTURE-DESIGN", "AI-FOUNDATION", "WRITING", "ENGLISH"):
        group = rules[f"R-GE-2026-{name}"]["course_ids"]
        selected.add(min(code for code in group if code in by_code))
    for area in rules["R-GE-2026-BALANCED-AREAS"]["areas"]:
        options = (course["course_id"] for course in catalog["courses"]
                   if _eligible(course) and course["classification"] == "GENERAL_BALANCED"
                   and course.get("general_area") == area)
        selected.add(min(options))

    def total(classification: str) -> int:
        return sum(by_code[code]["catalog_credits"] for code in selected
                   if by_code[code]["classification"] == classification)

    for classification, rule_name in (("GENERAL_BASIC", "BASIC-CREDITS"),
                                      ("GENERAL_BALANCED", "BALANCED-CREDITS")):
        minimum = rules[f"R-GE-2026-{rule_name}"]["required_value"]
        for course in sorted(by_code.values(), key=lambda row: row["course_id"]):
            if total(classification) >= minimum:
                break
            if course["classification"] == classification:
                selected.add(course["course_id"])
    general_min = rules["R-GE-2026-TOTAL-CREDITS"]["required_value"]
    general_cap = rules["R-GE-2026-CREDIT-CAP"]["required_value"]
    for course in sorted(by_code.values(), key=lambda row: (row["classification"] != "GENERAL_EXPANDED", row["course_id"])):
        if _sum(selected, by_code, "GENERAL_") >= general_min:
            break
        if course["classification"].startswith("GENERAL_") and course["course_id"] not in selected:
            if _sum(selected, by_code, "GENERAL_") + course["catalog_credits"] <= general_cap:
                selected.add(course["course_id"])
    if not general_min <= _sum(selected, by_code, "GENERAL_") <= general_cap:
        raise ValueError("Verified general-education rows cannot satisfy the Core range")
    total_min = rules["R-GRAD-2026-TOTAL-CREDITS"]["required_value"]
    major_min = rules["R-CE-2026-MAJOR-TOTAL-CREDITS"]["required_value"]
    elective_min = rules["R-CE-2026-MAJOR-ELECTIVE-CREDITS"]["required_value"]
    advanced_rule = rules["R-CE-2026-ADVANCED-CREDITS"]
    for course in sorted(by_code.values(), key=lambda row: row["course_id"]):
        major = _sum(selected, by_code, "MAJOR_")
        elective = total("MAJOR_ELECTIVE")
        total_credits = major + _sum(selected, by_code, "GENERAL_")
        if (major >= major_min and elective >= elective_min and
                major - advanced_rule["base_major_credits"] >= advanced_rule["required_value"] and
                total_credits >= total_min):
            break
        if course["classification"] == "MAJOR_ELECTIVE":
            selected.add(course["course_id"])
    if _sum(selected, by_code, "MAJOR_") + _sum(selected, by_code, "GENERAL_") < total_min:
        raise ValueError("Verified catalog cannot construct the Core complete fixture")
    return sorted(selected)


def variants(complete: list[str], catalog: dict) -> dict[str, tuple[list[str], str | None]]:
    by_code = {course["course_id"]: course for course in catalog["courses"]}
    rules = {rule["rule_id"]: rule for rule in catalog["requirements"]}
    partial = set(complete)
    electives = sorted(code for code in partial if by_code[code]["classification"] == "MAJOR_ELECTIVE")
    minimum = rules["R-CE-2026-MAJOR-ELECTIVE-CREDITS"]["required_value"]
    for code in reversed(electives):
        if sum(by_code[item]["catalog_credits"] for item in partial
               if by_code[item]["classification"] == "MAJOR_ELECTIVE") < minimum:
            break
        partial.remove(code)
    positive_required = next(code for code in rules["R-CE-2026-REQUIRED-COURSES"]["course_ids"]
                             if by_code[code]["catalog_credits"] > 0)
    partial.remove(positive_required)
    zero_required = next(code for code in rules["R-CE-2026-REQUIRED-COURSES"]["course_ids"]
                         if by_code[code]["catalog_credits"] == 0)
    boundary = [code for code in complete if code != zero_required]
    return {"mock_2026_complete": (complete, None),
            "mock_2026_partial": (sorted(partial), None),
            "mock_2026_boundary": (boundary, zero_required),
            "mock_2026_missing_info": (complete, zero_required)}


def semester_for(course: dict, index: int) -> tuple[str, str]:
    term = course.get("grade_term") or ""
    if len(term) >= 3 and term[0] in "1234" and term[1] == "-" and term[2] in "12":
        return str(2025 + int(term[0])), term[2]
    return str(2026 + (index // 14) % 4), str(1 + (index % 2))


def make_rows(codes: list[str], catalog: dict, unknown_code: str | None) -> list[dict]:
    by_code = {course["course_id"]: course for course in catalog["courses"]}
    rows = []
    for index, code in enumerate(codes):
        course = by_code[code]
        if not _eligible(course):
            raise ValueError(f"Unverified or restricted catalog course in fixture: {code}")
        year, semester = semester_for(course, index)
        rows.append({"year": year, "term": semester,
                     "course_code": None if code == unknown_code else code,
                     "catalog_course_id": code,
                     "course_name": course["name"], "classification": CLASS_LABELS[course["classification"]],
                     "credits": course["catalog_credits"],
                     "grade": "S" if course["catalog_credits"] == 0 else "A+"})
    return rows


def oracle(codes: list[str], catalog: dict, unresolved_code: str | None = None) -> dict:
    """Calculate test expectations from verified Rule IR without asking the Rule Engine."""
    by_code = {course["course_id"]: course for course in catalog["courses"]}
    chosen = set(codes)
    confirmed = chosen - ({unresolved_code} if unresolved_code else set())
    sums = defaultdict(int)
    for code in confirmed:
        course = by_code[code]
        sums[course["classification"]] += course["catalog_credits"]
        if course["classification"].startswith("MAJOR_"):
            sums["MAJOR_TOTAL"] += course["catalog_credits"]
        else:
            sums["GENERAL_TOTAL"] += course["catalog_credits"]
    sums["MAJOR_ADVANCED"] = max(0, sums["MAJOR_TOTAL"] - next(
        rule["base_major_credits"] for rule in catalog["requirements"] if rule.get("area") == "MAJOR_ADVANCED"))
    cap = next(rule["required_value"] for rule in catalog["requirements"] if rule["rule_type"] == "CREDIT_CAP")
    sums["GRADUATION_TOTAL"] = sums["MAJOR_TOTAL"] + min(sums["GENERAL_TOTAL"], cap)
    incomplete = unresolved_code is not None
    results = {}
    missing_amount = {}
    missing_courses = {}
    for rule in catalog["requirements"]:
        rid = rule["rule_id"]
        if "SINGLE" not in rule.get("program_types", ["SINGLE"]):
            status = "NOT_APPLICABLE"
        elif rule["rule_type"] == "MIN_CREDITS":
            value = sums[rule["area"]]
            status = "SATISFIED" if value >= rule["required_value"] else "NEEDS_INFORMATION" if incomplete else "UNSATISFIED"
            if status == "UNSATISFIED":
                missing_amount[rid] = rule["required_value"] - value
        elif rule["rule_type"] == "REQUIRED_COURSES":
            missing = sorted(set(rule["course_ids"]) - confirmed)
            status = "SATISFIED" if not missing else "NEEDS_INFORMATION" if incomplete else "UNSATISFIED"
            if status == "UNSATISFIED":
                missing_courses[rid] = missing
        elif rule["rule_type"] in {"ANY_COURSE", "ANY_COURSE_OR_EXEMPTION"}:
            status = "SATISFIED" if set(rule["course_ids"]) & confirmed else "NEEDS_INFORMATION" if incomplete else "UNSATISFIED"
        elif rule["rule_type"] == "ALL_AREAS":
            present = {by_code[code].get("general_area") for code in confirmed}
            status = "SATISFIED" if set(rule["areas"]) <= present else "NEEDS_INFORMATION" if incomplete else "UNSATISFIED"
        elif rule["rule_type"] == "CREDIT_CAP":
            status = "NEEDS_INFORMATION" if incomplete else "SATISFIED"
        elif rule["rule_type"] == "REQUIRED_EVIDENCE":
            status = "SATISFIED"  # Explicit test-only attestations, never inferred from the PDF.
        else:
            raise ValueError(f"No independent oracle for {rule['rule_type']}")
        results[rid] = status
    applicable = [value for value in results.values() if value != "NOT_APPLICABLE"]
    final = "NOT_ELIGIBLE_PDF" if "UNSATISFIED" in applicable else "UNKNOWN" if "NEEDS_INFORMATION" in applicable else "ELIGIBLE_PDF"
    return {"expected_requirement_results": results, "expected_final_decision": final,
            "expected_total_credits": sums["GRADUATION_TOTAL"] if not incomplete else None,
            "expected_major_credits": sums["MAJOR_TOTAL"] if not incomplete else None,
            "expected_major_confirmed_minimum": sums["MAJOR_TOTAL"],
            "expected_confirmed_minimum": sums["GRADUATION_TOTAL"],
            "expected_missing_amount": missing_amount, "expected_missing_courses": missing_courses}


def write_pdf(path: Path, fixture_id: str, rows: list[dict], student_id: str) -> None:
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import SimpleDocTemplate, Spacer, Table, TableStyle, Paragraph

    pdfmetrics.registerFont(TTFont("MockMalgun", "C:/Windows/Fonts/malgun.ttf"))
    style = getSampleStyleSheet()["Normal"]
    style.fontName = "MockMalgun"
    style.fontSize = 8
    style.leading = 11
    doc = SimpleDocTemplate(str(path), pagesize=A4, topMargin=75, bottomMargin=42,
                            leftMargin=28, rightMargin=28)
    table_data = [["학년도", "학기", "이수구분", "과목코드", "과목명", "학점", "성적"]]
    table_data.extend([[row["year"], row["term"], row["classification"], row["course_code"] or "",
                        row["course_name"], str(row["credits"]), row["grade"]] for row in rows])
    table = Table(table_data, colWidths=[41, 23, 62, 60, 252, 31, 32], repeatRows=1,
                  rowHeights=[20] + [19] * len(rows), splitByRow=1)
    table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), "MockMalgun"),
        ("FONTSIZE", (0, 0), (-1, -1), 7.1),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8eef6")),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#aab4c2")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]))
    story = [Paragraph(f"모의 프로필: {fixture_id}", style),
             Paragraph(f"학번: {student_id} | 학과: 컴퓨터공학과 | 입학연도: 2026", style),
             Paragraph("테스트 전제: 국내 일반학생, 단일전공. 전체 성적표 범위와 논문·인증·동일과목 검토는 "
                       "별도 합성 확인 입력으로 제공한다.", style), Spacer(1, 8), table]

    def header(canvas, document):
        canvas.saveState()
        canvas.setFont("MockMalgun", 12)
        canvas.setFillColor(colors.HexColor("#ad2530"))
        canvas.drawString(28, A4[1] - 34, NOTICE)
        canvas.setFont("MockMalgun", 7)
        canvas.setFillColor(colors.HexColor("#636b75"))
        canvas.drawString(28, 25, "자동 생성 테스트 자료 - 공식 증명서 아님")
        canvas.drawRightString(A4[0] - 28, 25, f"{document.page}쪽")
        canvas.restoreState()

    doc.build(story, onFirstPage=header, onLaterPages=header)


def main() -> None:
    catalog = catalog_v1()
    complete = select_complete_courses(catalog)
    configurations = variants(complete, catalog)
    DEST.mkdir(parents=True, exist_ok=True)
    ruleset = catalog["curriculum_ruleset"]
    document_set = catalog["authoritative_document_set"]
    for index, fixture_id in enumerate(PROFILE_IDS, 1):
        codes, special = configurations[fixture_id]
        unknown_code = special if fixture_id == "mock_2026_missing_info" else None
        rows = make_rows(codes, catalog, unknown_code)
        expected = oracle(codes, catalog, unknown_code)
        expected.update({"fixture_id": fixture_id, "fixture_notice": NOTICE,
                         "curriculum_version": "CURRICULUM-CE-2026",
                         "authoritative_document_set_id": document_set["set_id"],
                         "ruleset_id": ruleset["ruleset_id"], "ruleset_version": ruleset["ruleset_version"],
                         "course_count": len(rows), "expected_printed_total_credits": sum(row["credits"] for row in rows),
                         "expected_resolved_records": len(rows) - (1 if unknown_code else 0),
                         "expected_needs_information": ["UNRESOLVED_COMPLETION_RECORD"] if unknown_code else [],
                         "expected_required_course_state": expected["expected_requirement_results"]["R-CE-2026-REQUIRED-COURSES"],
                         "source_rule_ids": sorted(ruleset["included_rule_ids"]),
                         "simulation_added_course_id": special if fixture_id == "mock_2026_boundary" else None,
                         "unresolved_source_course_id_for_generator_audit": unknown_code,
                         "synthetic_attestations": ["DOMESTIC_REGULAR", "SINGLE", "COMPLETE_TRANSCRIPT",
                                                     "APPLICABILITY_2026", "EQUIVALENCE_REVIEW",
                                                     "THESIS_PASSED", "THESIS_ENROLLED", "CERTIFICATION_PASSED"],
                         "generation_source": "Pinned CRS-CE-2026-CORE v1 verified catalog and Rule IR",
                         "course_ids_for_generator_audit": codes})
        write_pdf(DEST / f"{fixture_id}.pdf", fixture_id, rows, f"202600000{index}")
        (DEST / f"{fixture_id}.expected.json").write_text(
            json.dumps(expected, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"fixture_id": fixture_id, "course_count": len(rows),
                          "printed_credits": expected["expected_printed_total_credits"],
                          "expected_outcome": expected["expected_final_decision"]}, ensure_ascii=True))


if __name__ == "__main__":
    main()
