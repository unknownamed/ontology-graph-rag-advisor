# Knowledge Model: 교육과정 사실

## 범위와 원칙

근거는 `docs/curriculum/2026년도 교육과정.pdf`와 1단계의 `curriculum_inventory.md`, `computer_engineering_scope.md`, `source_index.json`뿐이다. PDF의 편성 사실, 학생의 실제 이수 사실, 규칙 실행 결과를 다른 층으로 둔다. 이 문서는 논리 모델이며 Neo4j 레이블·간선이나 저장 방식을 확정하지 않는다. 모든 원문 사실과 관계에는 고유 ID, 적용 범위, `verification_status`, `source_locator_id`를 부여한다.

## 개체와 식별자

| 개체 | 필수 속성·책임 | 원문 연결 또는 경계 |
| --- | --- | --- |
| `Department`, `MajorProgram` | `department_id`, 공식 명칭; `program_id`, 주전공/복수/부/연계/융합 종류 | 컴퓨터공학과 공식 명칭 PDF 259. 학과와 학생의 이수 경로는 별도다. |
| `CurriculumVersion` | `curriculum_id`, 연도, 버전 역할(`CREDIT_POLICY`, `COURSE_CATALOG`, `THESIS_POLICY`, `CERT_POLICY`) | 입학 시 학점기준과 개편된 과목표가 다를 수 있음(PDF 13, 575). 문서 발행연도=학생 적용연도로 취급하지 않는다. |
| `CurriculumApplicability` | `applicability_id`, 학생/학과/영역, 기준 입학연도·실제 적용연도·학적 변동, 근거, 상태 | 학점·교과목·논문·인증별 선택 버전이 다를 수 있다. 전과/편입/재입학, 학과 경과조치는 별도 근거를 요구한다. |
| `Course` | 안정적인 `course_id`(학수번호 기반), 명칭 식별 | 과목 자체에 전필/전선 또는 학생 인정학점을 고정하지 않는다. 코드가 같아도 연도별 속성을 별도 기록한다. |
| `CatalogEntry` | `entry_id`, `course_id`, `curriculum_id`, 학과, 학점, 이수구분, 권장/필수 표시, 편성 학년·학기 | PDF 262–263의 43행은 2026 편성표 항목. `CDA0008`은 전공선택이면서 부전공 필수 `※`다. |
| `CourseOffering` | 실제 개설연도·학기·분반 ID | 편성표의 학년/학기는 개설 안내이며 실제 개설 증거가 아니다. 현재 원문으로는 실제 분반을 생성하지 않는다. |
| `Requirement`, `RequirementGroup` | `requirement_id`, 영역·대상·규칙 참조; 그룹의 필수 결합 관계 | 학점 21/24/33, 교양 4영역, 논문, 인증 등. 수치와 조건은 `rule_model.md`의 기계 판독 IR에 둔다. |
| `Student`/`StudentState` | 학생 식별자, 학적·전공·입학연도; 특정 시점의 불변 입력 스냅샷 | PDF는 개별 학생 자료가 아니다. 업로드/사용자 입력은 검증된 학생 증거로 별도 취급한다. |
| `CourseAttempt`/`CompletionRecord` | 수강 시도, 학기, 원래 학점·성적, 합격/취소/재수강 상태, 학생 증거 ID | 수강 신청과 이수 완료를 혼동하지 않는다. 빈 이수목록만으로 미이수 확정 금지. |
| `CreditRecognition` | `recognition_id`, 이수기록, 학생에게 인정된 영역·학점, 산입 여부, 규칙 실행 ID | 규칙 엔진의 **파생 결과**다. 과목표 학점, 취득학점, 졸업에 산입되는 학점은 각각 다를 수 있다(PDF 33, 14, 476). |
| `EquivalenceDesignation`, `ReplacementDesignation` | 지정 ID, 두 과목·적용 버전·시점·선택 요건·확인 상태 | PDF 14는 처리 원칙만 제시한다. 실제 지정 목록이 없으면 `MISSING`으로 두며 과목명 유사성으로 연결하지 않는다. |
| `Exception`/`Transition` | 예외 ID, 대상·기간·효과, 우선 적용할 규칙 참조 | PDF 264의 컴퓨터공학과 연도별 소급·의무 해제, PDF 33의 교양 예외. 적용 조건이 확인돼야 효력이 있다. |
| `Evidence` | 학생 자료나 공식 승인 기록의 ID, 종류·위치·추출 상태 | 성적표/논문/인증 증빙은 원문 교육과정 PDF와 별개다. 질문 텍스트는 이수 증거가 아니다. |

`CourseClassification`은 `CatalogEntry`의 연도·학과·프로그램별 값으로 표현한다. `전공필수`, `전공선택`, 교양 세부 영역, 부전공 필수 표시는 서로 독립적인 속성/관계다. 이수 결과의 영역은 이 값과 학생의 적용 교육과정·동일/대체/예외를 규칙이 결합해 산출한다.

## 관계와 식별

| 관계 ID 형식(예시) | 의미 |
| --- | --- |
| `rel:catalog:2026:ce:CDA0143` | `CurriculumVersion(2026 course catalog)` → `CatalogEntry(CDA0143)` → `Course`; PDF 262 행을 출처로 가짐. |
| `rel:class:2026:ce:CDA0143` | 해당 **편성표 항목** → `전공필수`; 과목 전체의 영구 속성이 아님. |
| `rel:minor-required:2026:ce:CDA0008` | 컴퓨터공학과 부전공 → 자료구조 필수 `※`; 주전공 전필 관계와 구분. |
| `rel:applies:<student-snapshot>:<domain>` | 학생 스냅샷 → 학점/교과목/논문/인증의 적용 기준; 판정 시 근거가 필요. |
| `rel:attempt:<attempt-id>` | 학생 → 실제 수강 시도·완료 기록; 가상 입력은 이 관계에 쓰지 않는다. |
| `rel:req:<requirement-id>:<rule-id>` | 요건 → 결정적 규칙; 출처와 유효 기간이 함께 연결된다. |

모든 관계는 `relationship_id`, 양끝 ID, 관계형, 유효 교육과정/기간, 확인 상태, 출처 ID를 가진다. 예시 ID는 설계용이다. 물리 DB의 실제 ID나 탐색 순서를 뜻하지 않는다.

## 실제 상태, 가정, 불확실성

- 실제 `StudentState`는 확인된 `CompletionRecord`만 가진다. “이 과목을 들었다면?”은 원본 스냅샷을 변경하지 않는 `ScenarioDelta`에 계획 과목·가정(성공 이수, 학점, 학기)을 둔다. 가정의 결과에는 `SCENARIO` 표식을 붙인다.
- `VERIFIED`는 출처와 값을 대조함, `UNVERIFIED`는 후보이나 미확인, `CONFLICTED`는 양립 불가능한 확인 후보, `MISSING`은 필요한 사실/지정이 없음이다. 마지막 세 상태를 0학점이나 거짓으로 바꾸지 않는다. 개별 학생 증거에는 별도로 추출·확인 상태를 기록한다.
- 이수기록 범위에 `completion_coverage`를 둔다(예: 전체 학기 성적표 확인 여부). 미제출 학기나 불완전한 업로드가 있으면 “기록 없음”은 미이수 증거가 아니다.
- 출처가 있는 2026 컴퓨터공학과 학점·과목표(PDF 23, 261–263, 577)는 2002–2025 학생의 과목별 필수 목록을 자동으로 채우지 않는다. PDF 264의 경과조치와 실제 적용연도는 별도 관계로 보존한다.

## 구현 확장: 정책 사실 조회

원문 규칙의 **기준값 조회**와 학생에게 규칙을 **실행한 결과**를 구분한다. `Requirement`는 학점·필수과목 등의 계산 IR이다. `PolicyFact`는 적용연도 원칙, 자유선택의 잔여 인정, 공식 동일·대체 처리 원칙, 학과 권장과 경과조치의 존재처럼 계산 없이 조회할 원문 사실이다. SQLite 그래프의 `HAS_POLICY_FACT`는 교육과정 버전에서 각 사실로 연결하고, 모든 사실은 `source_refs`와 `verification_status`를 가진다. `POLICY_LOOKUP`은 학생 취득학점이나 졸업 상태를 계산하지 않는다.
