# 독립 50문항 실패 원인 및 수정 검증

수정 전 원본 결과는 `independent_scenario_results_before.json`과 `independent_scenario_report_before.md`에 보존했다. 아래의 **이전 SQ**와 **이전 QueryPlan**은 16건 모두 `null`이었다. 따라서 그래프나 규칙 엔진에 도달하기 전의 해석 실패 14건과 입력 경계의 HTTP 400 두 건을 먼저 분리했다. 표의 **현재 SQ/QueryPlan**은 수정 후 실제 `/api/query` 실행 기록을 요약한 것이며 전체 객체는 `independent_scenario_results.json`에 있다.

| ID · 질문 | 기대 의미 구조 | 이전 Entity Resolution / 실제 실패 계층 | 근본 원인 | 현재 SQ → 실제 QueryPlan · 일반화된 수정 |
| --- | --- | --- | --- | --- |
| FACT_03 · 2026 컴퓨터공학과 전공 과목은 총 몇 개야? | 검증된 2026 전공 편성 과목 COUNT | `CATALOG_AGGREGATE_UNSUPPORTED` / 조회 계획 | 카탈로그 집계 연산 부재 | `CATALOG_AGGREGATE(COUNT, 전필+전선)` → `FETCH_CATALOG_SET, AGGREGATE_COUNT`; 적용 버전·학과·분류를 검증 |
| FACT_04 · 컴공 전공 과목 전체 학점 합계가 어떻게 돼? | 편성 과목 학점 SUM, 졸업 최소치와 별개 | `CATALOG_AGGREGATE_UNSUPPORTED` / 조회 계획 | 편성 학점 합계와 최소 요건을 구분할 집계 부재 | `CATALOG_AGGREGATE(SUM_CREDITS, 전필+전선)` → `FETCH_CATALOG_SET, AGGREGATE_SUM_CREDITS`; 반환 행만 합산 |
| FACT_07 · 컴퓨터공학과 졸업 판정에 쓰는 요건 종류를 보여줘. | 학생 판정 없이 VERIFIED 요건 목록 | HTTP 400 / 입력 경계 | 모든 요건 질문에 학생 상태를 요구 | `POLICY_LOOKUP(ALL_REQUIREMENTS)` → `FETCH_REQUIREMENTS`; VERIFIED만 원문 출처와 열거 |
| EDGE_05 · 없는 과목 코드 ABC9999를 들었다고 넣으면 어떻게 처리해? | 존재 여부 확인, 미확인 과목 불인정 | `QUESTION_INTENT` / 의도·엔티티 | 코드 뒤 조사와 존재 확인 표현을 해석하지 못함 | `ENTITY_CHECK(ABC9999)` → `FETCH_CATALOG_ENTRY, FETCH_REQUIREMENTS`; 미존재를 VERIFIED 사실로 만들지 않음 |
| EDGE_06 · 과목명이 비어 있는 이수기록 하나가 있어. 그걸 졸업학점에 넣어도 돼? | 불완전 기록 보존, 학점 확정 보류 | HTTP 400 / 입력 계약 | `course_id` 누락 기록을 API에서 즉시 거부 | `CREDIT_SUMMARY(GRADUATION_TOTAL)` → 조회·요건 평가; 누락 필드와 제외 이유를 기록하고 `NEEDS_INFORMATION` |
| EDGE_07 · 같은 학생 정보를 순서만 바꿔서 넣어도 결과가 똑같아야 해. 확인해줘. | 입력 순서 불변 비교 | `QUESTION_INTENT` / 의도 | 메타 검증 의도 없음 | `CONSISTENCY_CHECK(INPUT_ORDER)` → 실제 조회 두 번·`COMPARE_DECISIONS`; 정규화된 결정/근거 비교 |
| EDGE_08 · 같은 질문을 두 번 하면 판정 결과와 근거가 같아? | 동일 입력 반복 비교 | `QUESTION_INTENT` / 의도 | 반복 일관성 의도 없음 | `CONSISTENCY_CHECK(REPEAT)` → 실제 조회 두 번·`COMPARE_DECISIONS`; 동일 결정/근거 확인 |
| SIM_02 · 전공필수 하나를 더 이수했다고 가정하면 부족한 요건이 줄어들어? | 미충족 필수 후보 1개만 특정 가능하면 가정 | `COURSE_ENTITY` / 대상 식별 | 명시 코드 없는 가정을 전부 거부 | `WHAT_IF(MISSING_REQUIRED_ONE)` → 실제 조회·요건 평가·대상 검증; 유일할 때만 별도 시뮬레이션 |
| SIM_03 · 이 과목을 들었다고 가정한 결과랑 실제 내 이수내역을 구분해서 보여줘. | 대화 참조 과목으로 실제/가상 비교 | `COURSE_ENTITY` / 맥락 식별 | 선행 과목이 없을 때 대상 미확정을 표현 못함 | `WHAT_IF(CONTEXT_COURSE, compare)` → 현재 상태 조회; 선행 과목 없으면 `NEEDS_TARGET`, 가상값 없음 |
| SIM_04 · 과목 두 개를 추가로 들으면 졸업 가능 여부가 바뀌는지 계산해줘. | 과목 2개를 명시해야 복수 가정 | `COURSE_ENTITY` / 대상 식별 | 복수 과목 가정 계약 부재 | `WHAT_IF(UNSPECIFIED_TWO_COURSES)` → 현재 상태 조회; 대상 2개를 요청. 명시된 복수 ID는 별도 가상 상태로 계산 |
| SIM_05 · 없는 과목을 추가로 들었다고 가정하면 계산해도 돼? | 미존재 대상 거부, 현재 상태는 확인 | `COURSE_ENTITY` / 대상 식별 | 미존재·미지정 대상과 가정 자체를 구분 못함 | `WHAT_IF(UNKNOWN_STUDENT_COURSE)` → 현재 상태 조회·대상 검증; 검증 전 가상 계산 금지 |
| SIM_06 · 0학점으로 등록된 필수 항목을 추가했다고 가정하면 학점 말고 요건 상태만 바뀌는지 보여줘. | 미충족 0학점 필수의 요건 변화 | `COURSE_ENTITY` / 대상 식별 | 필수 조건으로 후보를 찾지 못함 | `WHAT_IF(MISSING_ZERO_CREDIT_REQUIRED_ONE)` → 유일 후보 검증·별도 계산; 학점과 요건 delta 분리 |
| SIM_07 · 가정 시뮬레이션을 두 번 해도 실제 성적표 데이터는 그대로지? | 가정 반복 후 실제 상태 불변 검증 | `COURSE_ENTITY` / 의도 | 시뮬레이션 무결성 질문을 과목 추가로만 해석 | `CONSISTENCY_CHECK(SIMULATION_IMMUTABILITY)` → 실제 실행·가정 실행·원본 비교 이벤트 |
| SIM_08 · 이 과목을 추가하면 전공필수랑 총학점 중 뭐가 바뀌는지 각각 알려줘. | 참조 과목의 요건별 delta | `COURSE_ENTITY` / 맥락 식별 | 맥락 부재 시 부분 답변 계약 없음 | `WHAT_IF(CONTEXT_COURSE, requirement+credit delta)` → 현재 상태만 확정, 선행 과목 요청 |
| CTX_05 · 내가 지금 부족한 조건이랑, 과목 하나 추가했을 때 없어지는 부족조건을 같이 보여줘. | 실제 부족조건 + 미지정 가정의 변화 | `COURSE_ENTITY` / 대상 식별 | 복합 질문에서 가정 대상 미확정을 전체 거부 | `WHAT_IF(UNSPECIFIED_COURSE, compare)` → 현재 부족조건 표시, 가상 delta는 보류 |
| EVID_03 · 답변 만들 때 실제로 어떤 관계와 규칙을 사용했는지 보여줘. 없는 경로는 만들지 마. | 실제 반환 관계·실행 규칙 열거 | `QUESTION_INTENT` / 의도·설명 | 실행 기록 설명 의도 없음 | `TRACE_EXPLAIN` → 실제 조회·규칙 평가; ExecutionTrace와 EvidenceBundle의 ID만 반환 |

수정 후 모든 행의 Entity Resolution은 `RESOLVED`다. 단, `RESOLVED`는 **질문 의미를 구조화했다는 뜻**이며 시뮬레이션 대상까지 확인했다는 뜻이 아니다. SIM_03·04·05·08과 CTX_05의 최종 상태는 `NEEDS_TARGET`인 안전한 부분 답변이다. 가상 결과나 delta를 계산했다고 주장하지 않는다. CTX_04는 빠진 학기 때문에 특정 전필 미이수를 확정할 수 없어 원래의 SKIP을 유지한다.

각 수정은 특정 질문 문자열이나 ID가 아니라 집계 연산, 대상 선택자, 메타 의도, 누락 필드 상태 및 실제 trace 계약에 적용된다. 신규 `REV2_01`–`REV2_15`는 조건별 다른 카탈로그 범위, 다중 과목, 두 후보의 모호성, 존재하지 않는 코드, 부분 성적표, 입력 순서 등으로 이를 역검증한다.
