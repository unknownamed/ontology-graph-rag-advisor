# Provenance Model: 원문부터 실제 실행까지

## v4 조건부 계산과 범위 근거

영어 조정은 실제 조회 PolicyFact 관계·PDF33 locator·확인된 학생 면제 입력을 연결하며, `RULE_CONDITIONAL_ADJUSTMENT`에 기본/실효 요구량·보충 Rule·자동 학점0을 기록한다. 개인 면제 사용은 `RULE_EXEMPTION_INPUT`, 시험점수 정책 비교는 `POLICY_EXAM_CRITERION`으로 분리한다. 정책 연도별 실행은 `POLICY_YEAR_RESULT`, 원문 충돌 행은 `CATALOG_CONFLICT_LOOKUP`에 실제 문서 해시/행을 기록한다.

`COVERAGE_CHECK.details`는 적재 실행·적용조건·입력 완전성·직접 계산/공식 결과 입력을 구분한다. 미구현 조건에 실제 PDF locator가 있으면 연결하되, 알려지지 않은 주장에 원문을 꾸며 붙이지 않는다. UI는 이 실행 기록과 당시 답변 payload를 표시하며 PDF 내부 방문 순서를 만들지 않는다. verifier는 조건부 계산·연도·coverage·실제 관계/학생 입력 근거를 대조한다. [v4 기록](source_accuracy_corrections.md)에 원문과 회귀 결과를 정리했다.

## 세 종류의 근거

1. **원문 근거** `SourceDocument`: `source_document_id`, 경로, SHA-256, 제목, PDF 총 페이지. 현재 유일한 교육과정 기준은 `docs/curriculum/2026년도 교육과정.pdf`이며 SHA-256은 `source_index.json`의 `source.sha256`과 일치해야 한다. `SourceLocator`는 PDF 물리 페이지, 인쇄 페이지, 절·표·행·각주, 원문 확인 방식과 범위를 가진다. 인쇄 페이지를 단순 계산해 표기할 때는 관찰된 본문 오프셋 8쪽임을 명시한다.
2. **모델 근거** `Fact`/`Relationship`/`RuleDefinition`: 각각 `fact_id`·`relationship_id`·`rule_id`, 버전, 값/대상, 적용 범위, `verification_status`, `source_locator_ids`를 가진다. 예: 2026 `CDA0143 고급자료구조` 3학점·전공필수는 PDF 262의 과목 행(`CE-COURSES`)에 연결한다. `CI-029`·`CE-06`은 검증 기록의 교차참조이며 PDF 원문 위치를 대체하지 않는다.
3. **학생 근거** `StudentEvidence`: 사용자 입력·업로드의 파일/쪽/행/추출 단위, 확인 상태, 수강 시도/완료/승인과의 연결. 성적표에 과목이 **없는 것**을 미이수 증거로 쓰려면 해당 기간의 성적 범위가 완전함을 입증해야 한다. 평가 전용 폴더의 자료는 이 세 계층 어느 곳에도 적재하지 않는다.

`VERIFIED`=원문/증빙 대조 완료, `UNVERIFIED`=후보이나 미확인, `CONFLICTED`=서로 다른 값이 충돌, `MISSING`=필요한 출처 또는 학생 값 없음. 출처가 두 개라고 자동으로 다수결하지 않는다. `CONFLICTED`/`MISSING` 자체와 원인을 보존하며 수치 0으로 바꾸지 않는다.

## 추적 가능한 ID와 불변 스냅샷

| 레코드 | 반드시 보관할 필드 |
| --- | --- |
| `SourceLocator` | `source_document_id`, `pdf_page`, `printed_page`, `section`, `table_id`, `row_key`, `footnote_marker`, `extraction_method`, `visual_verification`, `verification_status` |
| `FactProvenance` | `fact_id`, 값/단위, 학과·버전·기간, `source_locator_ids`, 검증 상태·검증 시점 |
| `RelationshipProvenance` | `relationship_id`, 시작/끝 ID, 관계형, 유효 범위, `fact_ids`, `source_locator_ids` |
| `RuleProvenance` | `rule_id`, IR 버전·해시, `source_locator_ids`, `fact_ids`, `supersedes`, 검증 상태 |
| `DecisionProvenance` | `execution_id`, 입력/시나리오 해시, 교육과정 PDF 해시, 사실·규칙 스냅샷 ID, 실제 사용한 fact/relationship/rule ID, 결과·trace ID |

원문 PDF가 달라지거나 구조화 사실이 정정되면 기존 ID의 내용을 조용히 바꾸지 않고 새 버전을 만든다. 같은 정규화 입력과 동일 스냅샷·규칙 버전의 **판정 본문**은 같아야 한다. `execution_id`와 시각은 재실행마다 달라도 계산 결과 비교에서 제외한다.

## ExecutionTrace는 수행한 단계만 기록

`ExecutionTrace`는 `execution_id`, 단조 증가 `sequence`, 단계형, 입력 ID/값(민감정보 최소화), 실제 반환 ID, 배제 ID·이유(있을 때), 적용 규칙과 피연산자·계산 결과, 최종 결과 기여 여부를 가진 불변 이벤트 목록이다.

| 단계형 | 기록할 실제 행위 |
| --- | --- |
| `INPUT_EXTRACTED`, `STATE_NORMALIZED` | 어떤 입력에서 어떤 학생 상태 후보를 읽고 무엇을 확인/보류했는지. |
| `QUERY_INTERPRETED`, `ENTITY_RESOLVED` | 질문 의도와 엔티티 후보, 검증된 ID, 모호성. 질문 해석 결과는 사실/판정이 아님. |
| `QUERY_PLANNED`, `QUERY_EXECUTED` | 서버가 생성한 허용 연산·필터, 실제 호출한 조회 단계, 반환된 관계·사실 ID와 개수. |
| `CANDIDATE_EXCLUDED` | **실제로 반환되어 검토한** 후보의 제외 이유(예: 교육과정 연도 불일치, `UNVERIFIED`). 조회되지 않은 후보를 상상해 나열하지 않는다. |
| `RULE_EVALUATED` | 사용한 `rule_id`, 입력값과 해당 입력 ID, 요구값, 계산식 ID, 출력값·상태, 미확인 사유. |
| `DECISION_COMPOSED`, `ANSWER_VERIFIED` | 요건별 상태의 결합, 최종 상태·근거 폐쇄성 점검, 답변 표현의 수치/상태 일치 검사. |

이 `sequence`는 **애플리케이션 단계의 실행 순서**다. 그래프 DB 내부의 노드 방문 순서나 LLM의 숨은 추론 과정은 기록·표시하지 않는다. 실행하지 않은 조회/관계/규칙을 설명에 덧붙이지 않는다. 프론트의 “근거 펼쳐보기”는 `DECISION_COMPOSED` → 실제 `RULE_EVALUATED` → 사용된 fact/relationship → `SourceLocator` 및 학생 증거 순으로 역추적한다. 조회 결과 중 사용하지 않은 후보는 필요할 때만 실제 `CANDIDATE_EXCLUDED` 이벤트로 표시한다.

## 출처 폐쇄성과 실패 처리

- 최종 판정에 기여한 숫자·과목·예외에는 `used_fact_ids`, `used_relationship_ids`, `used_rule_ids`가 있어야 하며 원문 PDF 위치 또는 학생 증빙까지 경로가 이어져야 한다. 경로가 끊기면 판정은 `NEEDS_INFORMATION`이다.
- 원문상 확인되지 않은 동일/대체 지정(1단계 `UNVERIFIED`)은 `CANDIDATE_EXCLUDED`의 근거가 될 수는 있어도 대체 충족의 근거가 될 수 없다. PDF 567의 논문 대체 없음과 PDF 572의 학과 지정 자격증 없음은 서로 다른 `fact_id`를 둔다.
- 사용자 업로드 원문과 개인 식별정보는 답변·로그에 필요한 최소 참조와 마스킹된 요약만 남긴다. 원본 파일 경로/전체 추출 텍스트를 공개 실행 기록에 복제하지 않는다.

정책 사실 조회에서도 실제 `FETCH_REQUIREMENTS` 또는 `FETCH_POLICY_FACTS` 호출과 반환된 관계 ID만 `ExecutionTrace`에 남긴다. `PolicyFact`의 `source_refs`가 PDF 위치로 닫히지 않거나 조회되지 않은 관계가 답변 그래프에 나타나면 출력 검증을 실패시킨다. 정책 기준을 읽은 것을 학생에게 규칙을 적용·계산했다고 표현하지 않는다.
