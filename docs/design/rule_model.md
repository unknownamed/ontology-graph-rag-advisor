# Rule Model: 결정적 판정 IR

## v4 원문 예외 정정

기존 MIN_CREDITS/REQUIRED_COURSES/REQUIRED_EVIDENCE 유형은 유지한다. 영어 면제는 원문 PolicyFact와 `conditional_adjustments`로 특정 기초교양 Rule의 요구량만 조건부9→7로 조정한다. 조건은 확인된 개인 면제와 영어 미이수이며, 영어 이수의무 면제·학점 자동 부여0·교양 총량 보충 Rule·다른 필수군 유지를 명시한다. 면제 미확인 입력으로 확정 감액하지 않는다. 졸업인증의 원문 장애 면제는 `conditional_exemptions`에 근거를 연결한다.

RequirementResult는 실제 계산과 공식 최종 결과 입력, 확인된 면제, 적용조건 정보 부족을 구분한다. coverage는 Rule ID 존재만으로 확정하지 않고 학생 조건과 입력 범위를 함께 검사한다. 인증 세부 조건 전체 계산은 현재 미구현이다. v1/v2/v3 스냅샷은 보존하며 변경 Rule 세 건에 새 rule_version/supersedes 계보를 남겼다. [검증과 한계](source_accuracy_corrections.md)를 따른다.

## 규칙 정의와 실행 결과를 분리

원문 사실은 `ontology_model.md`의 편성표·증거로 저장하고, 판정은 아래 **유형이 정해진 IR**로 수행한다. 규칙 문장은 설명용 메타데이터일 뿐 실행식이 아니다. 규칙 집합은 `rule_set_id`·버전·콘텐츠 해시로 고정한다. 각 `RuleDefinition`은 `rule_id`, `rule_type`, `applies_to`(학과/프로그램/입학·적용연도/이수유형), `when`(조건), `inputs`(타입·조회 범위), `required_value`, `calculation`(허용 연산과 산입 순서), `source_refs`, `verification_status`, `supersedes`/`exception_of`(필요 시)를 갖는다. **`result_state`와 계산값은 학생·시나리오별 `RuleEvaluation`에만** 기록한다.

`RuleEvaluation`의 최소 필드는 `evaluation_id`, `rule_id`, `student_state_id`, `scenario_id|null`, 실제 사용한 입력값과 근거 ID, 요구값, 계산값, `result_state`, 부족값 또는 정보 부족 이유, `execution_event_id`다. 같은 규칙 정의를 여러 학생·시나리오에 적용해도 원문 규칙 값은 변하지 않는다.

조건식은 `AND`, `OR`, `NOT`, `EQ`, `IN`, `RANGE`, `EXISTS`와 고정된 필드 경로만 허용한다. 임의 코드·SQL·Cypher·LLM 문장은 실행하지 않는다. 적용연도 선택 자체가 미확인이면 해당 규칙을 `NOT_APPLICABLE`로 건너뛰지 않고 `NEEDS_INFORMATION`으로 남긴다.

## 필요한 연산자

| `rule_type` | 확정된 원문 근거와 계산 의미 |
| --- | --- |
| `MIN_CREDITS` | PDF 261·577의 2026 컴퓨터공학과 교양34, 전필21, 전선24, 심화33, 총130처럼 지정 영역에 **실제 산입된** 학점을 합산해 하한과 비교. 미완전 성적표는 부족으로 확정하지 않는다. |
| `REQUIRED_COURSES` | PDF 262–263의 전필 9행(0학점 논문·심층상담 포함)을 과목/승인된 대체 지정으로 확인. 과목표 적용 버전과 PDF 264 경과조치가 필요하다. |
| `MIN_COURSE_COUNT` / `AT_LEAST_N_OF` | PDF 33 균형교양 4영역 각 1과목, PDF 570 인증 선택영역 5개 중 2개 이상. 같은 영역의 두 과목을 서로 다른 영역 두 개로 세지 않는다. |
| `ALL_OF` / `ANY_OF` | 졸업의 학점·논문·인증 결합(PDF 565), 기초교양 택1(PDF 33), 인증 수단 선택(PDF 570). 조합 결과는 자식의 근거를 보존한다. |
| `CONDITIONAL` | 학과·교육과정 연도·학적·다전공 **선발연도** 조건. PDF 264의 연도별 소급, PDF 476의 2025 선발 전후 중복 상한을 서로 다른 조건으로 표현. |
| `CREDIT_CAP` | PDF 33 일반 교양 인정 상한42. PDF 264의 2002–2020 컴퓨터공학과 초과 교양 잔여 인정은 해당 필드만 바꾸는 출처 있는 예외다. |
| `NO_DOUBLE_COUNT` | PDF 14의 동일과목 재수강 선이수 성적 삭제, PDF 476–477의 여러 전공 영역 인정과 졸업 총학점 **한 번** 산입을 구별. |
| `SUBSTITUTE` / `EXEMPTION` | PDF 14의 공식 동일·대체 **지정** 및 학생 선택, PDF 33의 영어 과목 면제(0학점), PDF 264의 옛 의무 해제. 지정 목록이 없으면 대체 인정은 실행 불가. |
| `REQUIRED_EVIDENCE` | PDF 565 논문 심사·최종학기 수강신청, PDF 569–575 인증의 증빙 확인. `해당사항 없음`인 컴퓨터공학과 논문 **대체요건**(PDF 567)을 논문 면제로 바꾸지 않는다. |

`RECOGNIZE_CREDIT`는 위 연산의 준비 단계다: 완료된 시도 → 공식 동일/재수강 처리 → 적용 과목표의 이수구분 → 학과/다전공 영역 인정 → 상한·중복 산입을 순서대로 계산하고 `CreditRecognition`을 출력한다. 분류/인정은 과목 고정 속성이 아니다. 각 중간 산입과 제외 이유를 실행 기록에 남긴다.

## 상태와 전파 규칙

| 상태 | 필요한 증거 |
| --- | --- |
| `SATISFIED` | 적용 대상·규칙·필요 입력·계산값이 검증됐고 요구값 충족. |
| `UNSATISFIED` | 적용과 필수 입력 범위가 충분히 확인됐고 요구값 미달. 단순히 업로드에서 과목이 보이지 않는 것은 부족 증거가 아니다. |
| `NEEDS_INFORMATION` | 적용연도, 성적표 범위, 공식 지정, 필수 출처 또는 증빙이 `UNVERIFIED`·`CONFLICTED`·`MISSING`이어서 참/거짓 확정 불가. 필요한 항목 ID를 함께 반환. |
| `NOT_APPLICABLE` | 검증된 적용 조건이 거짓임. 미확인은 이 상태가 아니다. |

`ALL_OF`: 자식의 확정된 `UNSATISFIED`가 있으면 그 요건군은 `UNSATISFIED`이며 다른 미확인 항목도 함께 보고한다. 확정 실패가 없고 미확인이 있으면 `NEEDS_INFORMATION`; 적용되는 자식이 전부 `SATISFIED`일 때만 `SATISFIED`. `NOT_APPLICABLE`은 합산 대상에서 제외한다. `ANY_OF`는 검증된 만족 자식 하나로 만족, 전부 확정 실패일 때만 불충족, 나머지는 정보 부족이다. `AT_LEAST_N_OF`는 만족 수가 N 이상이면 만족; 확정 실패와 미확인을 모두 최대로 세어도 N 미만일 때만 불충족; 그 사이는 정보 부족이다.

필요한 `RuleDefinition`·사실·관계·학생 증거 중 하나라도 `VERIFIED`가 아니면 그 값에 의존한 만족/불충족을 확정하지 않는다. 다만 검증된 조건으로 규칙 적용 대상이 아님이 먼저 확인되면 `NOT_APPLICABLE`로 처리한다. `UNVERIFIED` 원문 사실을 숫자 0, 빈 과목군, 자동 면제로 변환하는 것은 계약 위반이다.

## 적용 우선순위와 전체 판정 폐쇄성

1. `CurriculumApplicability`가 학점 기준 연도, 개편 후 과목표 버전, 논문/인증 선택 기준을 **분리해서** 확정한다(PDF 13, 565, 569, 575). 입학연도만으로 예외 승인·전과·편입·재입학을 추측하지 않는다.
2. 명시적 학과 경과조치(PDF 264)는 대상·기간이 참일 때 지정된 `override_fields`만 바꾼다. 예를 들어 교양 소급값은 영역값에 적용하고, 연도별 표의 졸업 **총학점**까지 임의 변경하지 않는다. 후보 규칙 둘의 우선관계가 원문으로 확정되지 않으면 `CONFLICTED`이며 정보 부족이다.
3. 재수강/동일 과목을 먼저 정리하고, 인정 영역을 구한 다음 상한·중복 제한을 적용한다. 동일 이수는 전공별 요건에 허용 범위 내에서 보일 수 있어도 졸업 총학점에는 한 번만 산입한다. 0학점 필수는 학점 합계와 독립적으로 완료 여부를 검사한다.
4. 전체 졸업 판정은 `RuleCoverageManifest`가 해당 학생에게 적용될 수 있는 **학점(총·영역·필수), 논문, 인증, 다전공/부전공, 경과조치·예외** 규칙군을 완전하게 열거·검증했을 때만 `SATISFIED`가 될 수 있다. 일부 규칙만 적재됐다면 알려진 규칙을 모두 통과해도 전체 상태는 `NEEDS_INFORMATION`이다. 확정된 미충족은 별도로 표시한다.

동일한 정규화 `StudentState`·시나리오·사실 스냅샷·규칙 버전에는 순서와 산술이 결정적이다. LLM 출력은 이 함수의 입력 규칙이나 요구값을 바꾸지 못한다.

## 2026 컴퓨터공학과 규칙 IR 예시

아래는 **설계 예시**이며 실행 파일이 아니다. 값 21과 적용 범위의 근거는 PDF 23·261·577(CE-02)이다. `result_state`는 이 정의에 없고, 실제 학생 입력을 받은 평가 레코드에 생긴다.

```json
{
  "rule_id": "R-CE-2026-MAJOR-REQUIRED-CREDITS",
  "rule_type": "MIN_CREDITS",
  "applies_to": { "department_id": "DEPT-COMPUTER-ENGINEERING", "credit_policy_year": 2026 },
  "when": { "op": "EQ", "field": "applicability.credit_policy_year", "value": 2026 },
  "inputs": [{ "name": "recognized_major_required_credits", "type": "RecognizedCreditSum", "classification": "MAJOR_REQUIRED" }],
  "required_value": { "credits": 21 },
  "calculation": { "op": "SUM_DISTINCT_ELIGIBLE_CREDITS", "compare": "GTE", "unit": "CREDIT" },
  "source_refs": ["CE-2026-OVERVIEW", "CE-CREDITS", "CE-2026-GRAD"],
  "verification_status": "VERIFIED",
  "supersedes": []
}
```

## 구현 확장: 규칙 정의 조회

`POLICY_LOOKUP`은 `Requirement` 노드의 `required_value`, `course_ids`, `areas`, 적용 `program_types`를 조회할 수 있다. 이 경로는 `RequirementResult`의 `SATISFIED`/`UNSATISFIED`를 만들지 않는다. 학생 개인의 요건 충족을 묻는 질문은 기존 Rule Engine으로 보내고, 단일전공 78학점과 복수전공 45학점을 같은 적용 범위로 합치지 않는다. 적용연도·권장·경과조치 등 비계산 사실은 별도 `PolicyFact`로 조회하며, 공식 동일·대체 지정 목록이 없다는 상태를 그대로 보존한다.

현재 활성 RuleSet v2는 교육과정 PDF 33쪽의 편입생 교양 의무 면제, 야간·재직자/성인학습자 관련·계약학과의 영역별 최소 면제, 일부 학과 유형의 교양 최소 26학점 및 상한 초과분 처리 사실을 추가한다. 적용 대상은 `student_category`와 그 증빙, `program_type`, 입학연도·학점기준연도·과목표 연도를 분리해 검사한다. 적용/비적용 결과에는 근거 `policy_fact_id`와 실행 이벤트를 남긴다. 해당 학생의 학과 유형 또는 과거 RuleSet이 확인되지 않으면 2026 일반 학생 기준을 개인 판정에 전용하지 않는다. 이 v2는 기존 19개 실행 `Requirement`의 요구값과 Rule ID를 변경하지 않는다.
