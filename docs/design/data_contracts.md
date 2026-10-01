# 데이터 계약: 입력부터 답변까지

## 공통 형식과 신뢰 경계

모든 객체는 `contract_version: "1"`, 안정 ID, 작성 주체, `snapshot_id` 또는 `execution_id`를 가진다. 연도는 정수, 학점은 음수가 아닌 수, 과목은 검증된 `course_id`로 표시한다. `null`은 **미확인**, `0`은 **확인된 0**이다. 출처 상태 `VERIFIED | UNVERIFIED | CONFLICTED | MISSING`과 요건 상태 `SATISFIED | UNSATISFIED | NEEDS_INFORMATION | NOT_APPLICABLE`는 다른 열거형이다. 질문 해석·OCR 결과는 확인 전까지 교육과정 사실이나 학생 이수 사실이 아니다.

| 계층·작성 주체 | 계약의 필수 필드 | 금지/검증 조건 |
| --- | --- | --- |
| `1 StudentState` · 입력 정규화 코드 | `student_state_id`, `as_of`, `student_id`, `admission_year`(미확인 시 `null`), `department_id`, `program_enrollments`(종류·선발연도·상태), `academic_events`(편입/전과/재입학), `course_attempts`(코드·학기·성적·이수상태·학생 증거 ID), `other_evidence`, `completion_coverage`(기간·완전성), 필드별 확인 상태 | 과목표가 학생 이수를 뜻하지 않음. 업로드에서 보이지 않는 과목을 자동 미이수로 만들지 않음. `recognized_credits`는 여기에 넣지 않음. |
| `2 StructuredQuery` · 자연어 해석 | 허용 `intent`(`COURSE_LOOKUP`, `POLICY_LOOKUP`, `CATALOG_AGGREGATE`, `ENTITY_CHECK`, `CONSISTENCY_CHECK`, `TRACE_EXPLAIN`, `CREDIT_SUMMARY`, `REQUIREMENT_GAPS`, `WHAT_IF`, `GRADUATION_STATUS`), 한국어 원문 참조, 과목/영역/연도 언급 후보, `student_state_id`, `scenario_proposal`(있는 경우), 해석 신뢰·모호성 | LLM 출력의 과목 ID·적용연도·학점·졸업값은 **후보**. 자유 Cypher, SQL, 코드, 요구학점, 규칙 ID를 받아 실행하지 않음. |
| `3 QueryPlan` · 서버의 엔티티 검증/계획 코드 | `query_plan_id`, 검증된 `resolved_entity_ids`, `operations[]`, 허용 필터, 예상 사실 종류, 요청자·스냅샷 ID | 연산은 `RESOLVE_APPLICABILITY`, `FETCH_CATALOG_ENTRY`, `FETCH_CATALOG_SET`, `AGGREGATE_COUNT`, `AGGREGATE_SUM_CREDITS`, `FETCH_REQUIREMENTS`, `FETCH_EQUIVALENCE`, `FETCH_STUDENT_ATTEMPTS`, `FETCH_SOURCE_LOCATORS`, `COMPARE_DECISIONS` 등의 allowlist만. LLM은 이 객체를 만들거나 수정하지 못함. |
| `4 EvidenceBundle` · 조회 어댑터 | `bundle_id`, 실제 반환된 `facts[]`, `relationships[]`, `rule_refs[]`, `source_locators[]`, `student_evidence_refs[]`, 각 항목 상태·적용 범위, `coverage_report` | 조회되지 않은 사실을 채우지 않음. PDF 262–263의 2026 과목 행을 2025 이하 필수 목록으로 보간하지 않음. |
| `5 RuleEngineInput` · 서버 | `student_state_id`, `query_plan_id`, `bundle_id`, `applicability_by_domain`, `rule_set_id`/해시, `RuleCoverageManifest`, `scenario_delta`(선택), 입력 해시 | 규칙 엔진은 확인 상태가 나쁜 필수 입력을 0 또는 거짓으로 바꾸지 않음. 실제/가상 입력을 합친 복사본만 시뮬레이션. |
| `6 DeterministicDecision` · 규칙 엔진 | `decision_id`, `intent`, `decision_status`(사실 조회만 할 때 `null`), `graduation_outcome`, `lookup_status`/`lookup_result`(사실 조회 시), `requirement_results[]`, `credited_amount`, `missing_amount`, `missing_courses`, `needs_information[]`, 사용 근거 ID, 규칙/데이터 버전 | `ELIGIBLE_PDF`는 적용 가능한 모든 졸업요건과 출처·입력 범위가 완전하고 전부 만족할 때만. 미확인 수치는 `null`; 필요한 정보 목록을 함께 반환. |
| `7 ExecutionTrace` · 실제 실행기 | `execution_id`, 순번 있는 `events[]`(계획·실제 조회·반환 ID·제외 이유·규칙 입력/요구값/결과), 스냅샷·해시 | DB 내부 물리 탐색 순서나 실행하지 않은 단계를 생성하지 않음. `provenance_model.md`의 이벤트형만 기록. |
| `8 AnswerPayload` · 서버 | `decision` 전체 또는 불변 참조, `lookup_result`, `requirement_results`, `credited_amount`, `missing_amount`, `missing_courses`, `needs_information`, `evidence`(PDF/학생 출처), `execution_trace`(표시 가능한 실제 단계), 표현 허용 범위 | LLM에는 읽기 전용 전달. 새 판정·숫자·과목·출처 생성 금지. 서버가 최종 문장의 상태·숫자·근거를 검증하고 불일치 시 결정적 템플릿으로 대체. |

## 업로드 자료 정규화 경계

`/api/extract`는 원본 학번·학과·입학연도 관찰값, 과목별 원본 코드·이름·취득학점·학기·이수표시·이수구분, 파일 위치·OCR 점수, 카탈로그 연결 후보를 반환한다. 과목 연결은 **정확한 코드**와 확인된 이름 일치에 기반하며 이름이 다르거나 코드가 없으면 `AMBIGUOUS`/`UNRESOLVED`이다. 같은 코드가 여러 행이면 `DUPLICATE_CANDIDATE`로 표시한다. 후보의 추출 상태는 항상 `UNVERIFIED`이고 판정 입력으로 자동 승격되지 않는다.

`/api/normalize-upload`는 원본 파일 해시를 재확인하고 사용자가 검토한 값으로 **새** `StudentState`를 만든다. 응답의 `records[]`에는 `raw_values`, `reviewed_values`, `corrections`, `official_course`, `resolution_status`, `review_status`, `usable_for_decision`, `needs_user_confirmation`을 남긴다. 원문과 충돌하는 정정값, 누락 학점·학기·이수표시, 중복/재이수 후보는 확정 이수로 인정하지 않는다. `VERIFIED_FROM_UPLOAD`는 사용자가 원문 행을 확인했고 해당 행의 코드·이름·학점·이수표시가 일치한다는 뜻이며 **공식 성적표 진위 또는 교육과정 적용연도 증명**이 아니다. `completion_coverage=PARTIAL`, `applicability_status=UNVERIFIED`로 시작하고 누락 페이지·학기는 모를 때 `null`로 둔다. 업로드 자료는 공식 RuleSet에 들어가지 않는다.

## 핵심 타입 제약

```text
SourceStatus = VERIFIED | UNVERIFIED | CONFLICTED | MISSING
DecisionStatus = SATISFIED | UNSATISFIED | NEEDS_INFORMATION | NOT_APPLICABLE
GraduationOutcome = ELIGIBLE_PDF | NOT_ELIGIBLE_PDF | UNKNOWN | NOT_REQUESTED
AmountResult = {
  total: number | null,              // 완전한 산입 결과일 때만 수치
  confirmed_minimum: number,         // 확인된 하한, 총 인정학점이라고 부르지 않음
  status: COMPLETE | PARTIAL | UNKNOWN,
  unit: CREDIT,
  breakdown: { area_id, credited: number | null, used_recognition_ids[] }[]
}
CreditGapResult = { total: number | null, status: COMPLETE | UNKNOWN,
  unit: CREDIT, by_area: { area_id, missing: number | null }[] }
RequirementResult = {
  requirement_id, rule_id, status: DecisionStatus,
  observed: number | boolean | null, required: number | boolean | null,
  missing_amount: number | null, missing_course_ids: string[] | null,
  used_fact_ids[], used_relationship_ids[], used_student_evidence_ids[],
  needs_information[], execution_event_ids[]
}
```

`missing_courses: []`는 **완전한 이수내역과 검증된 필수 목록을 대조해 부족 과목이 0개임**을 뜻한다. `null`은 목록을 계산할 수 없다는 뜻이다. `completion_coverage`가 불완전할 때는 `UNSATISFIED`나 정확한 부족학점을 만들지 않는다. `NOT_APPLICABLE`은 확인된 조건이 거짓일 때만 쓴다.

단순 `COURSE_LOOKUP`은 요건 판정이 아니므로 `decision_status=null`, `graduation_outcome=NOT_REQUESTED`로 두고, 검증된 편성표 값과 적용 버전·출처를 `lookup_result`에 둔다. `lookup_status`는 `FOUND | NEEDS_INFORMATION | NOT_FOUND` 중 하나다. 조회 후보가 모호하면 `lookup_result=null`, `needs_information`에 확인할 과목/버전을 적는다. `StudentState.department_id`처럼 필수 키이지만 값이 불명확한 필드는 `null`과 상태를 함께 보낸다.

`RuleCoverageManifest`는 해당 학생·이수유형에 필요한 규칙군 ID와 각각의 적재/출처/입력 상태를 가진다. 2026 컴퓨터공학과의 출발 목록은 총·교양영역·전필/전선·심화/다전공·필수과목·논문·인증·중복/예외다(PDF 23, 33, 261–264, 565–575, 577). 이 목록이 확정·완전하다는 증거가 없으면 전체 졸업 `ELIGIBLE_PDF`를 내지 않는다. 별도 영역(교직 등)은 **해당 학생에게 적용됨이 확인된 때** 추가한다.

구현 시 사용할 **최소 타입 형태**는 아래와 같다. 생략한 중첩 객체도 ID·확인 상태·증거 참조를 가져야 하며, 외부 경계에서는 정의되지 않은 필드와 연산을 거부한다.

```text
StudentState = { contract_version, student_state_id, as_of,
  student_id, admission_year: number|null, department_id: string|null,
  program_enrollments[], academic_events[], course_attempts[],
  other_evidence[], completion_coverage[], field_statuses{} }
StructuredQuery = { contract_version, intent, utterance_ref,
  student_state_id, entity_mentions[], scenario_proposal: ScenarioProposal|null,
  interpretation_status, ambiguities[] }
QueryPlan = { contract_version, query_plan_id, student_state_id,
  resolved_entity_ids[], operations: {op: AllowedOperation,
  filters: AllowedFilter[], requested_fact_types[]}[], snapshot_id }
EvidenceBundle = { contract_version, bundle_id, query_plan_id,
  facts: SourcedFact[], relationships: SourcedRelationship[],
  rule_refs[], source_locators[], student_evidence_refs[], coverage_report }
RuleCoverageManifest = { manifest_id, student_scope, source_refs[],
  families: {family_id, applicability_status, load_status,
  verification_status, required_rule_ids[], missing_items[]}[],
  completeness: COMPLETE|PARTIAL|UNKNOWN }
RuleEngineInput = { contract_version, student_state_id, query_plan_id,
  bundle_id, applicability_by_domain{}, rule_set_id, rule_set_hash,
  coverage_manifest: RuleCoverageManifest, scenario_delta: ScenarioDelta|null,
  canonical_input_hash }
DeterministicDecision = { contract_version, decision_id, intent,
  decision_status: DecisionStatus|null, graduation_outcome,
  lookup_status?, lookup_result?, requirement_results[],
  credited_amount: AmountResult|null, missing_amount: CreditGapResult|null,
  missing_courses: string[]|null, needs_information[], used_evidence_ids[],
  rule_set_hash, data_snapshot_id, canonical_result_hash }
ExecutionTrace = { contract_version, execution_id, decision_id,
  events: {event_id, sequence, event_type, actual_input_refs[],
  returned_ids[], excluded_ids_with_reasons[], rule_id?, operands?, result?}[] }
AnswerPayload = { contract_version, decision: DeterministicDecision,
  lookup_result?, requirement_results[], credited_amount, missing_amount,
  missing_courses, needs_information[], evidence: SourceLocatorRef[],
  execution_trace: ExecutionTrace, allowed_claims[] }
```

`decision_status`는 요건/학점 판정일 때만 네 상태 중 하나다. `GRADUATION_STATUS`는 확정된 미충족이 있으면 `NOT_ELIGIBLE_PDF`와 그 미충족을 반환하고 남은 미확인도 함께 보존한다. 확정 미충족이 없고 적용/요건/입력이 불완전하면 `UNKNOWN`; 모두 완전하고 만족하면 `ELIGIBLE_PDF`다. 다른 질문의 `graduation_outcome`은 `NOT_REQUESTED`다.

## 엔티티 연결과 시뮬레이션 계약

`StructuredQuery`의 문자열 언급과 `ScenarioProposal`은 서버가 허용된 학과·과목·영역 어휘 및 적용 버전에서 ID로 연결한다. 복수 후보/오타 모호성은 후보와 이유를 반환하며 임의의 첫 후보를 확정하지 않는다. 서버는 확인된 ID와 `intent`에 따라 `QueryPlan`을 만들고, 검증된 제안만 `ScenarioDelta`로 변환한다. 사용자 질문의 “지금까지”는 실제 `StudentState`를 가리키고 “들었다면”은 별도의 `ScenarioDelta`를 요구한다.

구현 확장 `POLICY_LOOKUP`은 학생 개인 학점이 아닌 **교육과정 규칙 자체**를 묻는 의도다. `StructuredQuery.topics[]`는 서버 허용 목록(`APPLICABILITY`, `GRADUATION_CREDITS`, `GENERAL_CREDITS`, `GENERAL_AREAS`, `MAJOR_CREDITS`, `REQUIRED_COURSES`, `GRADUATION_CONDITIONS`, `FREE_CHOICE`, `EQUIVALENCE`, `RECOMMENDATIONS`, `TRANSITION`)의 값만 허용한다. 선택적 `program_type`·`entry_year`는 적용 범위를 좁히며 규칙값을 덮어쓰지 못한다. 결과 `decision_status=null`, `graduation_outcome=NOT_REQUESTED`, `lookup_result={rules,policy_facts,courses,scope}`다. 조회된 기준을 학생의 충족 결과로 표현하지 않는다.

현재 구현에서 명시된 입학연도가 2026이 아니면 2026의 학점·필수과목 수치 규칙을 반환하지 않는다. 대신 PDF 13쪽의 적용 원칙을 조회하고 `needs_information`에 해당 연도 규칙 확인을 기록한다. 특정 예외로 2026 교육과정을 적용받는 과거 입학생의 정책 조회는 별도 적용 증거와 규칙 구조화가 필요하다.

2026 단일전공의 잔여학점 계산용 `StudentState.free_choice_records[]`는 `record_id`, `course_id`, `earned_credits`, `source_category`, `completion_status`, `verification_status`, `recognition_status`, `evidence_kind`, `evidence_id`를 가진다. PDF 13쪽에 열거된 자유선택 범주이고 공식 성적/인정 증거가 확인된 기록만 `FREE_CHOICE`로 인정한다. 교육과정 편성표의 전공·교양 과목과 겹치거나 중복 코드인 기록은 자동 합산하지 않고 확인 필요로 남긴다. 업로드 OCR 확인은 공식 인정 증거가 아니므로 이 계약의 `VERIFIED`로 자동 승격하지 않는다.

```json
{
  "scenario_id": "scenario:<execution-id>:1",
  "base_student_state_id": "student-state:<snapshot-id>",
  "kind": "WHAT_IF",
  "proposed_course_id": "CDA0163",
  "assumptions": { "completion": "SUCCESS", "term": null },
  "status": "HYPOTHETICAL"
}
```

이 예시는 **서버의 엔티티 검증을 통과한 뒤의** `ScenarioDelta`이며 PDF 262의 `CDA0163 웹프로그래밍`을 가리킬 뿐, 실제 학생이 이수했다거나 추가 인정 3학점이 확정됐다는 뜻이 아니다. 엔진은 기존 이수·동일/대체·중복·상한과 적용 과목표를 검증한 후 **시나리오 결과만** 별도로 낸다. 원본 `StudentState`와 실제 결정은 변경하지 않는다.

## 현재 구현의 질문·가정 확장

`CATALOG_AGGREGATE`는 `aggregate: COUNT | SUM_CREDITS`, 검증된 `department_id`, `curriculum_id`, `classifications[]`를 받아 `FETCH_CATALOG_SET`의 VERIFIED 편성 행에만 집계한다. 결과는 **편성 과목 수/학점 합계**이며 학생의 인정학점이나 졸업 최소학점이 아니다. 실제 반환 행과 원문 위치가 EvidenceBundle·ExecutionTrace에 남는다. `POLICY_LOOKUP(topics=[ALL_REQUIREMENTS])`는 학생 상태 없이 VERIFIED 적용 요건을 출처와 열거한다.

`WHAT_IF`는 `mode=SIMULATION`, `added_course_ids[]` 또는 `target_selector`, `comparison_requested`, `requested_deltas[]`, 선택적 `conversation_reference`를 사용한다. 대상이 유일하게 검증되면 원본 StudentState를 복사한 별도 가상 상태와 요건별 `scenario_delta`를 계산한다. 대상이 없거나 복수 후보라면 `simulation_status=NEEDS_TARGET`, `scenario_decision=null`, 미계산 delta는 `null`로 두며 실제 상태에서 확인한 값과 필요한 과목 정보를 함께 반환한다. 명시된 미확인 과목코드는 이전 대화의 과목으로 대체하지 않는다.

`scenario_delta`에는 `missing_required_before`, `missing_required_after`, `completed_required_course_ids`를 둔다. 요건 전체 상태가 여전히 `UNSATISFIED`여도 지정 필수 한 과목의 해결을 별도로 표시한다. 미확인 입력으로 어느 목록이든 계산할 수 없으면 해당 목록과 차이를 `null`로 둔다. 세 값은 실제/가상 `DeterministicDecision` 및 `SCENARIO_COMPARISON` 실행 이벤트와 대조한다.

`CONSISTENCY_CHECK`의 `REPEAT | INPUT_ORDER | SIMULATION_IMMUTABILITY`는 실제 결정 경로를 두 번 실행해 결정·근거·가상 입력의 원본 불변을 비교한다. `TRACE_EXPLAIN`은 실제 조회로 반환된 관계와 `RULE_EVALUATION`·계산 이벤트 ID만 제시한다. `ENTITY_CHECK`의 미존재 코드 또는 이수기록의 누락 `course_id`는 과목으로 발명하거나 0학점 미이수로 바꾸지 않는다. 식별 불가능한 이수기록은 `UNRESOLVED_COMPLETION_RECORD`와 누락 필드 이유를 보존하고 관련 판정을 `NEEDS_INFORMATION`으로 둔다. 확인된 다른 요건의 `UNSATISFIED`는 동시에 표시한다.

## 공식 문서집합과 RuleSet 고정 계약

`AuthoritativeDocument`는 `document_id`, `title`, `document_type`, `issuer`, `issued_at`, `effective_from/to`, `revision`, `source_file/hash`, `verification_status`, `authority_status`, `ingestion_status`, 공식성 근거와 누락 메타데이터 목록을 가진다. 현행 `CURRICULUM-2026`의 미확인 발행기관·일자는 `null`이다. `EVALUATION_ONLY`와 학생 업로드는 `included_documents`에 들어갈 수 없다.

`AuthoritativeDocumentSet={set_id,set_version,created_at,included_documents,excluded_documents,effective_scope,status}`와 `CurriculumRuleSet={ruleset_id,ruleset_version,source_document_set_id/version,created_at,effective_scope,included_rule_ids,unresolved_conflicts,verification_summary,status}`는 서로 정확한 버전을 참조한다. 각 Rule은 안정된 `rule_id`, `rule_version`, `effective_scope`, `source_documents[]`, `supporting_evidence[]`, `supersedes`, `conflict_status`를 가진다. 출처 ID는 `source_locators[]`의 문서 ID·원본 해시·페이지/절에 연결된다.

`DeterministicDecision`과 `ExecutionTrace`에 `student_state_version`(정규화 입력 해시), `authoritative_document_set_id/version`, `ruleset_id/version`, `applicable_rule_ids[]`, `unresolved_conflict_ids[]`를 고정한다. `AnswerPayload.authority`는 적용 문서, 규칙별 문서 출처·이전 버전, 미해결 충돌을 **실제로 사용한 RuleSet 스냅샷**에서 읽기 전용으로 전달한다. `QUERY_PLAN` 이벤트에도 선택 버전을 남긴다. 서로 다른 RuleSet의 판정은 별도 Decision으로 만들고 같은 학생 상태 해시인 경우에만 차이를 비교한다.

새 문서의 추출 결과는 `EXTRACTED_PENDING_REVIEW`이며 RuleSet 입력이 아니다. 검증된 공식성·문서 관계·원문 locator·규칙 변경이 모두 있는 검토 기록을 통과해야 새 버전을 발행한다. 미해결 충돌이 학생 졸업 판정에 영향을 주면 `UNKNOWN`/`NEEDS_INFORMATION`과 충돌 ID·출처를 반환한다. 충돌이 없는 기존 v1 Core 계산값과 요건 상태는 유지한다.

## 남은 요건과 과목 후보 계약 (2026 Core)

`StructuredQuery(intent=REMAINING_PLAN, focus=ALL|MAJOR|GENERAL|MAJOR_REQUIRED, course_id?)`는 학생의 학년 라벨을 입력 조건으로 사용하지 않는다. 서버가 `FETCH_REQUIREMENTS` 실행 결과를 `RemainingRequirementSummary={satisfied_requirements[],unsatisfied_requirements[],needs_information[],not_applicable_requirements[],missing_credits_by_category,missing_required_courses[],remaining_requirement_groups,other_required_requirements[],progress,student_information_needed[]}`로 투영한다. `progress`는 각 요건의 관찰값·요구값·상태와 `is_lower_bound`를 보존하며 영역을 합친 종합 퍼센트는 만들지 않는다.

`CandidateCourse={course_id,course_name,credits,course_classification,candidate_status,satisfies_requirement_ids[],already_completed,relationship_ids[],provenance,next_term_offering_status,prerequisite_status}`는 VERIFIED 편성행과 실제 `SATISFIES` 그래프 관계에서만 생성된다. 상태는 `REQUIRED`(미이수 지정 필수), `ELIGIBLE_OPTION`(확인된 미충족 요건에 기여), `ALREADY_COMPLETED`, `NOT_APPLICABLE`이다. 선택 후보는 **졸업요건상 후보**이며 개설·수강 가능성 또는 선수과목 충족을 뜻하지 않는다. 해당 정보가 공식 확인되지 않으면 `NOT_VERIFIED`다.

학생용 `AnswerPayload.remaining_presentation`은 위 결정값의 표시 전용 투영이다. 충족·미충족·정보 부족 건수, 미이수 지정 필수(미확인이면 상태 유지), 기타 필수 증빙, 영역별 부족 학점, 전공/교양 선택 후보 수와 각 미충족 Rule에 연결된 후보 ID·건수를 포함한다. 한 과목이 여러 요건에 연결될 수 있어 요건별 건수를 합산하지 않는다. 서버는 이 투영을 결정값으로 재계산·검증하고, 기본 답변에는 후보 수만 요약한다. 펼쳐보기의 전체 후보는 실제 `EvidenceBundle`의 `SATISFIES` 관계·Rule 출처·PDF 위치를 사용한다. 실제 개설, 선수과목, 시간표 충돌은 별도 공식 정보 없이는 미확인으로 표시한다.

`DeterministicDecision.remaining_requirements`와 `candidate_courses`는 RuleSet v1 및 그래프 스냅샷과 함께 해시된다. `ExecutionTrace`에는 카탈로그 조회, `SATISFIES` 관계 조회, 투영 계산 이벤트가 남는다. 가정 이수는 기존 `WHAT_IF` 계약을 사용하며 원본 StudentState를 수정하지 않는다.

## 공식 PDF 정책 보강 계약 (v2 도입, v3 유지)

`CRS-CE-2026-CORE` v2는 같은 `ADS-CE-2026-CORE` v1과 실행 규칙을 유지하고, 원문 33쪽에서 재확인한 교양 적용 예외·상한 초과분 처리 `PolicyFact` 두 건만 추가했다. 현재 활성 v3는 이 정책과 실행 규칙을 그대로 보존하고 교양 편성학기 셀만 보강한다. 불변 v1/v2 스냅샷은 과거 판정 재현에 남는다. 위 남은 요건 계약의 RuleSet v1 기술은 최초 구현 기준이며, 실행 시에는 항상 결정과 trace에 고정된 활성 버전을 사용한다.

`StructuredQuery(intent=POLICY_LOOKUP)`은 학생 상태 없는 정책 조회를 허용한다. `topics[]`, 적용 대상의 `student_categories[]`·`program_type`, `entry_year`, `historical_scope_requested`, `requested_calculations[]`는 서버가 허용 목록으로 검증한다. 학생 개인값이 필요한 질문의 정책 부분만 확정 가능하면 `partial_policy_query`와 `STUDENT_STATE_FOR_PERSONAL_CALCULATION`을 함께 반환한다. 미확인 학생 유형은 적용된 것으로 추측하지 않는다.

`lookup_result.calculations[]`는 `operation`, `source_rule_ids[]`, `required_amount`, `earned_amount`, `recognized_amount`, `remaining_amount`, `excess_amount`, `capped_amount`, `excluded_amount` 중 해당 연산에 필요한 필드를 가진다. 교양 상한은 공식 42학점 규칙을 조회한 경우에만 `recognized=min(earned, cap)`, `excess=max(earned-recognized,0)`, `remaining=max(required-recognized,0)`으로 계산한다. 이는 정책 가정값 계산이지 학생 이수 인정 기록이 아니다. 개인 판정의 `RequirementResult.credit_calculation`은 실제 인정 입력과 Rule ID를 별도로 기록한다. 모든 계산은 `ExecutionTrace`의 실제 연산 이벤트와 출처 locator로 검증한다.

## 편성정보 계약 (v3)

`CatalogEntry.grade_term` 원문과 교양 `placement_term_raw`는 보존한다. 조회 결과와 `CandidateCourse`에 읽기 전용 `curriculum_placement={normalization_version,curriculum_id,raw_grade_term,raw_term,grade_scope,grades[],slots[{grade,grade_scope,term}],term_verification_status,grade_verification_status,source,fact_id,actual_offering_status,student_eligibility_status}`를 전달한다. `CandidateCourse.student_eligibility_status`와 기존 `next_term_offering_status`는 `NOT_VERIFIED`다. 편성 학년 미기재와 학기 미확인은 독립 상태다.

`StructuredQuery(intent=PLACEMENT_LOOKUP,classifications[],curriculum_id,department_id,placement_filter)`는 학생 입력 없이 허용한다. `placement_filter={grade?,terms[],term_match:ANY|ALL}`은 서버 허용값으로 검증하며 학년 1..4와 정규·계절학기 네 열거값만 실행한다. 구체 과목은 `COURSE_LOOKUP, placement_requested:true`, 개인 미이수/후보 교집합은 `REMAINING_PLAN, placement_filter, classifications[], group_by_placement:true`로 구조화한다. QueryPlan의 `placement_classifications`가 요청 분류 범위를 기록한다. 특정 학생의 과거 졸업 적용조건과 현재 2026 편성표의 일반 조회는 구분한다.

카탈로그 `lookup_result` 또는 개인 `placement_view`에 `selection={filters,matched_course_ids[],needs_verification_course_ids[],excluded_course_ids[]}`, `groups[{term,label,course_ids[],course_count}]`, `next_term_basis`를 반환한다. 미지정 다음 학기 기준은 `UNSPECIFIED`; 확인 필요 과목은 삭제하지 않는다. 복수 편성 과목은 여러 그룹에 속하므로 그룹별 수를 총 과목 수로 합산하지 않는다. 개인 필터는 요건·인정학점·전체 후보를 수정하지 않는 별도 표시다.

`ExecutionTrace.PLACEMENT_SELECTION`은 실제 읽은 entry ID와 필터·반환 분할을 기록한다. verifier가 원문 셀 투영, 실제 CatalogEntry 관계, 후보 연결, 선택 및 그룹을 재계산·대조한다. 상세 형식과 원문 사례는 [편성정보 설계](curriculum_placement.md)를 따른다.

## 답변 불변식

- `AnswerPayload.decision`은 `DeterministicDecision`과 동일 ID/해시를 가리킨다. LLM은 한국어 문장화만 하고 계산·조회·졸업 판정 필드를 쓸 권한이 없다.
- 답변의 모든 수치·과목·상태·PDF 페이지는 `Decision`/`EvidenceBundle`/`ExecutionTrace`의 실제 사용 ID에 매핑되어야 한다. 매핑 실패 시 그 문장을 버리고 서버 템플릿으로 표현한다.
- `graduation_outcome=ELIGIBLE_PDF`일 때만 “해당 PDF 기준 졸업 가능”을 표현할 수 있다. `UNKNOWN`이면 정보 부족, `NOT_ELIGIBLE_PDF`이면 확인된 미충족을 나타내며 서로 바꾸지 않는다.
- 개인 이수기록, 원문 PDF 해시, 규칙 세트 해시, 계약 버전이 같으면 LLM 교체와 관계없이 `DeterministicDecision`의 계산 필드는 같아야 한다.
