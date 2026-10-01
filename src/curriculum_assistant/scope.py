"""Explicit year/condition bindings. They describe requests, never edit a student."""
from __future__ import annotations

import re

YEAR_BASES = {'ADMISSION_YEAR', 'CREDIT_POLICY_YEAR', 'CATALOG_YEAR', 'DOCUMENT_YEAR'}


def year_targets(question: str) -> list[dict]:
    result = []
    for m in re.finditer(r'((?:19|20)\d{2})(?:\s*[~～–—-]\s*((?:19|20)\d{2}))?', question):
        before = re.sub(r'\s+', '', question[max(0,m.start()-18):m.start()])
        after = re.sub(r'\s+', '', question[m.end():m.end()+22])
        if re.match(r'(?:학번|학년도?(?:입학|신입)|년입학|입학생|신입생)', after) or re.search(r'입학(?:연도|년도)(?:는|가|가령|가정)?$',before):
            basis = 'ADMISSION_YEAR'
        elif re.match(r'(?:년도?|학년도)?(?:발행|문서|PDF|pdf)', after) or re.search(r'문서(?:발행)?연도(?:는|가)?$',before):
            basis = 'DOCUMENT_YEAR'
        elif re.search(r'(?:과목표|편성표)연도(?:는|가)?$',before) or re.match(r'(?:년도?|학년도)?(?:과목표|편성표)', after):
            basis = 'CATALOG_YEAR'
        else:
            basis = 'CREDIT_POLICY_YEAR'
        first, last = int(m[1]), int(m[2] or m[1])
        if last < first or last-first > 30:
            # An invalid range remains explicit and cannot become a 2026 default.
            result.append({'year':first,'basis':basis,'invalid_range':True})
            continue
        for year in range(first,last+1):
            value = {'year':year,'basis':basis}
            if value not in result:
                result.append(value)
    return result


def policy_targets(query: dict, student: dict) -> list[dict]:
    targets = query.get('year_targets', [])
    selected = targets
    if selected:
        return selected
    if query.get('historical_scope_requested'):
        return [{'year':None,'basis':'CREDIT_POLICY_YEAR'}]
    if 'entry_year' in query:
        return [{'year':query['entry_year'],'basis':'ADMISSION_YEAR'}]
    credit_year=student.get('credit_policy_year')
    year = credit_year if credit_year is not None else student.get('admission_year')
    return [{'year':year,'basis':'CREDIT_POLICY_YEAR' if credit_year is not None else 'ADMISSION_YEAR'}]


def declared_conditions(question: str) -> list[str]:
    clean = re.sub(r'\s+', '', question)
    values=[]
    for key, terms in (('DISABILITY',('장애학생','장애가있','장애인')),
                       ('STANDARD_DURATION_EXCEEDED',('수업연한초과','학제초과','초과학기','초과학제')),
                       ('READMISSION',('재입학했','재입학한','재입학생')),
                       ('DEPARTMENT_TRANSFER',('전과했','전과한','전과생')),
                       ('TRANSFER',('편입생','편입했','편입한')),
                       ('LEAVE_OF_ABSENCE',('휴학생','휴학중','휴학한'))):
        if any(t in clean for t in terms):
            values.append(key)
    return values


def question_scope_conflicts(query: dict, student: dict) -> list[str]:
    fields={'ADMISSION_YEAR':'admission_year','CREDIT_POLICY_YEAR':'credit_policy_year','CATALOG_YEAR':'catalog_year'}
    conflicts=[]
    for target in query.get('year_targets',[]):
        field=fields.get(target['basis'])
        if target['basis']=='DOCUMENT_YEAR' and (target['year']!=2026 or target.get('invalid_range')):
            conflicts.append(f"QUESTION_STUDENT_SCOPE_CONFLICT:document_year:{target['year']}")
        if field and (target.get('invalid_range') or student.get(field)!=target['year']):
            conflicts.append(f"QUESTION_STUDENT_SCOPE_CONFLICT:{field}:{target['year']}")
    return sorted(set(conflicts))


def relevant_conditions(student: dict, query: dict) -> list[str]:
    """Only declared decision-relevant conditions; unrelated metadata is harmless."""
    values=list(query.get('declared_conditions',[]))
    if student.get('academic_events'):
        values.extend('ACADEMIC_EVENT:'+str(v) for v in student['academic_events'])
    for key, label in (('exceeded_standard_duration','STANDARD_DURATION_EXCEEDED'),
                       ('disability_status','DISABILITY')):
        raw=student.get(key)
        value=raw.get('value') if isinstance(raw,dict) else raw
        if raw is not None and value is not False:
            values.append(label)
    # Unimplemented admissions/exemptions must not disappear as extra JSON keys.
    known={'academic_events','admission_year','credit_policy_year','catalog_year','applicability_status',
           'applicability_evidence_id','student_category','student_category_evidence_id',
           'equivalence_review_status','equivalence_review_evidence_id','exceeded_standard_duration',
           'current_semester_registered_credits','disability_status'}
    for key,value in student.items():
        if key not in known and value not in (None,False,[],{}) and re.search(
            r'(readmission|department_transfer|exemption|equivalence|replacement|academic_event|leave_of_absence|academic_status)',key):
            values.append('UNSUPPORTED_FIELD:'+key)
    known_outcomes={'english_course_exemption','graduation_certification_passed','thesis_passed','thesis_final_semester_enrollment'}
    for key,raw in student.get('official_outcomes',{}).items():
        value=raw.get('value') if isinstance(raw,dict) else raw
        if key not in known_outcomes and value is not False and re.search(r'(exemption|exception|equivalence|replacement)',key):
            values.append('UNSUPPORTED_OUTCOME:'+key)
    return sorted(set(values))
