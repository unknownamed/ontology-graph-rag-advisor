# Core Prototype v2 시연 기준 고정

검수일: 2026-09-30. **Quality Gate: PASS — 명시된 Core의 시연 기준 버전**. 전체 제품 완료와 Extended Scope 해소를 의미하지 않는다.

## 고정된 기준

- 문서 집합: `ADS-CE-2026-CORE v1`, 유일한 공식 문서 `CURRICULUM-2026`.
- RuleSet: `CRS-CE-2026-CORE v2`, 상태 `VERIFIED_FOR_CORE_SCOPE`.
- 스냅샷: `data/processed/ruleset_versions/ruleset-v2-1f9b890b4a432216.json`.
- SHA-256: `1f9b890b4a43221657862de9f05d20ed8ce13a2e1ec8490aed9aa932beb4730b`.
- 공식 PDF SHA-256: `0d800318dc367a89518f9be6be8f559092474bf00b3573e14bd37b6c44b54471`.
- 실행 규칙 19개·VERIFIED 정책 사실 11개·편성행 323개. 이번 작업에서 규칙·카탈로그·활성 포인터는 변경하지 않았다. v1 기록도 보존한다.

## Builder: UI·문서 검수와 수정

기존 서버가 허용하는 학생 없는 과목/정책 조회를 UI에서 차단하던 문제를 수정했다. 빈 상태에서 학생 객체를 만들어 보내지 않으며, 개인 판정에는 한국어로 실제 학생 입력을 안내한다. `null`·배열 등 비객체 JSON도 서버 연결 오류로 오인하지 않고 입력 오류로 차단한다. 기존 정책 계산·적용 결과를 근거 패널에 표시하고 SVG 간선에 반환된 관계 ID를 연결했다. CLI 데모가 최초 v1 빌더를 호출하던 문제는 활성 스냅샷을 읽도록 수정했다. Rule Engine과 자연어 해석의 지원 범위는 변경하지 않았다.

README의 과거 191개 결과와 현재 215개 결과를 구분하고 Architecture의 활성 v2·결정적 해석 우선·규칙 계산·표시 투영 구조를 동기화했다. [데모 안내](../../docs/demo/core_v2_demo.md)에는 실제 실행한 10개 시나리오와 합성 입력 위치를 명시했다.

## Reviewer: 실제 UI와 반례

별도 데모 탭에서 D01–D10을 직접 입력하고 각 답변의 펼쳐보기를 열었다. 과목·정책 조회, 초기 미충족, 남은 요건, 교양/전공 후보, 총학점 충족+0학점 필수 누락, 추가 이수 가정, 모든 증빙 충족, 실제 파일 선택·추출·정규화·정보 부족을 검수했다. **10/10 PASS**다. 274개 교양 후보의 전체 행·관계가 반환값과 같고, 목록은 379px 내부 스크롤로 제한된다. 기본 답변은 후보 개수만 보여주며 임의 순위가 없다.

추가 UI 반례 **4/4 PASS**: 빈 상태의 개인 판정은 안내·허위 판정 없음, 잘못된 JSON(구문 오류 및 `null`)은 실행 차단, 정책/개인 의미가 모호한 질문은 학생 상태 안내로 안전 종료, 0학점 가정 재실행은 원본 불변. 모호 정책 질문의 거부를 완전 자연어 처리 성공으로 계산하지 않았다. 정책임을 명시해야 하는 기존 제한은 Core 범위 문서에 남겼다.

같은 채팅의 남은 요건→`CDA0143` 가정→현재 졸업 질문도 실행했다. 가정 총학점 7→10·전공 +3을 보이고, 이후 실제 질문은 다시 7학점·3개 이수기록으로 계산됐다. 좁은 인앱 화면과 1280×900 데스크톱 레이아웃을 시각 확인했다. 기본 답변은 요약을 유지하며 긴 관계/후보는 펼쳐보기와 내부 스크롤로 확인한다.

## Verifier: 화면과 실행의 일치

[API 기록](core_v2_demo_api_results.json)은 실제 `/api/query` 응답의 결정·실행 ID를 보존한다. [브라우저 기록](core_v2_demo_ui_results.json)은 화면의 한국어 답변, 문서집합/RuleSet, 요건 관찰/요구값, 실행 이벤트, SVG 노드·간선 ID, PDF 링크 페이지, 학생 상태 불변을 독립 API 응답과 비교한 결과다. D01–D09 모두 일치했다. D10은 적용 정보 미확인으로 그래프·규칙 계산 전에 종료하므로 실제로 없는 노드·간선·PDF 근거를 표시하지 않는 것을 확인했다.

모의 PDF 2쪽에서 후보 43건·사용 가능 42건·확인 필요 1건을 생성했다. 실제 브라우저 정규화 StudentState는 API 결과와 일치하고 `PARTIAL / UNVERIFIED`를 유지했다. 완전 합성 상태에서만 적용 요건 18개 SATISFIED·1개 NOT_APPLICABLE로 졸업 가능이 나왔다. 합성 증빙은 실제 학생의 승인 증빙이 아니다.

## 재검증 결과

| 검사 | 실제 결과 |
| --- | --- |
| 전체 `unittest discover -s tests -q` | 215/215 PASS |
| 활성 v2 CLI Core 데모 | 5/5 PASS |
| 학생용 `/api/query` | 100/100, Reviewer 4/4 PASS |
| 독립 50문항 | 49 PASS / 0 FAIL / 1 SKIP |
| 모의 PDF 업로드 HTTP E2E | 4/4 PASS |
| 실제 브라우저 시나리오 | 10/10, 추가 안전 처리 반례 4/4 PASS |
| LLM ON/OFF | 독립 49/49·학생 상태 10/10·모의 PDF 4/4 핵심값 일치 |
| UI JS 문법 / Git diff / 공개 자료 경계 | PASS |

`./scripts/serve.ps1 -Port 18473` 실행 후 `python scripts/verify_demo_v2_api.py --port 18473`으로 API 대조 자료를 다시 만들 수 있다. 브라우저 기록은 API 스크립트가 자동으로 PASS 처리하지 않는다. 다른 재검증 명령은 `python scripts/verify_remaining_ux_2026.py`, `python scripts/verify_mock_2026_pdf_e2e.py`, `python scripts/evaluate_independent_scenarios.py --port 18473`, `./scripts/demo_core.ps1`이다. 현재 PC에서는 WindowsApps 별칭 대신 번들 Python을 사용했다. OCR 라이브러리의 deprecation 경고는 있었으며 테스트 실패는 없었다.

## 범위와 남은 사항

현재 Core는 2026 컴퓨터공학과 국내 일반 학생 단일전공이다. 과거 전체 RuleSet·타 학과·다전공 개인 판정, 공식 동일/대체 지정, 승인·운영 증빙, 개설·선수과목·시간표, `GEA8617` 충돌, HWP 양성 전체 경로는 [Extended/B/C 제한](../../docs/design/core_scope.md)을 유지한다. 독립 평가 `CTX_04` SKIP은 누락 학기의 필수 미이수를 확정할 증거가 없기 때문이다.

이번 작업에서는 승인 요청서 내용을 다시 읽거나 재평가하지 않았다. 승인 요청서 QA·파생 결과와 실제 학생 자료는 공개 커밋에서 제외한다. 공식 문서집합·v2 스냅샷·런타임에는 합성 fixture를 적재하지 않는다. 개인정보 세션을 데모 입력으로 바꾸지 않는다.
