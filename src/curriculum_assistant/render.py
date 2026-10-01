"""Server-owned Korean rendering of locked decision values."""
from __future__ import annotations

from .placement import placement_label, TERMS

AREA_LABELS = {"GRADUATION_TOTAL": "졸업 총학점", "GENERAL_TOTAL": "교양", "GENERAL_BASIC": "기초교양",
               "GENERAL_BALANCED": "균형교양", "GENERAL_EXPANDED": "확대교양", "MAJOR_REQUIRED": "전공필수", "MAJOR_ELECTIVE": "최소전공 전공선택",
               "MAJOR_ADVANCED": "심화전공", "MAJOR_TOTAL": "전공 합계", "FREE_CHOICE": "자유선택 잔여학점"}
BALANCED_LABELS = {"DIGITAL_COMMUNICATION": "디지털커뮤니케이션", "HUMANITIES_ARTS": "인문예술",
                   "SOCIETY_CULTURE": "사회와문화", "SCIENCE_TECHNOLOGY": "자연과학기술의이해"}


def _rule_name(payload: dict, result: dict) -> str:
    rule = next((r for r in payload["evidence"]["rules"] if r["rule_id"] == result["rule_id"]), None)
    if not rule:
        return result["rule_id"]
    kind = rule["rule_type"]
    if kind == "MIN_CREDITS":
        label = AREA_LABELS.get(rule["area"], rule["area"]) + " 최소학점"
        if result["missing_amount"] is not None and result["missing_amount"] > 0:
            label += f"({result['missing_amount']}학점 부족)"
        return label
    if kind == "REQUIRED_COURSES":
        return "전공필수 지정 과목"
    if kind == "ALL_AREAS":
        return "균형교양 영역별 이수"
    if kind == "CREDIT_CAP":
        return "교양 졸업 산입 상한"
    if kind == "REQUIRED_EVIDENCE":
        return {"thesis_passed": "졸업논문 합격 여부", "thesis_final_semester_enrollment": "최종학기 졸업논문 신청 여부",
                "graduation_certification_passed": "졸업인증 통과 여부"}.get(rule["evidence_key"], result["rule_id"])
    if kind in {"ANY_COURSE", "ANY_COURSE_OR_EXEMPTION"}:
        return {"R-GE-2026-FUTURE-DESIGN": "미래설계 교양", "R-GE-2026-AI-FOUNDATION": "AI 기초 교양",
                "R-GE-2026-WRITING": "글쓰기 교양", "R-GE-2026-ENGLISH": "영어 교양 또는 면제"}.get(result["rule_id"], result["rule_id"])
    return result["rule_id"]


def _needs_name(item: str) -> str:
    direct = {"COMPLETE_STUDENT_TRANSCRIPT": "전체 이수내역", "OFFICIAL_EQUIVALENCE_REVIEW": "공식 동일·대체 과목 검토",
              "VERIFIED_STUDENT_CATEGORY_AND_EXCEPTIONS": "학생 적용 대상과 예외", "VERIFIED_2026_CREDIT_AND_CATALOG_APPLICABILITY": "적용 교육과정",
              "COMPLETE_VERIFIED_SINGLE_MAJOR_RULE_COVERAGE": "이 학생의 적용조건·입력 확인 범위",
              "VERIFIED_APPLICABILITY_EVIDENCE": "적용 교육과정 확인 입력",
              "COMPLETE_VERIFIED_TRANSCRIPT_EVIDENCE": "전체 이수내역의 완전성 확인 입력",
              "ACADEMIC_EVENT_APPLICABILITY_REVIEW": "재입학·전과 등 학적변동 적용 검토",
              "SECOND_PROGRAM_RULE_COVERAGE": "제2전공 적용 규칙과 학생 이수정보"}
    if item in direct:
        return direct[item]
    if item.startswith('QUESTION_STUDENT_SCOPE_CONFLICT:'):
        return '질문에 명시된 적용연도와 현재 학생 정보의 차이: '+item.split(':',1)[1]
    if item.startswith('UNHANDLED_APPLICABILITY_CONDITION:'):
        label=item.split(':',1)[1]
        names={'STANDARD_DURATION_EXCEEDED':'수업연한 초과자의 이번 학기 등록 조건',
               'READMISSION':'재입학자의 적용 교육과정', 'DEPARTMENT_TRANSFER':'전과자의 적용 교육과정',
               'TRANSFER':'편입생 적용 조건','LEAVE_OF_ABSENCE':'휴학 상태에서의 적용 조건'}
        return '이 학생에게 명시된 적용조건의 계산 범위 확인: '+names.get(label,label)
    if item == 'VERIFIED_ENGLISH_EXEMPTION_OR_COURSE_COMPLETION':
        return '영어 이수 또는 공식 영어 면제 여부'
    if item == 'VERIFIED_DISABILITY_EXEMPTION_CONDITION':
        return '졸업인증 면제 대상 여부'
    if item.startswith("STUDENT_EVIDENCE:"):
        return "학생 이수 증빙 " + item.split(":", 1)[1]
    if item.startswith("RULE_NOT_LOADED:"):
        return "필수 판정 규칙 적재 " + item.split(":", 1)[1]
    if item.startswith("CATALOG_CLASSIFICATION:") or item.startswith("CATALOG_VERIFICATION:"):
        return "과목 분류·원문 확인 " + item.split(":", 1)[1]
    if item.startswith("UNRESOLVED_COMPLETION_RECORD:"):
        _, attempt_id, field = item.split(":", 2)
        return f"이수기록 {attempt_id}의 {field} 식별 정보"
    if item == "SIMULATION_TARGET_COURSE_IDS_REQUIRED":
        return "추가로 이수할 과목코드"
    if item == "PRIOR_COURSE_REFERENCE_REQUIRED":
        return "앞선 대화에서 지칭한 과목"
    if item == "VERIFIED_SIMULATION_COURSE_REQUIRED":
        return "가정할 과목의 검증된 교육과정 편성 정보"
    return item


def _missing_course_text(payload: dict) -> str:
    codes = payload["decision"].get("missing_courses")
    if not codes:
        return ""
    names = {entry["course_id"]: entry["name"] for entry in payload["evidence"]["facts"]
             if entry.get("course_id") and entry.get("verification_status") == "VERIFIED"}
    listed = [f"{names[code]}({code})" if code in names else code for code in codes]
    return " 남은 전공필수: " + ", ".join(listed) + "."


def build_remaining_presentation(payload: dict) -> dict | None:
    """Group an executed plan for display without changing its decision or candidate status."""
    decision = payload["decision"]
    summary = decision.get("remaining_requirements")
    if summary is None:
        return None
    results = {r["rule_id"]: r for r in decision["requirement_results"]}
    names = {fact["course_id"]: fact["name"] for fact in payload["evidence"]["facts"]
             if fact.get("course_id") and fact.get("verification_status") == "VERIFIED"}
    required = [{"course_id": code, "course_name": names.get(code)}
                for code in (summary["missing_required_courses"] or [])]
    groups = []
    for area, prefix in (("MAJOR", "MAJOR_"), ("GENERAL", "GENERAL_")):
        if not any(c["course_classification"].startswith(prefix) for c in decision["candidate_courses"]):
            continue
        options = [c for c in decision["candidate_courses"]
                   if c["candidate_status"] == "ELIGIBLE_OPTION"
                   and c["course_classification"].startswith(prefix)]
        rule_ids = sorted({rid for c in options for rid in c["satisfies_requirement_ids"]})
        rule_groups = []
        for rid in rule_ids:
            ids = sorted(c["course_id"] for c in options if rid in c["satisfies_requirement_ids"])
            result = results[rid]
            rule_groups.append({"rule_id": rid, "label": _rule_name(payload, result),
                                "missing_amount": result["missing_amount"],
                                "candidate_count": len(ids), "course_ids": ids})
        groups.append({"area": area, "candidate_count": len(options),
                       "requirement_groups": rule_groups})
    return {"satisfied_count": len(summary["satisfied_requirements"]),
            "unsatisfied_count": len(summary["unsatisfied_requirements"]),
            "needs_information_count": len(summary["needs_information"]),
            "required_courses": required,
            "required_courses_status": summary["progress"].get("MAJOR_REQUIRED_COURSES", {}).get("status"),
            "other_required": [{"rule_id": rid, "label": _rule_name(payload, results[rid]),
                                "status": results[rid]["status"]}
                               for rid in summary["other_required_requirements"]],
            "candidate_groups": groups,
            "missing_credits_by_category": summary["missing_credits_by_category"],
            "needs_information": [_rule_name(payload, results[rid]) for rid in summary["needs_information"]]
                                 + [_needs_name(item) for item in summary["student_information_needed"]]}


def _placement_answer(view: dict, courses: list[dict], unknown: list[dict], personal: bool = False) -> str:
    filters = view['selection']['filters']
    requested = '·'.join(TERMS[t] for t in filters.get('terms', [])) or '학기별'
    if filters.get('grade'):
        requested = f"{filters['grade']}학년 " + requested
    if filters.get('term_match') == 'ALL' and len(filters.get('terms', [])) > 1:
        requested += ' 모두'
    label = '남은 요건을 채울 졸업요건상 후보' if personal else '2026 교육과정 과목'
    parts = [f"{requested} 편성 조건에 해당하는 {label}: {len(courses)}개."]
    if len(courses) <= 12:
        parts.append('\n'.join(f"- {c.get('course_name', c.get('name'))}({c['course_id']}) · {placement_label(c['curriculum_placement'])}"
                               + (' · 반드시 이수' if c.get('candidate_status') == 'REQUIRED' else ' · 선택 후보' if personal else '') for c in courses))
    parts.append('일치 과목의 전체 편성학기: ' + ' / '.join(f"{g['label']} {g['course_count']}개" for g in view['groups']) + '. 여러 학기 편성 과목은 각 학기에 포함됩니다. 전체 과목·출처는 펼쳐보기.')
    parts.append(f"편성학기 또는 학년 확인 필요: {len(unknown)}개. 이 항목도 펼쳐보기에서 확인할 수 있습니다.")
    if view.get('next_term_basis') == 'UNSPECIFIED':
        parts.append('다음 학기의 기준이 없어 특정 학기를 선택하지 않았습니다. 원하시는 학기를 알려 주세요.')
    parts.append('PDF상의 편성정보입니다. 실제 개설·개인 수강 가능·선수조건은 미확인이고, 편성 학년은 수강 제한을 뜻하지 않습니다.')
    return '\n'.join(p for p in parts if p)


def _render_policy(payload: dict) -> str:
    result = payload["decision"].get("lookup_result")
    if not result:
        return "확인된 2026 컴퓨터공학과 정책 사실을 찾지 못했습니다. 적용 범위를 확인해 주세요."
    if result.get('year_comparison'):
        from copy import deepcopy
        answers=[]
        for row in result['year_comparison']:
            child=deepcopy(payload)
            child['decision']['lookup_result']=row['lookup_result']
            child['decision']['needs_information']=row['needs_information']
            answers.append(_render_policy(child))
        return '\n'.join(answers)
    if result.get('document_scope_available') is False:
        return f"요청한 {result['policy_year']}년도 공식 문서는 등록되어 있지 않습니다. 현재 등록된 2026년도 교육과정의 적용 원칙은 확인할 수 있지만, 이를 요청 문서의 수치로 확정하지 않습니다."
    if "ALL_REQUIREMENTS" in result["topics"]:
        listed = []
        for rule in result["rules"]:
            label = _rule_name(payload, {"rule_id": rule["rule_id"], "missing_amount": None})
            pages = sorted({payload["evidence"]["source_locators"][ref]["pdf_page_start"]
                            for ref in rule["source_refs"] if ref in payload["evidence"]["source_locators"]})
            scope = ",".join(rule.get("program_types", ["SINGLE", "MINOR", "DOUBLE"]))
            listed.append(f"{label} [{rule['rule_id']}; {rule['rule_type']}; {scope}; VERIFIED; PDF {','.join(map(str, pages))}쪽]")
        return f"2026 컴퓨터공학과 적용 범위에서 확인된 졸업 판정 요건 {len(listed)}건: " + "; ".join(listed) + "."
    parts: list[str] = []
    direct: list[str] = []
    for calculation in result.get("calculations", []):
        if calculation["operation"] == "SUM_MINIMUM_COMPONENTS":
            by_id = {rule["rule_id"]: rule for rule in result["rules"]}
            operands = [by_id[rid]["required_value"] for rid in calculation["source_rule_ids"]]
            direct.append(f"전공선택 최소 {operands[0]}학점과 심화전공 최소 {operands[1]}학점의 합은 {calculation['required_amount']}학점입니다")
        elif calculation["operation"] == "REMAINDER_AFTER_REQUIRED_AREAS":
            direct.append(f"교양 최소학점에서 기초·균형 최소학점을 뺀 잔여 구조는 {calculation['required_amount']}학점입니다. 특정 확대교양만으로 채워야 한다는 지정은 확인되지 않습니다")
        elif calculation["operation"] == "GRADUATION_REMAINDER_STRUCTURE":
            direct.insert(0, f"졸업 총학점에서 교양·전공 최소학점을 뺀 잔여 구조는 {calculation['required_amount']}학점입니다. 공식적으로 인정된 자유선택 학점 등으로 채울 수 있지만 모든 과목이 자동 인정되는 것은 아닙니다")
        elif calculation["operation"] == "APPLY_VERIFIED_CREDIT_CAP":
            statement = f"교양 {calculation['earned_amount']}학점 중 졸업학점으로 인정되는 교양은 {calculation['recognized_amount']}학점입니다"
            if calculation["excess_amount"]:
                statement += f". 상한 초과 {calculation['excess_amount']}학점은 졸업학점에서 제외됩니다"
            if calculation["remaining_amount"]:
                statement += f". 교양 최소 {calculation['required_amount']}학점까지는 {calculation['remaining_amount']}학점이 부족합니다"
            direct.insert(0, statement)
    focus = result.get("policy_focus")
    if focus == "APPLICABILITY_CHOICE" and any(fact["predicate"] == "DEFAULT_CREDIT_POLICY_BASIS" for fact in result["policy_facts"]):
        direct.insert(0, "교육과정을 학생이 임의로 선택 적용할 수 없습니다")
    if focus == "GENERAL_AREA_COURSE_CREDITS" and any(rule["rule_type"] == "ALL_AREAS" for rule in result["rules"]):
        direct.insert(0, "균형교양의 개별 과목이 반드시 3학점이어야 하는 조건은 없습니다. 영역별 1과목 이상과 균형교양 합계 12학점은 별도로 확인합니다")
    if focus == "GENERAL_AREA_DOUBLE_COUNT" and any(rule["rule_type"] == "ALL_AREAS" for rule in result["rules"]):
        direct.insert(0, "2026 편성표에서 한 과목은 한 균형교양 영역에 분류되므로 두 영역에 동시에 산입하지 않습니다")
    if focus == "COUNSELING_SCHEDULE":
        course = next((item for item in result["courses"] if item["course_id"] == "CDA0088"), None)
        if course:
            schedule = " 교육과정상 " + placement_label(course["curriculum_placement"]) + " 편성입니다."
            direct.insert(0, "심층상담은 0학점 전공필수입니다." + schedule
                          + " 편성학기와 의무 횟수는 다르며, 실제 개설·수강 가능 여부와 2026 적용자의 별도 의무 횟수는 확정할 수 없습니다")
    if "APPLICABILITY" in result["topics"] and result.get("entry_year") is not None:
        year = result["entry_year"]
        if year == 2026:
            parts.append("2026학년도 일반 신입생에게는 원칙적으로 2026 교육과정의 졸업학점·영역별 학점 기준이 적용됩니다")
        else:
            parts.append(f"{year}학년도 입학생의 졸업학점·영역별 학점 기준은 원칙적으로 해당 입학연도 교육과정에 따릅니다")
    for rule in result["rules"]:
        if result.get("rule_applicability", {}).get(rule["rule_id"], {}).get("status") in {"NOT_APPLICABLE", "NEEDS_INFORMATION"}:
            continue
        kind = rule["rule_type"]
        if kind == "MIN_CREDITS":
            parts.append(f"{AREA_LABELS.get(rule['area'], rule['area'])}: 최소 {rule['required_value']}학점")
        elif kind == "CREDIT_CAP":
            parts.append(f"{AREA_LABELS.get(rule['area'], rule['area'])}의 졸업학점 산입 상한은 {rule['required_value']}학점입니다")
        elif kind == "ALL_AREAS":
            names = ", ".join(BALANCED_LABELS.get(area, area) for area in rule["areas"])
            parts.append(f"균형교양은 {names}의 각 영역에서 1과목 이상 이수해야 합니다")
        elif kind == "REQUIRED_COURSES":
            found = {course["course_id"]: course for course in result["courses"]}
            names = [f"{found[code]['name']}({code}, {found[code]['catalog_credits']}학점)" if code in found else code
                     for code in rule["course_ids"]]
            parts.append("전공필수는 " + ", ".join(names) + "입니다")
        elif kind == "REQUIRED_EVIDENCE":
            labels = {"thesis_passed": "졸업논문 합격", "thesis_final_semester_enrollment": "최종학기 졸업논문 수강신청",
                      "graduation_certification_passed": "졸업인증 충족"}
            parts.append(labels.get(rule["evidence_key"], rule["evidence_key"]) + " 여부를 확인합니다. 현재 경로는 확인된 최종 결과를 입력받으며 세부 기준을 모두 직접 계산한 것은 아닙니다")
    for fact in result["policy_facts"]:
        predicate, value = fact["predicate"], fact["value"]
        if predicate == "DEFAULT_CREDIT_POLICY_BASIS":
            parts.append("졸업학점과 영역별 학점은 원칙적으로 입학 당시 교육과정을 적용합니다. 개편 후 교양 영역별 최소학점이 더 낮거나 교육과정위원회가 인정한 경우에는 개편 기준을 적용할 수 있습니다")
        elif predicate == "COURSE_TABLE_BASIS":
            parts.append("이수교과목은 개편된 교육과정을 적용하며, 재입학·전과에는 별도 적용 조건이 있습니다")
        elif predicate == "COUNTS_AS_RESIDUAL":
            parts.append("원문에 정한 자유선택과목의 이수학점은 졸업 잔여학점으로 인정됩니다")
        elif predicate == "GENERAL_AREA_APPLICABILITY_EXCEPTIONS":
            categories = result.get("student_categories") or ([result["student_category"]] if result.get("student_category") else [])
            for category in categories:
                if category == "TRANSFER":
                    direct.append("편입생에게는 교양 이수 의무가 없습니다")
                elif category in value["area_minimum_exempt"]:
                    direct.append(f"{ {'NIGHT': '야간학과', 'EMPLOYED_ADULT': '재직자·성인학습자 관련 학과', 'CONTRACT': '계약학과'}[category] }는 교양 영역별 최소학점 적용 대상에서 제외됩니다")
                    parts.append(f"해당 학과 유형의 교양 최소 총량은 {value['reduced_total_minimum']}학점입니다. 정확한 학생 소속과 적용연도 확인이 필요합니다")
            if not categories and "GENERAL_AREAS" in result["topics"]:
                parts.append("교양 영역별 최소학점 예외는 편입생, 야간학과, 재직자·성인학습자 관련 학과, 계약학과에 따라 다릅니다")
        elif predicate == "GENERAL_CAP_EXCESS_TREATMENT":
            if result.get("student_category") != "TRANSFER" and "TRANSFER" not in result.get("student_categories", []):
                direct.append("교양 상한 초과분은 총 취득학점과 성적에는 남지만 졸업소요학점 및 졸업 잔여학점에는 산입하지 않습니다")
        elif predicate == "SAME_COURSE_REPEAT":
            parts.append("공식 지정된 동일과목의 중복 이수는 재수강으로 보아 선이수 성적을 삭제합니다")
        elif predicate == "REPLACEMENT_COURSE":
            parts.append("대체과목은 공식 지정과 수강신청 당시의 학생 선택에 따라 처리합니다. 개별 지정 목록은 아직 확인되지 않았습니다")
        elif predicate == "RECOMMENDED_NOT_REQUIRED":
            listed = ", ".join(f"{course['name']}({course['course_id']})" for course in value["courses"])
            parts.append(f"학과 권장 교양은 {listed}이며 이 권장 자체가 필수 이수 지정은 아닙니다")
        elif predicate == "YEAR_SCOPED_TRANSITION_EXISTS":
            year = result.get('policy_year',result.get("entry_year"))
            if year == 2026:
                parts.append("2002–2024 교육과정 적용자를 위한 학과 경과조치는 2026학년도 신입생에게 자동 적용되지 않습니다")
                continue
            band = next((b for b in value["retroactive_credit_bands"] if year is not None and b["first_year"] <= year <= b["last_year"]), None)
            if band:
                parts.append(f"학과 경과조치 표에는 {year} 적용연도에 교양 {band['general_total']}·전필 {band['major_required']}·전선 {band['major_elective']}학점이 소급 적용된다고 별도로 적혀 있습니다")
                if 2021 <= year <= 2024:
                    parts.append('2021–2024 적용자는 전공선택 최소 35학점 인정 단서도 함께 확인해야 합니다')
                if 2002 <= year <= 2007:
                    parts.append("2012년 2월 이후 졸업대상자는 2008 교육과정을 적용하는 단서도 있습니다")
            else:
                parts.append("컴퓨터공학과의 과거 교육과정 적용자에게 연도별 경과조치가 있으며, 개별 학생의 적용연도 확인이 필요합니다")
        elif predicate == "ANNUAL_SINGLE_MAJOR_CREDIT_ROW":
            wanted = set(result["topics"])
            labels = (("GRADUATION_CREDITS", "graduation_total", "졸업 총학점"),
                      ("GENERAL_CREDITS", "general_total", "교양 합계"),
                      ("MAJOR_CREDITS", "major_required", "전공필수"),
                      ("MAJOR_CREDITS", "major_elective", "전공선택"),
                      ("MAJOR_CREDITS", "major_advanced", "심화전공"),
                      ("MAJOR_CREDITS", "major_total", "전공 합계"))
            details = [f"{label} {value[key]}학점" for topic, key, label in labels if topic in wanted and key in value]
            parts.append(f"{fact['entry_year']}학년도 단일전공 연도별 표: " + ", ".join(details)
                         + "; 재입학·전과·경과조치 등 개별 적용 조건은 별도 확인이 필요합니다")
        elif predicate == "DOUBLE_MAJOR_SCOPE":
            parts.append("복수전공은 주전공과 제2전공의 최소전공학점·전공필수를 각각 이수하고, 주전공 졸업논문을 통과해야 합니다. 제2전공 논문은 면제됩니다")
            parts.append("동일 과목의 전공 간 중복 인정 상한은 2025학년도 이후 선발자 9학점, 이전 선발자 21학점이며 졸업 총학점에는 이중 산입하지 않습니다")
        elif predicate == "MINOR_SCOPE":
            parts.append("부전공은 주전공의 최소전공·심화전공과 부전공 21학점 이상, 지정된 부전공 필수과목을 확인해야 합니다")
            parts.append("동일 과목의 중복 인정은 9학점까지이며 졸업 총학점에는 이중 산입하지 않습니다")
        elif predicate == 'ENGLISH_COURSE_EXEMPTION':
            criterion=result.get('exam_criterion_result')
            if criterion:
                direct.insert(0, f"{criterion['exam']} {criterion['score']}점은 대학영어 면제 시험점수 기준 {criterion['minimum']}점을 "
                              + ('충족합니다' if criterion['meets_score_criterion'] else '충족하지 않습니다'))
            parts.append('대학영어 면제 기준: '+', '.join(c['display'] for c in value['criteria']))
            parts.append('시험점수 기준 충족과 개인의 공식 면제 처리 완료는 다릅니다. 공식 면제가 확인되면 영어 이수 의무를 면제하지만 학점은 자동 부여하지 않으며, 다른 교양으로 교양 최소 34학점을 채워야 합니다. 영어 외 기초교양 조건은 유지됩니다. 졸업인증 영어 기준과는 별개입니다')
        elif predicate == 'CERTIFICATION_DISABILITY_EXEMPTION':
            parts.append('원문은 장애 학생의 졸업인증을 면제합니다. 개인 적용에는 해당 학생 조건 확인이 필요합니다')
    if result.get("compared_program_type") == "MINOR" and result["program_type"] == "SINGLE":
        direct.insert(0, "단일전공 학생에게 부전공 지정 필수과목은 추가 졸업요건으로 적용되지 않습니다")
    if "MULTI_PROGRAM" in result["topics"] and result["program_type"] == "MINOR":
        minor_courses = [course for course in result["courses"] if course.get("minor_required")]
        if minor_courses:
            parts.append("컴퓨터공학과 부전공 지정 필수과목: " + ", ".join(
                f"{course['name']}({course['course_id']})" for course in sorted(minor_courses, key=lambda c: c["course_id"])))
    counseling = next((course for course in result["courses"] if course["course_id"] == "CDA0088"), None)
    if "REQUIRED_COURSES" in result["topics"] and counseling and focus != "COUNSELING_SCHEDULE":
        schedule = " 교육과정상 " + placement_label(counseling["curriculum_placement"]) + " 편성입니다."
        parts.append("심층상담은 0학점 전공필수입니다." + schedule
                     + " 편성 학기와 의무 이수 횟수는 다른 개념이며, 실제 개설·수강 가능 여부와 2026 적용자의 별도 의무 횟수는 현재 확인한 편성표만으로 확정하지 않습니다")
    if "GENERAL_AREAS" in result["topics"] and any(
        rule["rule_type"] == "ALL_AREAS" and result.get("rule_applicability", {}).get(rule["rule_id"], {}).get("status") == "APPLICABLE"
        for rule in result["rules"]
    ):
        parts.append("균형교양은 과목별 공식 편성 영역 한 개로 구분하여 같은 과목을 두 영역에 동시에 산입하지 않습니다. 네 영역에서 각 한 과목 이상과 균형교양 총 12학점을 각각 확인하며, 개별 과목이 반드시 3학점이어야 한다는 조건은 없습니다")
    if focus == "DOUBLE_COUNT" and "FREE_CHOICE" in result["topics"] and "GENERAL_CREDITS" in result["topics"] and "MAJOR_CREDITS" in result["topics"]:
        direct.insert(0, "이미 교양·전공으로 산입한 동일 이수학점을 졸업 잔여학점에 다시 더하지 않습니다")
    pages = sorted({payload["evidence"]["source_locators"][ref]["pdf_page_start"]
                    for item in [*result["rules"], *result["policy_facts"]] for ref in item["source_refs"]
                    if ref in payload["evidence"]["source_locators"]}
                   | {course["source"]["pdf_page"] for course in result["courses"]})
    scope = {"SINGLE": "단일전공", "DOUBLE": "복수전공", "MINOR": "부전공"}.get(result["program_type"], result["program_type"])
    if any(item.startswith("APPLICABLE_CURRICULUM_RULES_FOR_ENTRY_YEAR:")
           for item in payload["decision"]["needs_information"]):
        year = result.get('policy_year',result.get("entry_year"))
        basis = result.get('year_target', {}).get('basis')
        target = (f"{year}학년도 입학생" if basis == 'ADMISSION_YEAR' else f"학점기준 연도 {year} 적용자") if year is not None else "해당 적용연도 학생"
        parts.append(f"{target}에게 적용되는 수치 기준은 확인된 표와 학생별 적용 조건을 함께 검토해야 하며 2026 수치로 확정하지 않습니다")
    if "STUDENT_STATE_FOR_PERSONAL_CALCULATION" in payload["decision"]["needs_information"]:
        parts.append("학생 이수내역이 없어 개인별 인정학점과 부족량은 아직 계산할 수 없습니다. 성적표 또는 확인된 StudentState가 필요합니다")
    year = result.get('policy_year',result.get("entry_year"))
    basis={'ADMISSION_YEAR':'입학연도','CREDIT_POLICY_YEAR':'적용 학점기준 연도',
           'CATALOG_YEAR':'과목표 연도','DOCUMENT_YEAR':'문서 발행연도'}.get(result.get('year_target',{}).get('basis'),'적용연도')
    heading = ("기존 학번 적용 원칙: " if result.get("historical_scope_requested") else
               f"컴퓨터공학과 {year}학년도 입학생 적용 원칙: " if year is not None and year != 2026 and basis=='입학연도' else
               f"컴퓨터공학과 {basis} {year} 기준: " if year is not None and year != 2026
               else f"2026 컴퓨터공학과 {scope} 기준: ")
    return heading + ". ".join([*direct, *parts]) + (f". 근거: 교육과정 PDF {', '.join(map(str, pages))}쪽." if pages else ".")


def _render_locked(payload: dict) -> str:
    decision = payload["decision"]
    intent = decision["intent"]
    if any(n.startswith('REQUESTED_CATALOG_SCOPE_UNAVAILABLE:') for n in decision['needs_information']):
        return '요청한 연도의 과목표를 확인할 수 없어 해당 연도의 과목 분류·편성 결과를 확정하지 않습니다. 현재 등록된 과목표는 2026년도이며 다른 연도 대신 적용하지 않았습니다.'
    if intent == "POLICY_LOOKUP":
        return _render_policy(payload)
    if intent == "CATALOG_AGGREGATE":
        result = decision["lookup_result"]
        pages = sorted({entry["source"]["pdf_page"] for entry in payload["evidence"]["facts"]
                        if entry.get("entry_id")})
        label = "편성 과목 수" if result["operation"] == "COUNT" else "편성 과목 학점 합계"
        unit = "개" if result["operation"] == "COUNT" else "학점"
        return (f"2026 컴퓨터공학과 전공 {label}는 {result['value']}{unit}입니다. "
                "이는 교육과정 편성표의 합계이며 학생의 이수학점이나 졸업 최소 전공학점이 아닙니다. "
                f"근거: 교육과정 PDF {', '.join(map(str, pages))}쪽.")
    if intent == "CONSISTENCY_CHECK":
        result = decision["lookup_result"]
        kind = {"INPUT_ORDER": "학생 이수기록 순서 변경", "REPEAT": "동일 입력 반복 실행",
                "SIMULATION_IMMUTABILITY": "가상 이수 반복 실행"}[result["operation"]]
        if result["consistent"] and decision["decision_status"] == "SATISFIED":
            probe = f" 검증 예시 과목: {result['probe_course_id']}." if result["probe_course_id"] else ""
            return (f"{kind} 검증에서 판정·수치·근거·실행 기록이 일치했습니다. "
                    f"실제 StudentState는 변경되지 않았습니다.{probe} "
                    f"비교한 결정 ID: {result['first_decision_id']}, {result['second_decision_id']}.")
        return f"{kind} 검증을 확정하려면 비교 대상 과목 또는 입력 정보를 더 확인해야 합니다."
    if intent == "ENTITY_CHECK":
        result = decision["lookup_result"]
        if result.get('catalog_conflict'):
            return f"{result['course_id']}는 공식 PDF에 존재하지만 이름·분류가 충돌합니다. {result['catalog_conflict']['reason']} 자동 연결·학점 인정은 보류했습니다."
        if result["verified_catalog_entry"]:
            return f"{result['course_id']}는 확인된 2026 교육과정 편성 과목입니다. 학생별 인정은 이수 증빙과 적용 조건을 별도로 검증합니다."
        return (f"{result['course_id']}는 확인된 2026 교육과정 편성표에서 찾지 못했습니다. "
                "해당 이수기록을 자동으로 학점에 산입하지 않았습니다. 공식 과목 식별·인정 자료가 필요합니다.")
    if intent == "TRACE_EXPLAIN":
        result = decision["lookup_result"]
        relations = result["relationship_ids"]
        rules = result["rule_ids"]
        return (f"이번 질문에서 실제 반환·사용한 관계 {len(relations)}건"
                + (f"({', '.join(relations[:5])})" if relations else "")
                + f", 실행한 규칙 검증 {len(rules)}건"
                + (f"({', '.join(rules[:5])})" if rules else "")
                + "을 실행 기록에서 확인했습니다. 전체 관계·계산 이벤트와 PDF 위치는 근거 펼쳐보기에 있습니다. "
                  "데이터베이스 내부의 물리적 방문 순서는 주장하지 않습니다.")
    if intent == "COURSE_LOOKUP":
        if decision.get("lookup_status") == "FOUND":
            entry = decision["lookup_result"]
            label = {"MAJOR_REQUIRED": "전공필수", "MAJOR_ELECTIVE": "전공선택",
                     "GENERAL_BASIC": "기초교양", "GENERAL_BALANCED": "균형교양",
                     "GENERAL_EXPANDED": "확대교양"}.get(entry["classification"], entry["classification"])
            scope = {"FOREIGN_ONLY": "유학생 전용 편성 과목이므로 학생별 인정은 적용 대상 확인이 필요합니다.",
                     "NON_ENGINEERING_ONLY": "컴퓨터공학과 대상 편성 과목이 아니므로 컴퓨터공학과 학생의 인정학점으로 자동 산입하지 않습니다."}.get(entry["eligible_scope"], "")
            return (f"{entry['name']}({entry['course_id']})의 교육과정상 편성: {placement_label(entry['curriculum_placement'])}. "
                    f"2026 교육과정 분류는 {label}, "
                    f"학점은 {entry['catalog_credits']}학점입니다. {scope + ' ' if scope else ''}"
                    f"근거: 교육과정 PDF {entry['source']['pdf_page']}쪽. 실제 특정 학기의 개설·수강 가능 여부는 미확인입니다.")
        if decision.get("lookup_status") == "NOT_FOUND":
            return "확인된 2026 교육과정 편성표에서 해당 과목을 찾지 못했습니다. 과목코드와 적용 교육과정을 확인해 주세요."
        return "과목 분류를 확정하려면 원문 또는 적용 교육과정 정보를 추가로 확인해야 합니다."
    if intent == "PLACEMENT_LOOKUP":
        result = decision["lookup_result"]
        return _placement_answer(result, result['courses'], result['needs_verification'])
    amount = decision.get("credited_amount")
    if amount is None:
        return "적용 교육과정이 확인되지 않아 학점과 요건을 계산할 수 없습니다."
    if amount["total"] is None:
        credit_text = f"현재 확인된 졸업 산입 학점의 하한은 {amount['confirmed_minimum']}학점입니다. 이수내역이나 규칙 정보가 부족해 정확한 합계는 확인이 필요합니다."
    else:
        credit_text = f"확인된 졸업 산입 학점은 {amount['total']}학점입니다."
    if intent == "REMAINING_PLAN":
        summary = decision["remaining_requirements"]
        candidates = decision["candidate_courses"]
        view = payload.get("remaining_presentation") or build_remaining_presentation(payload)
        if decision.get("placement_view"):
            pv = decision["placement_view"]
            selected = set(pv["selection"]["matched_course_ids"])
            unknown = set(pv["selection"]["needs_verification_course_ids"])
            return (credit_text + f" 전체 요건: 충족 {view['satisfied_count']} · 미충족 {view['unsatisfied_count']} · 확인 필요 {view['needs_information_count']}.\n"
                    + _placement_answer(pv, [c for c in candidates if c['course_id'] in selected],
                                        [c for c in candidates if c['course_id'] in unknown], personal=True)
                    + (" 이수기록 확인 전에는 미이수 필수과목을 확정할 수 없습니다." if view['required_courses_status'] == 'NEEDS_INFORMATION' else ''))
        progress = summary["progress"]
        def progress_line(key: str, label: str) -> str:
            item = progress.get(key)
            if not item:
                return ""
            qualifier = "이상 확인" if item["is_lower_bound"] else "인정"
            return f"{label} {item['current'] if item['current'] is not None else '미확인'}/{item['required']}({qualifier})"
        progress_text = ", ".join(part for part in (
            progress_line("GRADUATION_TOTAL", "총학점"), progress_line("MAJOR_TOTAL", "전공학점"),
            progress_line("MAJOR_REQUIRED_COURSES", "전공필수 과목"), progress_line("GENERAL_TOTAL", "교양학점")) if part)
        required_text = ", ".join(f"{c['course_name'] or c['course_id']}({c['course_id']})"
                                  if c["course_name"] else c["course_id"]
                                  for c in view["required_courses"]) or "없음"
        other_text = ", ".join(item["label"] + ("(확인 필요)" if item["status"] == "NEEDS_INFORMATION" else "")
                               for item in view["other_required"]) or "없음"
        if view["required_courses_status"] == "NEEDS_INFORMATION":
            required_text = "이수기록 확인 전에는 미이수 과목을 확정할 수 없음"
            required_count = "확인 필요"
        else:
            required_count = f"{len(view['required_courses'])}과목"
        shortages = view["missing_credits_by_category"]
        main_shortages = ", ".join(
            f"{label} {shortages.get(area) if shortages.get(area) is not None else '확인 필요'}"
            + ("학점" if shortages.get(area) is not None else "")
            for area, label in (("GRADUATION_TOTAL", "졸업 총"), ("MAJOR_TOTAL", "전공"),
                                ("GENERAL_TOTAL", "교양")) if area in shortages)
        other_shortages = sum(value is not None and value > 0 for area, value in shortages.items()
                              if area not in {"GRADUATION_TOTAL", "MAJOR_TOTAL", "GENERAL_TOTAL"})
        if other_shortages:
            main_shortages += f"; 세부 영역 {other_shortages}건은 펼쳐보기"
        if not main_shortages:
            main_shortages = "계산 가능한 부족 학점 없음"
        option_lines = []
        for group in view["candidate_groups"]:
            label = "전공" if group["area"] == "MAJOR" else "교양"
            rules = group["requirement_groups"]
            if not group["candidate_count"]:
                option_lines.append(f"{label}: 현재 조회 범위에 선택 후보 없음")
                continue
            descriptions = [f"{item['label']} {item['candidate_count']}개" for item in rules[:4]]
            if len(rules) > 4:
                descriptions.append(f"그 밖의 요건 {len(rules)-4}건")
            option_lines.append(f"{label}: 후보 {group['candidate_count']}개 · " + ", ".join(descriptions))
        requested = next((c for c in candidates if c["course_id"] == decision.get("requested_course_id")), None)
        reason_text = ""
        if requested:
            if requested["candidate_status"] == "REQUIRED":
                reason = "미이수 지정 필수과목"
            elif requested["candidate_status"] == "ELIGIBLE_OPTION":
                reason = "확인된 미충족 요건을 채울 수 있는 선택 후보"
            elif requested["candidate_status"] == "ALREADY_COMPLETED":
                reason = "이미 확정 이수한 과목"
            else:
                reason = "현재 확인된 미충족 요건과 연결되지 않는 과목"
            reason_text = (f" 질문한 {requested['course_name']}({requested['course_id']})은 {reason}입니다. "
                           f"연결 요건: {', '.join(requested['satisfies_requirement_ids']) or '없음'}. "
                           f"근거: 교육과정 PDF {requested['provenance']['source']['pdf_page']}쪽.")
        unknown = list(dict.fromkeys(view["needs_information"]))
        unknown_text = ", ".join(unknown[:3]) if unknown else "요건 판정에 필요한 추가 정보 없음"
        if len(unknown) > 3:
            unknown_text += f" 외 {len(unknown)-3}건"
        return "\n\n".join((
            f"현재 상태: {progress_text}. 요건 충족 {view['satisfied_count']}건, 미충족 {view['unsatisfied_count']}건, 확인 필요 {view['needs_information_count']}건.",
            f"반드시 이수: 미이수 전공필수 {required_count}: {required_text}. 그 밖의 필수 조건: {other_text}.",
            f"부족 학점: {main_shortages}.",
            "남은 요건별 선택 후보(졸업요건상 후보, 우선순위 아님): " + " / ".join(option_lines) + ". 한 과목이 여러 요건에 포함될 수 있습니다. 전체 목록과 연결 규칙은 펼쳐보기.",
            f"추가 확인: {unknown_text}. 다음 학기 개설·선수과목·시간표 충돌은 확인되지 않았습니다."
        )) + reason_text
    if intent == "WHAT_IF":
        scenario = payload.get("scenario_decision")
        if not scenario or not scenario.get("credited_amount"):
            unmet = [_rule_name(payload, r) for r in decision["requirement_results"] if r["status"] == "UNSATISFIED"]
            known = f" 현재 확인된 미충족 요건: {', '.join(unmet[:5])}." if unmet else ""
            candidates = decision.get("simulation_candidates", [])
            candidate_text = f" 확인 가능한 후보 과목코드: {', '.join(candidates)}." if candidates else ""
            needs = ", ".join(_needs_name(n) for n in decision["needs_information"][-3:])
            return credit_text + known + candidate_text + f" 가상 결과는 아직 계산하지 않았습니다. 추가 확인: {needs}. 실제 이수내역은 변경되지 않았습니다."
        projected = scenario["credited_amount"]
        before = {r["rule_id"]: r for r in decision["requirement_results"]}
        labels = {"SATISFIED": "충족", "UNSATISFIED": "미충족", "NEEDS_INFORMATION": "확인 필요",
                  "NOT_APPLICABLE": "해당 없음"}
        changes = [f"{_rule_name(payload, r)} {labels[before[r['rule_id']]['status']]}→{labels[r['status']]}"
                   for r in scenario["requirement_results"]
                   if r["rule_id"] in before and before[r["rule_id"]]["status"] != r["status"]]
        change_text = f" 가정 후 요건 변화: {', '.join(changes)}." if changes else ""
        delta = payload.get("scenario_delta") or {}
        major_change = (f" 전공 인정학점 변화는 {delta['major_credit_change']:+d}학점입니다."
                        if delta.get("major_credit_change") is not None else " 전공 인정학점 변화는 추가 확인이 필요합니다.")
        completed_required = delta.get("completed_required_course_ids")
        required_change = (f" 가정 이수로 미이수 지정 필수에서 제외되는 과목: {', '.join(completed_required)}."
                           if completed_required else "")
        preview_labels = {"ELIGIBLE_PDF": "해당 PDF 기준 졸업 가능", "NOT_ELIGIBLE_PDF": "졸업 요건 미충족",
                          "UNKNOWN": "졸업 가능 여부 확인 필요"}
        before_preview = delta.get("graduation_preview_before")
        after_preview = delta.get("graduation_preview_after")
        graduation_change = (f" 동일 RuleSet의 졸업판정 미리보기: {preview_labels[before_preview]}→{preview_labels[after_preview]}."
                             if before_preview in preview_labels and after_preview in preview_labels else "")
        if amount["total"] is not None and projected["total"] is not None:
            return credit_text + f" 제안한 과목을 성공적으로 이수한다는 가정에서는 {projected['total']}학점으로 계산됩니다." + major_change + required_change + change_text + graduation_change + " 실제 이수내역은 변경되지 않았습니다."
        return credit_text + f" 추가 이수 가정에서 확인된 하한은 {projected['confirmed_minimum']}학점입니다." + major_change + required_change + change_text + graduation_change + " 실제 이수내역은 변경되지 않았으며 정확한 증가는 확인이 필요합니다."
    if intent == "GRADUATION_STATUS":
        outcome = decision["graduation_outcome"]
        heading = {"ELIGIBLE_PDF": "해당 PDF 기준 졸업 가능", "NOT_ELIGIBLE_PDF": "해당 PDF 기준 졸업 요건 미충족",
                   "UNKNOWN": "졸업 가능 여부 확인 필요"}[outcome]
        major = amount["by_area"].get("MAJOR_TOTAL")
        major_text = (f" 전공 인정학점은 {major}학점입니다." if amount["status"] == "COMPLETE"
                      else f" 현재 확인된 전공 인정학점 하한은 {major}학점입니다.") if major is not None else ""
        if outcome == "NOT_ELIGIBLE_PDF":
            unmet = [_rule_name(payload, r) for r in decision["requirement_results"] if r["status"] == "UNSATISFIED"]
            needs = decision["needs_information"]
            pending = f" 추가 확인 항목: {', '.join(_needs_name(n) for n in needs[:5])}." if needs else ""
            return f"{heading}. {credit_text}" + major_text + f" 확인된 미충족 요건: {', '.join(unmet[:5])}." + _missing_course_text(payload) + pending
        if outcome == "UNKNOWN":
            return f"{heading}. {credit_text}" + major_text + f" 추가 확인 항목: {', '.join(_needs_name(n) for n in decision['needs_information'][:5])}."
        return f"{heading}. {credit_text}" + major_text + " 적용된 요건·학생 입력·확인된 최종 결과는 근거 펼쳐보기에서 확인할 수 있습니다."
    if intent == "REQUIREMENT_GAPS":
        unmet = [_rule_name(payload, r) for r in decision["requirement_results"] if r["status"] == "UNSATISFIED"]
        unknown = [_rule_name(payload, r) for r in decision["requirement_results"] if r["status"] == "NEEDS_INFORMATION"]
        satisfied = [_rule_name(payload, r) for r in decision["requirement_results"] if r["status"] == "SATISFIED"]
        return (credit_text + f" 충족 요건: {', '.join(satisfied) or '없음'}."
                + f" 확인된 미충족 요건: {', '.join(unmet[:5]) or '없음'}."
                + _missing_course_text(payload) + f" 정보 부족 요건: {', '.join(unknown[:5]) or '없음'}.")
    if intent == "CREDIT_SUMMARY" and decision.get("requested_area") in {"MAJOR_TOTAL", "GENERAL_TOTAL"}:
        area = decision["requested_area"]
        label = AREA_LABELS[area]
        observed = amount["by_area"][area]
        if amount["status"] == "COMPLETE":
            return f"확인된 {label} 인정학점은 {observed}학점입니다. " + credit_text
        pending = ", ".join(_needs_name(n) for n in decision["needs_information"][:4])
        return (f"현재 확인된 {label} 인정학점의 하한은 {observed}학점입니다. "
                f"추가 확인: {pending or '전체 이수내역'}. 확인되지 않은 이수기록은 산입하지 않았습니다.")
    pending = ", ".join(_needs_name(n) for n in decision["needs_information"][:4])
    return credit_text + (f" 추가 확인: {pending}. 확인되지 않은 이수기록은 산입하지 않았습니다." if pending else "")


def render_answer(payload: dict) -> str:
    """Only prevalidated wording choices can surround server-owned facts."""
    base = _render_locked(payload)
    details=payload['decision'].get('coverage_details')
    if details and details.get('question_scope_conflicts'):
        base=('질문의 연도와 현재 학생 상태가 다릅니다. 아래는 학생 상태의 학점기준 '
              f"{details['credit_policy_year']}·과목표 {details['catalog_year']}로 계산한 부분 결과이며, 질문의 다른 연도 기준 판정은 확정하지 않습니다. " +base)
    style = payload.get("answer_style", "DIRECT")
    if style == "DIRECT":
        return base
    if style == "CONVERSATIONAL":
        return "확인 결과, " + base
    raise ValueError("Unsupported answer style")
