# 승인 요청서 평가 전 최종 baseline

고정일: 2026-09-30. 이 baseline은 **2026 컴퓨터공학과 국내 일반 학생 단일전공 Core Prototype**의 코드, 공식 데이터, 합성 fixture, 자동 검증 결과를 기록한다. 승인 요청서 평가는 시작하지 않았으며 `evaluation/reference/`의 PDF는 존재와 파일 크기만 확인하고 본문은 열지 않았다.

## 1. 구현된 Core 기능과 지원 범위

- `ADS-CE-2026-CORE` v1은 `CURRICULUM-2026` 한 문서만 포함한다. `CRS-CE-2026-CORE` v1은 VERIFIED 규칙 19개를 고정하며 단일전공에 적용되는 요건 18개를 계산한다. 원문 PDF SHA-256은 `0d800318dc367a89518f9be6be8f559092474bf00b3573e14bd37b6c44b54471`, RuleSet 스냅샷 SHA-256은 `cd411cc541e6c43481ae2341d446d7e6fd38eadb3d9032dc5c9b250ae9585047`이다. 재실행에서 두 해시와 활성 포인터가 일치했다.
- 구조화된 `StudentState` → 허용된 그래프 조회 → 결정적 Rule Engine → `DeterministicDecision`/`ExecutionTrace`/`AnswerPayload` 경로가 동작한다. `RemainingRequirementSummary`는 충족·미충족·정보 부족과 영역별 부족량을, `CandidateCourse`는 실제 미충족 요건에 연결된 필수/선택 후보를 계산한다. 실제 이수와 가상 추가는 분리한다.
- 한국어 질문에서 “앞으로 뭐 더 들어야 해?”와 영역별 잔여 요건·전필·학점·가정 이수를 `/api/query`로 처리한다. 기본 답변은 상태·필수·부족량·영역별 후보 수·확인 필요를 요약하고, 펼쳐보기에는 실제 관계·규칙·계산·PDF 위치와 전체 후보를 표시한다. 로컬 LLM은 해석과 표현만 담당한다.
- PDF/DOCX/PNG 업로드 후보 추출과 `StudentState` 정규화 경로가 있다. 불명확한 행은 자동 인정하지 않으며 사용자 정정·확인 절차가 있다. 이미지·HWP의 모든 실제 자료 유형에 대한 양성 검증을 이 baseline의 보장 범위로 확대하지 않는다. **실제 학생의 졸업 가능 여부는 이 합성 검증으로 보증하지 않는다.**

## 2. 재실행한 검증과 결과

| 검증 | 현재 실행 결과 | 근거 |
| --- | --- | --- |
| 전체 회귀 | `python -m unittest discover -s tests -q`: **191 tests OK** | 이번 baseline 재실행 |
| 합성 Core 경로 | `scripts/demo_core.py`: **5/5 PASS** | 충족·미충족·정보 부족·가정·범위 밖 |
| 학생용 질문 UX | `scripts/verify_remaining_ux_2026.py`: **100/100**, Reviewer **4/4 PASS** | `remaining_2026_ux_results.json` |
| 1~4학년 상태·남은 요건 | `scripts/verify_remaining_2026_e2e.py`: **70/70**, Reviewer **7/7 PASS** | `remaining_2026_e2e_results.json` |
| 모의 2026 PDF 업로드 E2E | `scripts/verify_mock_2026_pdf_e2e.py`: **4/4 기대 판정 일치** | `mock_2026_pdf_e2e_results.json` |
| 독립 50문항 | `scripts/run_independent_eval_local.py`: **49 PASS / 0 FAIL / 1 SKIP** | `independent_scenario_results.json` |
| LLM ON/OFF | 독립 문항 **49/49**, 남은 요건 프로필 **10/10**, 모의 PDF **4/4** 핵심 판정·수치·근거 일치 | 각 결과 JSON 및 검증 스크립트 |
| 정적 검증 | UI JavaScript `node --check`와 `git diff --check` 통과; 평가자료 런타임 유입 검색 PASS | 이번 baseline 재실행 |

이번 실행에는 번들 Python 3.12+ 인터프리터를 사용했다. 자동 API 검증은 실제 HTTP `/api/query` 및 모의 PDF의 `/api/extract → /api/normalize-upload → /api/query`를 통과한다. 브라우저 화면의 펼쳐보기·스크롤·PDF 링크 일치는 직전 UX 검수 기록(`remaining_2026_ux_report.md`, `PLAN.md`)에 있으며, **이번 baseline 작업에서 브라우저 조작은 새로 수행하지 않았다.**

## 3. 모의 PDF·RemainingRequirements·UX 세부 결과

- `mock_2026_complete`: 43/43 연결, 131학점, 별도 테스트용 학생 증빙을 더한 경우 `ELIGIBLE_PDF`.
- `mock_2026_partial`: 28/28 연결, 74학점, `NOT_ELIGIBLE_PDF`.
- `mock_2026_boundary`: 42/42 연결, 131학점이나 0학점 필수 1과목 누락으로 `NOT_ELIGIBLE_PDF`; `CDA0034` 추가 가정 시 필수요건 충족 및 `ELIGIBLE_PDF`, 원본 불변.
- `mock_2026_missing_info`: 43행 중 42행 연결, 확정 총학점 미정, `UNKNOWN`/`NEEDS_INFORMATION`.
- 네 PDF **단독** 입력은 학생별 적용·전체 기록·논문·인증 증빙을 확정하지 못하므로 모두 `UNKNOWN`이다. 완전한 합성 판정은 명시적인 테스트 증빙을 추가한 경우에만 성립한다.
- 10개 학생 상태에서 총학점·전공/교양·전필 진행과 후보를 검증했다. `year4_late`는 18개 적용 요건 SATISFIED, `required_missing`은 총학점 충족에도 필수 1개 누락, `credit_or_general_short`는 총/교양 각각 2학점 부족이다. 학생용 기본 답변은 후보 이름 수백 개 대신 요건별 수를 표시했고, 과목의 이유는 `SATISFIES` 관계·Rule ID·PDF 링크로 추적된다. 후보는 졸업요건상 후보이며 개설·선수과목·시간표 정보가 아니다.

## 4. 알려진 SKIP과 Extended Scope 제한

- 독립 문항 `CTX_04` **SKIP**: 누락된 학기의 공식 기록이 없어 특정 필수과목 미이수를 확정할 수 없다. 기대값을 낮추거나 과목을 임의로 채우지 않았다.
- 과거 적용연도의 전체 과목표·경과조치, 공식 동일/대체 지정 쌍, PDF 내부 `GEA8617` 충돌, 다전공 학생별 요건, HWP 양성 경로, 실제 학생 증빙 진위는 Core 판정 범위 밖 또는 외부 공식 자료가 필요한 `BLOCKED` 항목이다. 다른 학과 전수 구조화와 전체 제품 최종 검수도 미완료다.
- 전체 승인 요청서 평가와 평가 후 일반화 검증은 **미시작**이다. `PLAN.md`의 4·10단계 `IN PROGRESS`, 9·11단계 `BLOCKED` 상태를 Core baseline만으로 변경하지 않는다.

## 5. 고정 경계

활성 RuleSet v1 스냅샷과 공식 교육과정 원문 해시, 재현 가능한 합성 fixture, 테스트 및 결과 파일을 Git 체크포인트로 함께 보존한다. `evaluation/reference/`의 승인 요청서와 `logs/private/`의 실제 학생 업로드 상태는 Git에서 제외한다. 승인 요청서의 질문·정답·별칭·규칙을 이 baseline의 런타임이나 테스트에 사용하지 않았다.
