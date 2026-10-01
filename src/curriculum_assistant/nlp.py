"""Conservative Korean question parsing into allowlisted StructuredQuery.

Aliases only affect entity resolution; they never create curriculum facts.
"""
from __future__ import annotations

import difflib
import re

ALIASES = {"고자구": "CDA0143", "데베": "CDA0065", "컴구": "CDA0016", "운체": "CDA0017"}
STOPWORDS = {"전공필수", "전공선택", "전공학점", "졸업학점", "교양학점", "필수과목", "남은과목", "그과목", "학점", "과목", "졸업", "교양", "전공"}


def _policy_topics(question: str) -> list[str]:
    """Map rule-fact language to broad source-derived topics, never to an answer."""
    clean = _norm(question)
    if any(term in clean for term in ("지금", "현재", "남았", "남은", "남음", "부족", "이수하면", "들으면",
                                     "추가", "안들은", "안들었", "빠진", "빠졌", "인정받", "졸업가능",
                                     "졸업할수", "졸업돼", "졸업됨", "졸업여부", "이수기록", "성적표", "넣어도", "산입해")):
        # Policy questions can discuss a *category's* residual credits or a
        # hypothetical cap without supplying a student's completed records.
        if not any(term in clean for term in ("잔여학점", "초과", "상한", "적용기준", "이수기준",
                                              "이전학번", "과거학번", "기존학번", "심층상담", "현재규정", "공식문서")) and not (
            "단일전공" in clean and "부전공" in clean
        ):
            return []
    if "얼마나" in clean and "인정" in clean:
        return []
    if re.search(r"(^|\s)(나|나는|내|제가|저는|우리)(\s|$)", question):
        return []
    topics: set[str] = set()
    if ("요건" in clean and ("졸업" in clean or "판정" in clean)
            and any(term in clean for term in ("종류", "목록", "어떤", "전체", "보여", "뭐"))):
        topics.add("ALL_REQUIREMENTS")
    if ("교육과정" in clean and any(term in clean for term in ("적용", "학번", "입학", "개편", "변경"))) or (
        any(term in clean for term in ("이전학번", "과거학번", "기존학번", "입학연도", "복학생", "재입학", "전과"))
        and any(term in clean for term in ("기준", "적용", "과목", "학점", "교육과정"))
    ):
        topics.add("APPLICABILITY")
    if "졸업학점" in clean or ("졸업" in clean and "총학점" in clean):
        topics.add("GRADUATION_CREDITS")
    if "교양" in clean and any(term in clean for term in ("학점", "상한", "최소", "이수기준")):
        topics.add("GENERAL_CREDITS")
    if "균형교양" in clean and any(term in clean for term in ("영역", "과목", "각", "제외", "의무")):
        topics.add("GENERAL_AREAS")
    major_clean = clean.replace("단일전공", "").replace("복수전공", "").replace("부전공", "")
    if "전공" in major_clean and "학점" in clean:
        topics.add("MAJOR_CREDITS")
    if "전필" in clean and "학점" in clean and any(term in clean for term in ("필요", "기준", "최소")):
        topics.add("MAJOR_CREDITS")
    if "전공필수" in clean and any(term in clean for term in ("과목", "모두", "뭐", "지정", "목록", "전체")):
        topics.add("REQUIRED_COURSES")
    if "졸업논문" in clean:
        topics.update(("REQUIRED_COURSES", "GRADUATION_CONDITIONS"))
    elif "심층상담" in clean:
        topics.add("REQUIRED_COURSES")
    if "졸업인증" in clean:
        topics.add("GRADUATION_CONDITIONS")
    if "권장" in clean:
        topics.add("RECOMMENDATIONS")
    if any(term in clean for term in ("동일과목", "대체", "재수강")) or ("중복" in clean and "잔여학점" not in clean):
        topics.add("EQUIVALENCE")
    if "경과조치" in clean:
        topics.add("TRANSITION")
    if any(term in clean for term in ("복수전공", "부전공")):
        topics.add("MULTI_PROGRAM")
    if "자유선택" in clean or ("잔여학점" in clean and "교양잔여학점" not in clean):
        topics.add("FREE_CHOICE")
    if "졸업잔여학점" in clean:
        topics.update(("GRADUATION_CREDITS", "GENERAL_CREDITS", "MAJOR_CREDITS"))
    if "심층상담" in clean and any(term in clean for term in ("횟수", "몇번", "한번", "학기", "이수")):
        topics.add("REQUIRED_COURSES")
    if any(term in clean for term in ("편입생", "재직자", "성인학습자", "야간학과", "계약학과")) and "교양" in clean:
        topics.update(("GENERAL_CREDITS", "GENERAL_AREAS"))
    return sorted(topics)


def _norm(text: str) -> str:
    return re.sub(r"[^가-힣a-zA-Z0-9ⅠⅡ]", "", text).lower()


def partial_policy_query(question: str) -> dict | None:
    """Return only source-backed policy components of a mixed personal query."""
    clean = _norm(question)
    if not any(term in clean for term in ("기준", "최소", "필요", "요건")):
        return None
    topics = []
    if "교양" in clean and any(term in clean for term in ("학점", "요건")):
        topics.append("GENERAL_CREDITS")
    if "전공" in clean and any(term in clean for term in ("학점", "요건")):
        topics.append("MAJOR_CREDITS")
    if "졸업" in clean and "학점" in clean:
        topics.append("GRADUATION_CREDITS")
    if not topics:
        return None
    year = re.search(r"(20\d{2})(?:학번|학년도입학생|년입학생)", clean)
    return {"intent": "POLICY_LOOKUP", "topics": sorted(set(topics)),
            "partial_student_information": True,
            **({"entry_year": int(year.group(1))} if year else {})}


def _entities(question: str, catalog: dict) -> tuple[list[str], list[str]]:
    normalized = _norm(question)
    courses = {c["course_id"]: c for c in catalog["courses"] if c["verification_status"] == "VERIFIED"}
    hits: list[tuple[int, str]] = []
    for code, course in courses.items():
        name = _norm(course["name"])
        if code.lower() in normalized:
            hits.append((len(code) + 20, code))
        if len(name) >= 3 and name in normalized:
            hits.append((len(name), code))
    for alias, code in ALIASES.items():
        if alias in normalized and code in courses:
            hits.append((len(alias) + 10, code))
    if hits:
        # A longer exact mention wins over a nested shorter course name.
        highest = max(score for score, _ in hits)
        chosen = sorted({code for score, code in hits if score == highest})
        return chosen, []
    tokens = [t for t in re.findall(r"[가-힣A-Za-z0-9ⅠⅡ]+", question) if len(t) >= 3 and _norm(t) not in STOPWORDS]
    fuzzy = []
    for token in tokens:
        clean = _norm(token)
        for code, course in courses.items():
            name = _norm(course["name"])
            if abs(len(clean) - len(name)) > 2:
                continue
            score = difflib.SequenceMatcher(None, clean, name).ratio()
            if score >= 0.78:
                fuzzy.append((score, code))
    if not fuzzy:
        return [], []
    best = max(score for score, _ in fuzzy)
    options = sorted({code for score, code in fuzzy if best - score <= 0.08})
    return (options, []) if len(options) == 1 else ([], options)


def _explicit_entities(question: str, catalog: dict) -> list[str]:
    """Resolve all non-overlapping exact mentions for multi-course simulation."""
    clean = _norm(question)
    courses = {c["course_id"]: c for c in catalog["courses"] if c["verification_status"] == "VERIFIED"}
    hits = []
    for code, course in courses.items():
        phrases = [code.lower(), _norm(course["name"])]
        phrases.extend(alias for alias, target in ALIASES.items() if target == code)
        for phrase in phrases:
            if len(phrase) >= 3:
                start = clean.find(phrase)
                if start >= 0:
                    hits.append((start, start + len(phrase), code))
    chosen, spans = [], []
    for start, end, code in sorted(hits, key=lambda hit: (-(hit[1] - hit[0]), hit[0], hit[2])):
        if not any(start < other_end and other_start < end for other_start, other_end in spans):
            chosen.append(code)
            spans.append((start, end))
    return sorted(set(chosen))


def interpret(question: str, catalog: dict, context: dict | None = None) -> dict:
    """Return a parsed intent or explicit ambiguity; never guesses a rule/value."""
    if not isinstance(question, str) or not question.strip():
        return {"interpretation_status": "NEEDS_INFORMATION", "ambiguities": ["EMPTY_QUESTION"], "structured_query": None, "context": context or {}}
    clean = _norm(question)
    placement = _placement_query(question, catalog, context)
    if placement is not None:
        return placement
    personal = any(term in clean for term in ("내가", "나는", "제가", "저는", "지금까지", "인정받", "이수한"))
    aggregate_form = ("과목" in clean and not personal and
                         (any(term in clean for term in ("몇개", "개수", "과목수")) or
                          ("학점" in clean and any(term in clean for term in ("합계", "총합")))))
    catalog_aggregate = aggregate_form and any(term in clean for term in ("전공", "전필", "전선"))
    if aggregate_form and not catalog_aggregate:
        return {"interpretation_status": "NEEDS_INFORMATION",
                "ambiguities": ["CATALOG_AGGREGATE_SCOPE_UNSUPPORTED"],
                "structured_query": None, "context": context or {}}
    if catalog_aggregate:
        year = re.search(r"20\d{2}", clean)
        if year and int(year.group()) != 2026:
            return {"interpretation_status": "NEEDS_INFORMATION", "ambiguities": ["CATALOG_VERSION_UNVERIFIED"],
                    "structured_query": None, "context": context or {}}
        classes = (["MAJOR_REQUIRED"] if "전공필수" in clean or "전필" in clean else
                   ["MAJOR_ELECTIVE"] if "전공선택" in clean or "전선" in clean else
                   ["MAJOR_ELECTIVE", "MAJOR_REQUIRED"])
        operation = "SUM_CREDITS" if "학점" in clean and any(term in clean for term in ("합계", "총합")) else "COUNT"
        return {"interpretation_status": "RESOLVED", "ambiguities": [],
                "structured_query": {"intent": "CATALOG_AGGREGATE", "aggregate": operation,
                                     "department_id": "DEPT-COMPUTER-ENGINEERING",
                                     "curriculum_id": "CURRICULUM-CE-2026", "classifications": classes},
                "context": context or {}}
    if (("순서" in clean and any(term in clean for term in ("바꿔", "바뀌", "달리", "뒤집")) or "역순" in clean)
            and any(term in clean for term in ("같", "똑같", "동일"))):
        consistency_operation = "INPUT_ORDER"
    elif ("시뮬레이션" in clean or "가정" in clean) and "두번" in clean and any(term in clean for term in ("그대로", "보존", "안바뀌", "같")):
        consistency_operation = "SIMULATION_IMMUTABILITY"
    elif any(term in clean for term in ("다시", "반복", "두번")) and any(term in clean for term in ("질문", "판정", "결과")) and any(term in clean for term in ("같", "똑같", "동일")):
        consistency_operation = "REPEAT"
    else:
        consistency_operation = None
    if consistency_operation:
        return {"interpretation_status": "RESOLVED", "ambiguities": [],
                "structured_query": {"intent": "CONSISTENCY_CHECK", "operation": consistency_operation},
                "context": context or {}}
    if (("관계" in clean and "규칙" in clean) or
            ("실행" in clean and any(term in clean for term in ("근거", "과정", "경로")))):
        return {"interpretation_status": "RESOLVED", "ambiguities": [],
                "structured_query": {"intent": "TRACE_EXPLAIN"}, "context": context or {}}
    code_mentions = sorted(set(re.findall(r"(?<![A-Z0-9])[A-Z]{3}\d{4}(?![A-Z0-9])", question.upper())))
    if (("과목" in clean and any(term in clean for term in ("없는", "있는", "존재", "실제"))
         and not any(term in clean for term in ("추가", "가정", "들으면")))
            or (code_mentions and any(term in clean for term in ("처리", "인정", "넣으면")))):
        resolved, _ = _entities(question, catalog)
        code = code_mentions[0] if len(code_mentions) == 1 else resolved[0] if len(resolved) == 1 else None
        if code:
            return {"interpretation_status": "RESOLVED", "ambiguities": [],
                    "structured_query": {"intent": "ENTITY_CHECK", "course_id": code}, "context": context or {}}
    planning = (any(term in clean for term in ("앞으로", "다음엔", "다음에", "더들어야", "뭘채우", "뭐채우", "얼마나채운", "왜이과목",
                                               "졸업까지", "채워야", "어느정도까지채", "아직뭐가남았"))
                or ("전필" in clean and any(term in clean for term in ("뭐남았", "뭐남아")))
                or ("전공" in clean and "남은거" in clean)
                or ("교양" in clean and "뭐더" in clean))
    if planning and "교양" in clean and "잔여학점" in clean and not personal and not any(
        term in clean for term in ("앞으로", "다음엔", "다음에", "내가", "나는", "제가", "저는")
    ):
        planning = False
    topics = [] if planning else _policy_topics(question)
    if topics:
        policy_program = "SINGLE" if "단일전공" in clean else "DOUBLE" if "복수전공" in clean or "제2전공" in clean else "MINOR" if "부전공" in clean else None
        compared_program = "MINOR" if policy_program == "SINGLE" and "부전공" in clean else None
        categories = (["TRANSFER"] if "편입생" in clean or "편입" in clean else []) + (
            ["EMPLOYED_ADULT"] if "재직자" in clean or "성인학습자" in clean else []) + (
            ["NIGHT"] if "야간학과" in clean else []) + (
            ["CONTRACT"] if "계약학과" in clean else [])
        entry_match = re.search(r"(20\d{2})(?:학번|학년도입학생|년입학생)", clean)
        historical_scope = not entry_match and any(term in clean for term in ("이전학번", "과거학번", "기존학번", "구학번"))
        earned = None
        if "교양" in clean and any(term in clean for term in ("초과", "상한", "인정", "이수")):
            linked = re.search(r"(\d{1,3})학점(?:을|를)?(?:이수|취득)", clean)
            if linked and "교양" in clean[max(0, linked.start() - 28):linked.start()]:
                earned = int(linked.group(1))
        calculations = []
        if "교양잔여학점" in clean:
            calculations.append("GENERAL_REMAINDER")
        if "졸업잔여학점" in clean:
            calculations.append("GRADUATION_REMAINDER")
        if "전공선택" in clean and (any(term in clean for term in ("심화전공", "합계", "합치", "합산")) or "+" in question):
            calculations.append("MAJOR_ELECTIVE_WITH_ADVANCED")
        focus = ("DOUBLE_COUNT" if "중복" in clean and "잔여학점" in clean else
                 "APPLICABILITY_CHOICE" if "교육과정" in clean and "선택" in clean and "적용" in clean else
                 "COUNSELING_SCHEDULE" if "심층상담" in clean and any(term in clean for term in ("횟수", "몇번", "한번", "학기")) else
                 "GENERAL_AREA_COURSE_CREDITS" if "균형교양" in clean and "과목" in clean and re.search(r"\d+학점", clean) else
                 "GENERAL_AREA_DOUBLE_COUNT" if "균형교양" in clean and "한과목" in clean and "두영역" in clean else None)
        return {"interpretation_status": "RESOLVED", "ambiguities": [],
                "structured_query": {"intent": "POLICY_LOOKUP", "topics": topics,
                                     **({"program_type": policy_program} if policy_program else {}),
                                     **({"compared_program_type": compared_program} if compared_program else {}),
                                     **({"student_category": categories[0]} if len(categories) == 1 else {}),
                                     **({"student_categories": categories} if len(categories) > 1 else {}),
                                     **({"historical_scope_requested": True} if historical_scope else {}),
                                     **({"requested_calculations": calculations} if calculations else {}),
                                     **({"policy_focus": focus} if focus else {}),
                                     **({"hypothetical_general_earned": earned} if earned is not None else {}),
                                     **({"entry_year": int(entry_match.group(1))} if entry_match else {})}, "context": context or {}}
    codes, ambiguity = _entities(question, catalog)
    if ambiguity:
        return {"interpretation_status": "AMBIGUOUS", "ambiguities": ambiguity, "structured_query": None, "context": context or {}}
    if len(codes) > 1:
        if not any(term in clean for term in ("들으면", "이수하면", "이수한다면", "추가", "수강하면",
                                                "수강한다면", "수강했다고", "이수했다고", "들었다고",
                                                "가정", "시뮬레이션", "들었을", "치면")):
            return {"interpretation_status": "AMBIGUOUS", "ambiguities": codes, "structured_query": None, "context": context or {}}
    course_id = codes[0] if codes else None
    context_used = False
    if not course_id and not code_mentions and context and ("그과목" in clean or "이과목" in clean or "하나더" in clean or "그거" in clean):
        course_id = context.get("last_course_id")
        context_used = bool(course_id)
    if not planning and not course_id and "몇학점" in clean and "몇" in question and not any(
        term in clean for term in ("전공학점", "교양학점", "졸업학점", "총학점", "인정받았", "지금까지")
    ):
        prefix = _norm(question.split("몇", 1)[0])
        for generic in ("지금까지", "현재", "이번학기", "전공", "교양", "인정받은", "이수한", "총", "내", "나", "저", "우리"):
            prefix = prefix.replace(generic, "")
        if len(prefix) >= 3:
            return {"interpretation_status": "NEEDS_INFORMATION", "ambiguities": ["UNRESOLVED_COURSE_ENTITY"],
                    "structured_query": None, "context": context or {}}
    what_if = any(term in clean for term in ("들으면", "이수하면", "이수한다면", "추가", "하나더",
                                                "수강하면", "수강한다면", "수강했다고", "이수했다고",
                                                "들었다고", "가정", "시뮬레이션", "들었을", "치면"))
    graduation = any(term in clean for term in ("졸업가능", "졸업할수", "졸업되", "졸업될", "졸업돼",
                                              "졸업됨", "졸업여부", "졸업기준보다", "졸업요건충족"))
    lookup = course_id and any(term in clean for term in ("몇학점", "이수구분", "전필", "전선", "어느영역", "무슨영역", "분류"))
    if what_if:
        intent = "WHAT_IF"
    elif graduation:
        intent = "GRADUATION_STATUS"
    elif lookup:
        intent = "COURSE_LOOKUP"
    elif planning:
        intent = "REMAINING_PLAN"
    elif any(term in clean for term in ("필수", "남았", "남음", "부족", "요건", "안들은", "안들었", "빠진", "빠졌", "탈락조건")):
        intent = "REQUIREMENT_GAPS"
    elif any(term in clean for term in ("학점", "얼마나", "몇점", "점수")):
        intent = "CREDIT_SUMMARY"
    elif course_id:
        intent = "COURSE_LOOKUP"
    else:
        return {"interpretation_status": "NEEDS_INFORMATION", "ambiguities": ["QUESTION_INTENT"], "structured_query": None, "context": context or {}}
    if intent == "COURSE_LOOKUP" and not course_id:
        return {"interpretation_status": "NEEDS_INFORMATION", "ambiguities": ["COURSE_ENTITY"], "structured_query": None, "context": context or {}}
    structured = {"intent": intent}
    if intent == "CREDIT_SUMMARY":
        structured["area"] = ("MAJOR_TOTAL" if "전공" in clean and "교양" not in clean and "졸업" not in clean else
                              "GENERAL_TOTAL" if "교양" in clean and "전공" not in clean and "졸업" not in clean else
                              "GRADUATION_TOTAL")
    if intent == "REMAINING_PLAN":
        structured["focus"] = ("MAJOR_REQUIRED" if "전필" in clean or "전공필수" in clean else
                               "GENERAL" if "교양" in clean and "전공" not in clean else
                               "MAJOR" if "전공" in clean and "교양" not in clean else "ALL")
    if course_id:
        structured["course_id"] = course_id
    if intent == "WHAT_IF":
        explicit = _explicit_entities(question, catalog)
        unknown_mentions = [code for code in code_mentions if code not in
                            {c["course_id"] for c in catalog["courses"] if c["verification_status"] == "VERIFIED"}]
        if unknown_mentions:
            structured.pop("course_id", None)
            structured["added_course_ids"] = sorted(set(explicit + unknown_mentions))
            structured["mode"] = "SIMULATION"
        elif len(explicit) > 1:
            structured.pop("course_id", None)
            structured["added_course_ids"] = explicit
            structured["mode"] = "SIMULATION"
        elif not course_id:
            selector = ("MISSING_ZERO_CREDIT_REQUIRED_ONE" if "0학점" in clean and any(x in clean for x in ("필수", "전필")) else
                        "MISSING_REQUIRED_ONE" if any(x in clean for x in ("전공필수", "전필")) and any(x in clean for x in ("하나", "한개", "한과목", "1개")) else
                        "UNKNOWN_STUDENT_COURSE" if "없는과목" in clean else
                        "UNSPECIFIED_TWO_COURSES" if any(x in clean for x in ("두개", "두과목", "2개")) else
                        "CONTEXT_COURSE" if "이과목" in clean or "그과목" in clean else
                        "UNSPECIFIED_COURSE")
            structured.update({"mode": "SIMULATION", "target_selector": selector,
                               "comparison_requested": any(x in clean for x in ("실제", "현재", "지금", "구분", "비교", "같이")),
                               "requested_deltas": ["REQUIREMENT_STATUS", "CREDITS"] if any(x in clean for x in ("바뀌", "달라", "줄어", "없어지", "뭐가")) else []})
        if context_used:
            structured["conversation_reference"] = "last_course_id"
        structured["assumed_completion"] = "SUCCESS"
    next_context = {"last_course_id": course_id or (context or {}).get("last_course_id")}
    return {"interpretation_status": "RESOLVED", "ambiguities": [], "structured_query": structured, "context": next_context}


def _placement_query(question: str, catalog: dict, context: dict | None) -> dict | None:
    """Parse dimensions, not answers: the server filters literal verified table cells."""
    clean = _norm(question)
    simulation = any(word in clean for word in ("들으면", "추가하면", "이수하면", "가정", "시뮬레이션"))
    dimension = '학기' in clean or '몇학년' in clean or bool(re.search(r'(?<!\d)[1-9]\d*학년(?!도)', clean)) or any(word in clean for word in ('하계', '동계', '여름', '겨울', '계절수업'))
    cue = dimension and any(word in clean for word in ('편성', '개설', '과목', '전필', '전공', '교양', '후보', '몇학년'))
    if not cue or simulation or any(word in clean for word in ("몇번", "횟수", "회차")):
        return None
    def incomplete(reason):
        return {"interpretation_status": "NEEDS_INFORMATION", "ambiguities": [reason], "structured_query": None, "context": context or {}}
    year = re.search(r"(20\d{2})(?:년도|년|학년도)?교육과정", clean)
    departments = re.findall(r'([가-힣]+학과)(?:\s|의|에서|에|$)', question)
    if any(name != '컴퓨터공학과' for name in departments):
        return incomplete('CATALOG_DEPARTMENT_UNVERIFIED')
    if year and year[1] != "2026":
        return incomplete("CATALOG_VERSION_UNVERIFIED")
    grade = re.search(r"(?<!\d)([1-9]\d*)학년(?!도)", clean)
    if grade and not 1 <= int(grade[1]) <= 4:
        return incomplete('PLACEMENT_GRADE_UNSUPPORTED')
    terms = []
    if "1학기" in clean or re.search(r"1[·,와과]2학기", clean):
        terms.append("SEMESTER_1")
    if "2학기" in clean:
        terms.append("SEMESTER_2")
    if "하계" in clean or "여름" in clean or "계절학기" in clean:
        terms.append("SUMMER")
    if "동계" in clean or "겨울" in clean or "계절학기" in clean:
        terms.append("WINTER")
    filters = {"terms": terms, "term_match": "ALL" if "모두" in clean or "둘다" in clean or "양쪽" in clean else "ANY"}
    if grade:
        filters["grade"] = int(grade[1])
    codes, ambiguity = _entities(question, catalog)
    if ambiguity or len(codes) > 1:
        return {"interpretation_status": "AMBIGUOUS", "ambiguities": ambiguity or codes, "structured_query": None, "context": context or {}}
    code_mentions = re.findall(r"[A-Z]{3}\d{4}", question.upper())
    code = codes[0] if codes else code_mentions[0] if len(code_mentions) == 1 else None
    reference = "그과목" in clean or "이과목" in clean
    if reference and code is None:
        code = (context or {}).get("last_course_id")
        if not code:
            return incomplete("PRIOR_COURSE_REFERENCE_REQUIRED")
    personal = any(word in clean for word in ("남은", "미이수", "안들은", "앞으로", "더들어야"))
    required = "전필" in clean or "전공필수" in clean
    major = "전공" in clean or "전선" in clean or required
    general = "교양" in clean
    focus = "MAJOR_REQUIRED" if required else "MAJOR" if major and not general else "GENERAL" if general and not major else "ALL"
    classes = (["MAJOR_REQUIRED"] if required else ["MAJOR_ELECTIVE"] if "전선" in clean or "전공선택" in clean else
               ["MAJOR_REQUIRED", "MAJOR_ELECTIVE"] if major and not general else
               ["GENERAL_BASIC"] if '기초교양' in clean and not major else
               ["GENERAL_BALANCED"] if '균형교양' in clean and not major else
               ["GENERAL_EXPANDED"] if '확대교양' in clean and not major else
               ["GENERAL_BASIC", "GENERAL_BALANCED", "GENERAL_EXPANDED"] if general and not major else
               ["MAJOR_REQUIRED", "MAJOR_ELECTIVE", "GENERAL_BASIC", "GENERAL_BALANCED", "GENERAL_EXPANDED"])
    query = {"placement_filter": filters, "placement_requested": True}
    if personal:
        query.update(intent="REMAINING_PLAN", focus=focus, group_by_placement=True, classifications=classes)
        if code:
            query["course_id"] = code
    elif code:
        query.update(intent="COURSE_LOOKUP", course_id=code)
    else:
        query.update(intent="PLACEMENT_LOOKUP", classifications=classes,
                     curriculum_id="CURRICULUM-CE-2026", department_id="DEPT-COMPUTER-ENGINEERING")
    if "다음학기" in clean and not terms:
        query["next_term_basis"] = "UNSPECIFIED"
    return {"interpretation_status": "RESOLVED", "ambiguities": [], "structured_query": query,
            "context": {**(context or {}), **({"last_course_id": code} if code else {})}}
