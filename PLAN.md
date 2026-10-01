# 프로젝트 계획

## 공식 원문 → 실제 답변 누락·미활용 감사 (2026-10-01)

- **상태: DONE / 감사 산출물 Quality Gate PASS.** `docs/design/source_to_answer_coverage.md`에 원문·구조화·실제 그래프·API·자연어·답변/UI·근거·테스트의 연결을 44개 정보 단위로 기록했다. **전체 PDF 활용 완료로 판정하지 않는다.** 편성 보강의 현재 동작은 유지하며 코드·공식 데이터·ADS v1·CRS v3·v1/v2 스냅샷·테스트는 변경하지 않았다.
- **Builder:** 현재 HEAD `bcdd8de`와 활성 v3, 공식 PDF만 조사했다. 원문 이미지 26쪽(공통13·14·23, 교양33·34·35·41·42·45, CE259–264, 다전공476–477, 졸업565·567·569–572·574–575·577)을 직접 대조하고 대표 질문43개를 실제 `/api/query`로 실행했다. 실제 학생 자료·사용자 탭·평가 승인 요청서를 사용하지 않았다.
- **Reviewer:** 기존 PASS와 별개로 합성 반례4개를 실행했다. 영어 면제2학점을 다른 교양2로 보충해 총교양34를 충족해도 기초교양9 고정 Rule이 2학점 부족을 반환하는 **실제 판정 결함**을 확인했다. 동일·대체 검토 guard가 내부 안전 확인과 새 학생 의무를 혼동할 위험, 계약 밖 초과학제/장애 조건을 무시하는 위험도 구별했다. “2022 교육과정 적용자” 표현의 연도 누락으로 2026 수치를 반환하는 정책 오답을 재현했다. 같은 작업자의 역할별 검토이며 외부 독립 검수로 주장하지 않는다.
- **Verifier:** 활성323개 과목/편성/분류의 실제 SQLite 투영 일치, 실제 payload37개 내부 provenance 검증 통과, 전체 회귀 **250/250 PASS(26.218초)**를 확인했다. 총47 HTTP 호출 중45개200·2개400이며 HTTP 성공은 의미 정확성 PASS가 아니다. UI는 현재 표시 코드와 payload를 대조했으며 이번에는 브라우저 E2E·LLM ON을 재실행하지 않았다. 실행 기록은 Git 제외 `logs/source_coverage/`에 남겼다.
- **감사에서 확인한 미연결:** 영어 면제 시험기준/보충 예외, 인증 필수·선택 및 면제/세부 기준, 재입학·경과조치 세부, 표의 시수·기간·영문명·능력, 권장 학기·학점배분, 저장된 확대교양 영역의 학생 조회, 원격수업 신청 제한 등. GEA8617은 이름/분류 충돌을 유지해야 하지만 기존 충돌 설명의 “42쪽2학점”은 원문3학점과 불일치한다. 원문에 있는 미구현 조건과 추가 자료 부족을 나눴다.
- **정확성 Gate:** 기존 정상 경로 회귀 PASS는 유지한다. 다만 **Core 영어면제 조합은 수정 전 PASS로 재확정할 수 없고**, 모든 PDF 조건 확인/활용 완료도 미충족이다. 이번 커밋은 감사 결과만 반영하며 결함 수정 완료를 주장하지 않는다.

| 후속 후보 | 상태 | 우선순위·근거 |
| --- | --- | --- |
| 영어 면제+다른교양 보충의 Rule 예외, 연도 미해결 수치 차단, 미모델링 적용조건/coverage 경계 | TODO | P1; 감사 F01·F03·F04, 실제 판정/정책 오답 |
| 졸업인증·논문 세부 기준/면제와 공식 승인 입력 분리, 동일과목 검토 guard의 학생 의무 오해 방지 | TODO | P1/P2; F02·F04·F10, 현재 PDF에 이미 있는 조건 |
| 교양 영역·권장 학기·표 속성·경과조치/수강정책의 직접 질의 접근, GEA8617 충돌 설명 오기 정정 | TODO | P2; F05–F11, 저장 미활용과 데이터 누락을 구별 |
| 남은 보조 문서의 활성 v2 표현 동기화 | TODO | P3; 실제 활성 v3, 이번에는 감사 문서/PLAN만 변경 |
| 실제 개설/수강편람, 공식 동일·대체 지정/학생 승인, 과거 전체 과목표, 인증 운영·공시 인정 목록, 원문 충돌/미설명 기호 확인 | BLOCKED | 감사 §8; 추가 공식 자료/확인 필요. PDF에 이미 있는 조건까지 이 사유로 보류하지 않음 |

이번 요청은 감사 확정까지이며 위 후속 기능을 자동 구현하지 않는다. 아래 과거 완료 기록은 당시 검증 범위로 유지한다.

## 교육과정 편성정보 활용 보강 (2026-10-01)

- **상태: DONE / Scoped Quality Gate PASS.** 교육과정상 편성 학년·학기를 일반 과목 조회·학년/학기별 목록·미이수 필수 교집합·후보 묶음·답변/UI에 연결했다. 실제 개설과 개인 수강 가능은 NOT_VERIFIED로 유지하며 편성 학년을 수강 제한으로 쓰지 않는다.
- **Builder:** 원문 `grade_term` 보존·쌍 정규화, 허용된 PLACEMENT_LOOKUP, 분류/학기 필터와 별도 placement_view, CandidateCourse 출처/확인 상태를 구현했다. 교양 편성표의 누락된 학기 셀 280개를 검토하고 불변 CRS-CE-2026-CORE v3에 보강했다. ADS v1·19개 Rule·요구값·기존 과목 사실·v1/v2 스냅샷은 유지한다.
- **Reviewer:** 신규 33개 테스트 중 15개 반례로 원문 공란·교양 학년 미기재·쌍 확대·미검증 승격·타 학과/연도·분류 혼합·근거 변조·migration 제한·과거 학생 일반 조회를 확인했다. 초기 정책/집계 의도 회귀와 큰 그래프 표시를 수정했다. 새 테스트의 편성 수/기여 후보 수 혼동은 PDF의 이미 이수한 행과 0학점 선택 행으로 재확인해 수정했으며 요구사항·기존 기대값을 낮추지 않았다. 같은 작업자의 역할별 검토이며 독립 외부 검수로 주장하지 않는다.
- **Verifier:** 공식 PDF 262–264 및 34–45 전 페이지를 렌더링 대조했다. 학생 자료 없는 질문과 공개 합성 학생의 별도 브라우저에서 답변·편성·후보·SATISFIES·Rule·SVG·PDF·trace를 확인했다. 실제 학생 탭·자료와 평가 승인 요청서를 사용하지 않았다.
- **검증:** 전체 회귀 250/250, 편성 HTTP/경계 테스트 33/33, 실제 API 편성 질문 10/10 및 LLM ON/OFF·반복·원본 보존·provenance 일치, 브라우저 기록 6/6, 학생용 API 100/100·반례 4/4, 모의 PDF E2E 4/4, 독립 49 PASS·0 FAIL·1 SKIP. 실행: `python -m unittest discover -s tests -q`, `python scripts/verify_curriculum_placement.py --port 18575`.
- **남은 제한:** 교양 편성 학년은 원문 미기재(MISSING); `이룸` 3셀은 학기 의미 UNVERIFIED; GEA8617 코드 충돌 유지. 실제 개설·선수조건·개인 수강 가능과 기존 Extended Scope/CTX_04는 보류한다. 편성정보 부족을 새 졸업 불가 조건으로 추가하지 않는다. 기존 18473 서버는 학생 세션 보호를 위해 자동 재시작하지 않았으며 새 테스트 서버 18575는 v3다.
- **기록:** `docs/design/curriculum_placement.md`, `evaluation/results/curriculum_placement_acceptance.md`, 편성 API/UI 검증 JSON. README·현재 계약·아키텍처를 활성 v3로 동기화했다. 아래 기존 단계/과거 완료 기록의 범위와 제한은 유지한다.

상태는 `TODO`, `IN PROGRESS`, `DONE`, `BLOCKED` 중 하나로 기록합니다. 단계 착수 시 `IN PROGRESS`, 구현과 검증 완료 시 `DONE`으로 바꾸고, 막히면 `BLOCKED`와 사유를 기록합니다.

| 단계 | 작업 | 상태 |
| ---: | --- | --- |
| 0 | 프로젝트 및 실행 환경 확인 | DONE |
| 1 | 교육과정 PDF 분석과 규칙 인벤토리 작성 | DONE |
| 2 | 온톨로지와 데이터 계약 설계 | DONE |
| 3 | 가장 작은 end-to-end 판정 기능 구현 | DONE |
| 4 | 전체 규칙군 확장 | IN PROGRESS |
| 5 | 자연어 질문 해석 연결 | DONE |
| 6 | 로컬 LLM 연결 | DONE |
| 7 | 실제 실행 근거 및 provenance 기록 | DONE |
| 8 | 채팅 UI와 관계 그래프 표시 | DONE |
| 9 | 이미지/PDF/HWP/DOCX 업로드 연결 | BLOCKED |
| 10 | 평가·회귀·일반화 검증 | IN PROGRESS |
| 11 | 로컬 통합 실행 및 최종 검수 | BLOCKED |

## 현재 시연 기준: Core Prototype v2 (2026-09-30)

- **DONE / Quality Gate PASS:** `ADS-CE-2026-CORE v1 / CRS-CE-2026-CORE v2`를 현재 구현의 발표·시연 기준으로 고정했다. 공식 PDF·RuleSet 스냅샷·19개 Rule·323개 편성행은 변경하지 않았다. 전체 제품의 4·10단계 IN PROGRESS, 9·11단계 BLOCKED는 Extended Scope 기준으로 유지한다.
- **Builder:** 빈 학생 상태의 기존 과목/정책 조회를 UI에서 허용하고 개인 판정에는 한국어 입력 안내를 표시했다. 기존 정책 계산·적용 결과와 실제 관계 ID를 펼쳐보기에 연결했다. CLI 데모가 최초 v1을 새로 빌드하던 문제를 활성 스냅샷 조회로 수정했다. README·Architecture·지원 범위를 v2에 동기화하고 `docs/demo/core_v2_demo.md`에 10개 공개 합성 시나리오를 작성했다.
- **Reviewer:** 별도 브라우저 탭에서 10개 질문·후보 펼쳐보기·simulation·모의 PDF 실제 파일 선택→43후보→정규화→질문을 수행했다. 빈 입력·잘못된 JSON·모호한 정책/개인 표현·반복 가정 반례 4개를 검사했다. 정책 의미를 명시해야 하는 기존 표현 제한은 해결됐다고 주장하지 않고 범위 문서에 남겼다. 같은 채팅의 남은 요건→3학점 가정→현재 판정에서도 실제 7학점·3기록은 보존됐다.
- **Verifier:** 화면 답변·v2·Rule 관찰/요구값·실행 이벤트·그래프 노드/간선·PDF 페이지가 실제 API 결과와 일치했다. D10은 적용 정보 미확인으로 조회 전 종료해 허위 관계/출처를 표시하지 않았다. 274개 후보 전부의 학점·SATISFIES가 일치했다. 실제 학생 자료·평가 QA는 데모·공개 파일에 포함하지 않았다.
- **재검증:** 전체 회귀 215/215, 학생용 API 100/100 및 Reviewer 4/4, 독립 49 PASS / 0 FAIL / 1 SKIP, 모의 PDF E2E 4/4, 브라우저 10/10 및 UI 반례 4/4, 활성 v2 CLI 5/5 PASS. LLM ON/OFF 핵심값은 독립 49/49·상태 10/10·모의 PDF 4/4 일치했다. UI JS 문법·Git diff·공개 경계 검사 PASS.
- **기록:** `evaluation/results/core_v2_demo_baseline.md`, API/브라우저 JSON 두 파일. API 준비 스크립트는 실제 브라우저 검증을 자동 PASS 처리하지 않는다. Extended 구현·B 공식 자료 대기·C 사람 검토는 `docs/design/core_scope.md`에 유지한다.

## 0단계 확인 기록 (2026-09-29)

- 기준 자료 `docs/curriculum/2026년도 교육과정.pdf` 존재 확인. PDF를 정상적으로 열었고 `pdfinfo`와 `pdfplumber`에서 모두 615쪽으로 확인했다.
- 표본 페이지 5, 20, 50, 100, 300, 615에서 본문 텍스트가 추출됐다. 20, 50, 100, 300, 615쪽에서는 표 구조와 셀이 추출됐고, 20쪽은 이미지 렌더링으로 표의 판독 가능성을 확인했다.
- 표본 페이지 1, 2, 10의 텍스트 추출량은 0이었다. 해당 페이지의 상태나 원인은 아직 확인하지 않았다. 전체 615쪽의 개별 추출 품질도 미검증이다.
- 평가 자료 `evaluation/reference/교육과정 규칙 검증 승인 요청서.pdf`가 평가 전용 폴더에 존재함을 확인했다. 파일 내부의 질문·정답, 페이지 수, 추출 가능 여부는 확인하지 않았다.
- PDF 점검에는 현재 사용 가능한 `pdfinfo`, `pdftoppm`, 번들 Python의 `pdfplumber`를 사용했다. 애플리케이션 실행 환경과 로컬 LLM 동작은 아직 확인하지 않았다.

### 실행 환경 추가 확인

- Windows 11, RAM 약 63.8GB, NVIDIA RTX 4070 Ti VRAM 12,282MiB를 실제 명령으로 확인했다. Node 24.19, npm 11.17, 번들 Python 3.12.14를 확인했다. Ollama 설치 및 `qwen3:8b` 등 보유 모델 목록을 확인했으나 모델 추론 성능은 6단계에서 별도 검증한다. Docker CLI는 있으나 엔진이 실행 중이지 않았다.
- 미추적 `docs/PROJECT_REQUIREMENTS.md.md`의 내용이 제품 요구사항임을 확인하고 `docs/PROJECT_REQUIREMENTS.md`로 경로를 바로잡았다. 원문 PDF와 평가 PDF는 변경하지 않았다. SQLite 속성 그래프와 표준 라이브러리 Python을 초기 스택으로 택했다. 그래프 사실·관계 조회와 결정적 규칙 계산을 분리하고 Docker 서비스 의존성을 피하기 위한 선택이다.
- **Quality Gate: PASS.** 프로젝트 파일·Git 상태·PDF 구획·실행 환경을 확인했다. 로컬 LLM의 추론 품질·지연·VRAM은 아직 6단계 과제다.

## 3단계 구현 및 검증 (2026-09-29)

- **Builder:** 원문 대조가 끝난 `computer_engineering_scope.md`의 43개 과목을 `source_index.json` 43행과 PDF SHA-256으로 검증해 `computer_engineering_2026.json`으로 생성했다. 실제 SQLite 속성 그래프에 학과·교육과정·과목·편성행·교육과정별 이수구분·요건 노드와 관계를 적재했다. 허용된 그래프 조회, 학생 이수 인정, 전필/전선/전공 학점 합산, 0학점 필수과목, 추가 이수 가정, 상태·출처·실행 기록을 구현했다. `scripts/run.ps1` 실실행에서 원본 확정 하한 3학점과 가정 후 6학점이 별도로 나왔다.
- **Reviewer:** 다른 시도 ID의 동일과목 재수강, 동일 시도 ID의 충돌 기록, 학생 학점과 편성표 학점 불일치, 원문 미검증 행, 적용연도 차이, 0학점 필수, 부분 성적표를 반례로 검사했다. 검토 중 시나리오가 원본 판정 해시를 바꾸던 문제와 미검증 편성행 산입 문제를 수정하고 재검증했다.
- **Verifier:** PDF 해시 일치, 262–263쪽의 43개 과목코드 텍스트 존재, 43행/144학점/전필 9행·21학점/부전공 ※ 3행, 그래프 반환 관계와 `EvidenceBundle`·규칙 결과·판정·`AnswerPayload`·실제 `ExecutionTrace`의 연결을 검증했다. 존재하지 않는 관계를 근거에 삽입하면 출력 검증기가 거부한다.
- **검증 명령/결과:** `python scripts/build_catalog.py` 통과, `python -m unittest discover -s tests -q` **24 tests OK**, `./scripts/run.ps1 ./tests/fixtures/structured_request.json` 실행 성공. 평가 PDF는 열지 않았다.
- **Quality Gate: PASS, 3단계 DONE.** LLM 없이 동일 구조화 입력에 결정적 결과가 나오고, 근거는 PDF 표 행과 실제 학생 입력 및 실행된 관계·규칙까지 연결된다. 현재 적재 범위는 2026 컴퓨터공학과 일부 전공 요건뿐이다. 전체 졸업요건, 과거 적용자, 공식 동일·대체 지정, 제2전공, 교양·논문·인증은 미완료로 남겨 `ELIGIBLE_PDF`를 금지한다. 다음은 4단계에서 검증된 공통 규칙군을 확장한다.

## 4–9단계 구현·검증 진행 (2026-09-29)

- **4단계 IN PROGRESS:** 교육과정 PDF 34–45쪽의 교양 후보 282행을 추출했고, 26행만 원문 페이지와 육안 대조해 `general_education_2026.json`에 VERIFIED로 적재했다. PDF 42·45쪽에서 동일 코드 `GEA8617`의 상충 행을 발견해 CONFLICTED로 격리했다. 2026 컴퓨터공학과 단일전공의 교양, 전공, 졸업 총 130학점, 교양 42학점 산입 상한, 전필, 논문·인증 증빙을 결정적 규칙으로 계산한다. 완전한 합성 학생 상태에서 `ELIGIBLE_PDF`, 127학점에서 미충족, 필수 증빙 누락에서 확인 필요를 재현했다. 나머지 교양·과거 연도·다전공·공식 대체 목록은 여전히 미확인이다.
- **5단계 DONE:** 한국어 과목명·`고자구` 약칭·오타·띄어쓰기·구어체·직전 과목 대명사·복합 졸업 질문을 검증된 ID와 허용 의도로 연결한다. 여러 후보가 남으면 모호성을 반환한다. Reviewer 반례로 존재하지 않는 과목과 중의적 이름을 검사했다. 현재 어휘 범위는 검증된 컴퓨터공학과/교양 과목이다.
- **6단계 IN PROGRESS:** 실제 RTX 4070 Ti 12,282MiB, RAM 약 63.8GB, Windows 11, Ollama 0.34.2, `qwen3:8b`를 확인했다. 로컬 JSON 의도 제안을 실행했고 4개 대표 질문의 원시 의도 3개 정답을 측정했다. 모델의 과목·의도는 결정적 해석과 원문 표현으로 검증하고 불일치 시 차단한다. 서버 소유 정형 답변은 구현됐으나 로컬 모델의 검증된 결과 표현과 더 넓은 한국어 정확도·지연 검증이 남았다.
- **7단계 DONE:** 실제 조회·제외·규칙 계산·판정 이벤트로 `ExecutionTrace`를 생성하고 관계 ID·사실 ID·PDF 위치·학생 증거와 결과를 교차 검증한다. 반환되지 않은 관계를 삽입하는 반례와 SQLite 관계 누락 재개방 반례를 추가했다. DB 내부 물리 탐색 순서는 표시하지 않는다.
- **8단계 DONE:** `./scripts/serve.ps1 -Port 18473`으로 로컬 채팅 UI/API를 실행하고 한국어 질문, 실제 관계 SVG, 규칙·계산·실행 순서, PDF 262쪽 링크를 브라우저에서 확인했다. 표시 그래프는 반환된 관계 중 판정에 사용된 ID만 그린다. 프론트 JavaScript 구문 검사 통과. 화면의 디자인 완성도보다 근거 일치 검증을 우선했다.
- **9단계 IN PROGRESS:** PDF 텍스트·DOCX 표·HWP 5 텍스트·PNG 이미지·스캔 PDF의 실제 파싱을 확인했다. EasyOCR 한국어 로컬 모델로 합성 이미지의 `CDA0143`을 추출했고 OCR 점수 0.616을 기록했다. 모든 파일 추출 결과는 `UNVERIFIED`/완료 여부 `UNKNOWN` 후보이며, UI에서 사용자가 코드·완료·취득학점을 확인해야 상태에 반영된다. 업로드 API와 후보 확인 화면을 구현하고 API·파서 테스트를 통과했으나 브라우저의 실제 파일 선택→확인→질문 전체 조작은 아직 검증하지 못했다. HWP 양성 시험은 공개 HWP 5 샘플의 텍스트 추출까지만 확인했다.
- **공통 Builder→Reviewer→Verifier→Gate:** `python -m unittest discover -s tests -q` **70 tests OK**, `node --check logs/ui-check.js` 통과, `/api/extract`에서 실제 HWP/PNG 후보 응답 확인. 원문 PDF 해시와 2026 CE 43행 및 육안 대조 GE 26행을 사용했다. Reviewer의 추가 반례는 미확인 과목, 파일 속 완료 문구, 조작된 그래프 관계, 잘못된 학생 레코드, 이미지 OCR 오탐 위험이다. 출처 없는 업로드 후보를 VERIFIED로 자동 승격하지 않는다. 4·6·9단계는 남은 항목 때문에 PASS 처리하지 않는다. 평가 전용 PDF의 내용은 이 기록 시점까지 열지 않았다.

## 4·10·11단계 추가 검증 (2026-09-29)

- **Builder:** 교육과정 PDF 13–14, 261, 264쪽에서 확인한 적용연도·자유선택 잔여학점·동일/대체·권장·경과조치 사실을 `PolicyFact`로 적재하고, `POLICY_LOOKUP` 의도에서 실제 `Requirement`/`PolicyFact` 그래프 조회와 PDF 출처를 반환한다. 학생 개인 학점 질의는 기존 규칙 엔진으로 처리한다. PDF 13쪽의 자유선택 범주에 속하는 **공식 인정 증빙을 구조화 입력으로 받은** 다른 학과 과목은 졸업 총학점의 잔여학점으로만 산입한다.
- **Reviewer:** 2025학번의 졸업학점 질문에 2026의 130학점을 잘못 반환할 수 있는 반례를 발견했다. 입학연도가 2026이 아닌 정책 질문의 2026 수치 규칙을 차단하고, PDF 13쪽의 원칙과 적용연도 확인 필요를 반환하도록 수정했다. 교양/전공 편성 과목을 자유선택으로 재분류하는 입력, 자유선택 중복 코드, 미검증 인정 증빙, 업로드 OCR을 공식 증빙으로 오인하는 입력도 반례로 검사했다.
- **Verifier:** 2026 전공 43행·육안 대조 교양 26행, 원문 PDF SHA-256, 정책 사실의 PDF 13–14·261·264쪽 색인, 실제 `FETCH_POLICY_FACTS`/`FETCH_REQUIREMENTS` 반환 ID와 EvidenceBundle·ExecutionTrace·AnswerPayload의 연결을 확인했다. 과목 인정 실행 이벤트가 학생 증빙·원문 사실·반환 관계 ID를 모두 기록하는지도 검증하고 누락 반례를 추가했다. `GEA8617`의 PDF 내부 충돌은 CONFLICTED를 유지한다. 평가 전용 스크립트와 자료는 런타임 빌더/그래프/규칙/프롬프트에서 참조하지 않는다.
- **검증 명령/결과:** `python scripts/build_catalog.py`에서 **69개 출처 연결 과목 행** 생성, `python -m unittest discover -s tests -q` **89 tests OK**. 2025학번 정책 질의를 로컬 API와 채팅 화면에서 실행해 2026 수치가 표시되지 않음을 확인했다. 평가 전용 문항과 정답은 공개 기록에서 제외한다.
- **Quality Gate:** 정책 조회와 공식 증빙 자유선택 계산의 해당 기능 단위는 PASS. 4단계 전체는 과거 연도·다전공·공식 대체 목록·남은 교양 과목표 때문에 IN PROGRESS. 6단계는 로컬 모델의 검증된 결과 표현과 폭넓은 한국어 성능 검사가 남아 IN PROGRESS. 9단계는 브라우저 파일 선택부터 질문까지 수동 통합 검증이 남아 IN PROGRESS. 10단계는 세부 평가 및 후속 일반화 검증이 남아 IN PROGRESS. 11단계는 로컬 서버 실행이 확인됐으나 최종 검수 전이라 IN PROGRESS.
- **로컬 모델 재측정:** `python scripts/benchmark_local_llm.py`로 평가 문항과 다른 한국어 8문장을 검사했다. 첫 실행에서 “전공필수 중에 남은 과목”을 원문 규칙 조회로 오분류한 반례를 수정한 뒤, **8/8 허용 의도 일치**, 실제 모델 호출 7건, 재실행 중앙 지연 **0.288초**, 최대 **0.613초**를 기록했다. 첫 실행의 최대 지연은 **2.691초**였다. `ollama ps`는 `qwen3:8b` 5.6GB, GPU 100% 적재를 표시했다. 이 소규모 검사는 모델의 전체 한국어·오타 정확도를 뜻하지 않는다. 수정 후 전체 자동 테스트는 **90 tests OK**다.
- **평가 범위 검토:** 평가 전용 질문·답변의 상세 내용은 비공개 평가 자료에 보관한다. 규칙 수정은 공식 교육과정 원문을 독립적으로 확인한 뒤 일반화 가능한 방식으로 수행했다.
- **답변 검증 반례:** 확정 미충족과 공식 증빙 누락이 함께 있는 합성 학생에 대해 결과가 `NOT_ELIGIBLE_PDF`인 동시에 미충족·확인 필요를 모두 표시하도록 정형 답변을 보완했다. 수정 후 `python -m unittest discover -s tests -q`는 **92 tests OK**다.
- **답변 근거 확장:** 미이수 전공필수의 과목명은 카탈로그 상수를 직접 읽지 않고 `FETCH_CATALOG_ENTRY`로 실제 조회한 뒤 기본 한국어 답변에 표시한다. 과목명·코드·PDF 출처는 `EvidenceBundle`에 들어가고 반환 관계의 실행 여부를 Verifier가 검사한다. 컴퓨터구조 미이수 반례를 추가한 전체 자동 테스트는 **94 tests OK**다.

## 1단계 진행 기록 (2026-09-29)

- 목차 PDF 3–7쪽으로 8개 장과 주요 절의 범위를 파악했다. 본문은 PDF 11–27, 31–34, 50–51, 77–82, 475–484, 547–552, 565–579, 596–597, 603–607, 612–615쪽을 목적별로 확인했다. 나머지 본문은 목차 기반 위치 색인 또는 미확인 상태다.
- `docs/design/curriculum_inventory.md`에 적용연도, 교양, 전공, 다전공, 동일·대체·중복, 졸업논문·인증 등 핵심 사실·규칙을 1차 기록했다. `data/processed/source_index.json`에는 장·절·표·규칙군과 목차상 학과/전공 구간을 넣었다.
- **당시 상태: IN PROGRESS.** 학과별 과목·경과조치 70개 구간, 연도별 학점표의 전 행, 자율전공·다전공 세부 프로그램과 별표는 아직 전수 검증하지 않았다. 외부 규정이 필요한 조건도 남아 있다.
- 표 머리와 병합 셀의 자동 추출 오류, 중복 글자 추출, 텍스트 0인 페이지가 확인됐다. 표의 수치와 각주는 원문 이미지로 다시 대조해야 한다. 승인 요청서는 열지 않았으며 온톨로지·스키마·판정 로직·그래프를 만들지 않았다.

## 1단계 완료 검증 (2026-09-29)

- 이번 단계의 완료 범위는 **대학 공통 핵심 졸업·교육과정 규칙과 컴퓨터공학과**다. 전체 70개 학과의 전수 구조화는 범위 밖이다. `docs/design/computer_engineering_scope.md`에 원문 규칙 CE-01–CE-13, 2026 전공 과목 43행, 연도별 학점·경과조치, 미확인 조건을 기록하고 기존 인벤토리를 CI-034까지 보강했다. `data/processed/source_index.json`에는 컴퓨터공학과 출처 위치 18개와 과목 행 위치 43개를 추가했다.
- 실제 대조한 핵심 PDF 페이지: **13–14, 23, 33–34, 259–264, 476–477, 481, 565, 567, 569–570, 572, 575, 577, 591, 593, 602, 605, 610–611, 613–615**. 607–608은 2009년 이전 참조 문구와 2010–2012 표에 컴퓨터공학과 독립 행이 없는지를 텍스트로 확인했다. 모든 본문 페이지를 전수 열람한 것은 아니다.
- 학점표의 병합 셀과 2026 컴퓨터공학과 수치(교양 34, 최소전공 45, 심화 33, 전공 계 78, 총 130), 연도별 해당 행, 학과 경과조치의 `57(35)` 각주, 0학점 전공필수 2행, 부전공 `※` 3행, 논문·인증 표의 서로 다른 `해당사항 없음`을 원문 이미지로 대조했다. 과목코드 43개가 PDF 추출 순서와 모두 일치하고, 전사 학점 합계 144·전필 유학점 합계 21·전필 9행·전선 34행이 과목표와 맞는다. 인벤토리 34개 항목의 필수 필드와 JSON 파싱·ID 중복도 확인했다.
- **완료 판단: DONE.** 이번 범위의 핵심 과목·공통 규칙·적용 교육과정/다전공 선발연도·출처 페이지·추출 오류 가능 값의 원문 대조 조건을 충족했다. 2단계는 `IN PROGRESS`로 전환하되 이번 작업에서 온톨로지 스키마나 그래프는 설계·구현하지 않았다.
- 남은 `UNVERIFIED`: 과거 교육과정의 개별 필수 과목표, 2002–2005 총 졸업학점, 2010–2012 컴퓨터공학과 독립 복수전공 표 행, 공식 동일/대체 지정 목록, 학생별 적용연도·학적·이수·논문·인증 증빙, 외부 운영지침의 세부사항. 이 값이 없으면 해당 학생의 전체 졸업 가능을 판정할 수 없다. 다른 학과·다전공 프로그램의 전수 값도 이후 범위에서 확인한다.
- 승인 요청서는 열거나 비교하지 않았다. 원본 PDF와 평가 자료를 변경하지 않았고, 온톨로지·Neo4j·Graph RAG·LLM 프롬프트·판정 구현은 시작하지 않았다.

## 2단계 설계 완료 검증 (2026-09-29)

- `docs/design/ontology_model.md`, `rule_model.md`, `provenance_model.md`, `data_contracts.md`, `architecture.md`를 작성했다. 근거는 교육과정 PDF와 1단계 인벤토리·컴퓨터공학과 범위·출처 색인이다. 평가 전용 승인 요청서는 열거나 분석하지 않았다.
- 교육과정 편성 사실(`CatalogEntry`)과 학생 수강/완료(`CourseAttempt`/`CompletionRecord`), 규칙으로 산출한 인정학점(`CreditRecognition`)을 분리했다. 학점 기준·개편 후 과목표·논문·인증의 적용 버전을 분리하고, 실제 상태와 `ScenarioDelta`도 분리했다.
- 결정적 규칙 IR, 검증 상태 `VERIFIED`/`UNVERIFIED`/`CONFLICTED`/`MISSING`, 판정 상태 `SATISFIED`/`UNSATISFIED`/`NEEDS_INFORMATION`/`NOT_APPLICABLE`, 규칙군 적재 범위 확인(`RuleCoverageManifest`)을 정의했다. 미확인 필수 입력은 0·면제·불충족으로 바꾸지 않는다.
- 사용자 입력부터 `AnswerPayload`까지 8개 계약과 서버 생성 allowlist `QueryPlan`을 정의했다. LLM은 질문 해석과 잠긴 판정값의 한국어 표현만 맡는다. 출처·실제 조회·규칙 계산 이벤트에서만 `ExecutionTrace`를 만들고, 답변의 수치·상태·근거는 서버가 검사한다.
- PDF로 검증된 컴퓨터공학과의 `CDA0143` 조회, 전공학점 합산, 0학점 필수를 포함한 필수과목 확인, `CDA0163` 추가 이수 시나리오를 **실제 학생값 없이 구조적으로** walkthrough했다. 모델은 이 네 흐름을 표현하며, 학생 기록·과거 과목표·공식 동일/대체 지정이 없을 때 정보 부족으로 남기는 것을 확인했다.
- **완료 판단: DONE.** 설계 문서 5개, JSON 예시 2개 파싱, 규칙의 출처 색인 ID, 원본 PDF SHA-256, 필수 상태·계약명·컴퓨터공학과 walkthrough 참조를 검사해 통과했다. 3단계는 `IN PROGRESS`로 전환하되 이번 작업에서 데이터베이스 적재·Neo4j 스키마 구현·Graph RAG·LLM·프론트·애플리케이션 코드는 만들지 않았다. 1단계의 `UNVERIFIED` 항목은 그대로 남는다.

## 최종 범위 재검증 및 Quality Gate (2026-09-29)

- **Builder — 교육과정 데이터/규칙:** PDF 34–45쪽 이미지와 추출 행을 대조해 중복 없는 교양 280행을 출처 연결 상태로 적재했다. 42쪽 `GEA8617`은 자동 표 추출의 3학점과 달리 원문에서 **2학점**이며, 45쪽 같은 코드는 다른 이름·영역·3학점이므로 두 행을 충돌 목록에 남겨 자동 적재에서 제외했다. 전공 43행과 합쳐 323행이다. PDF 591·593·602·605쪽의 컴퓨터공학과 2006–2025 단일전공 학점표는 연도별 `PolicyFact`로 조회하고, PDF 264쪽 경과조치와 476–477쪽 복수전공·부전공 정책 사실의 적용 대상을 구분했다. 이는 과거 학생의 과목별 이수 판정이나 제2전공 전체 판정과 다르다.
- **Reviewer:** 확대교양을 균형교양의 4영역 이수로 잘못 인정할 수 있는 반례, 유학생 전용 과목, `GEA8617`, 2025학번의 2026 수치 상속, 복수전공 주전공에 단일전공 78학점 적용, 동일과목 재수강을 별도로 검사했다. 확대교양 적재 후 `GENERAL_EXPANDED` 집계 키 누락으로 2개 테스트가 실패했고, 집계 항목을 수정해 재실행했다. 공식 동일·대체 **지정 쌍**과 과거 개별 과목표는 확보하지 못했으므로 자동 인정하지 않는다.
- **Verifier:** 원본 PDF SHA-256 및 교양 280개 코드의 인용 PDF 페이지 존재, 출처 색인, 과목/규칙 그래프 반환 ID와 `EvidenceBundle`·`RequirementResult`·`DeterministicDecision`·`ExecutionTrace`의 연결을 검사했다. 브라우저에서 합성 PDF를 실제 파일 선택→후보 1건 추출→사용자 확인→질문→6학점 하한 판정까지 실행했다. 같은 학생 상태의 독립 API 재실행은 결정 ID `DEC-9652fdb4d4b0743d`, 관계 25개, 규칙 결과 19개, 실행 이벤트 26개를 재현했고 브라우저의 그래프 25간선·26노드, 규칙 19행·실행 26행, PDF 링크 페이지 23·33·34·261·262·565·569·577과 대조했다. 모델 켜기/끄기의 판정·수치·근거·trace는 같았고 실제 `qwen3:8b` 답변 말투 선택은 `VERIFIED_STYLE`이었다. DOCX도 브라우저 선택→후보 확인→동일한 6학점 하한 판정까지 실행했다. PNG는 브라우저 선택→로컬 OCR→사용자 확인→질문→3학점 하한 판정을 실행했다. 실제 HWP 5 표본은 텍스트를 읽었지만 과목코드가 없어 브라우저 후보 0건이었다.
- **검증 명령/결과:** `scripts/promote_general_education.py` 280행, `scripts/build_catalog.py` 323행, `scripts/verify_live_integration.py 18473` PASS, `python -m unittest discover -s tests -q` **112 tests OK**, 현행 HTML 스크립트 `node --check` 통과. `scripts/benchmark_local_llm.py`는 평가 문항과 다른 8개 한국어 질문 중 8/8 허용 의도 일치, 실제 모델 호출 7건 중앙 0.287초·최대 0.601초였다. `ollama ps`에서 `qwen3:8b` 5.6GB·GPU 100% 적재를 확인했다. 평가 전용 상세 문항은 공개 기록에서 제외한다.
- **Gate — 6단계 DONE:** 로컬 모델의 검증된 의도 제안과 제한된 한국어 말투 선택이 실제 실행됐고 모델 유무에 따른 핵심 판정 불변성을 확인했다. 표현 범위는 서버가 고정한 답변의 말투 선택이며 자유 생성 설명의 품질을 검증한 것은 아니다.
- **Gate — 4단계 BLOCKED:** 2026 컴퓨터공학과 단일전공/교양의 확인된 범위는 동작한다. PDF 내부 `GEA8617` 충돌, 공식 동일·대체 지정 쌍, 과거 적용자의 개별 과목 분류·필수 이수 기준, 선택된 제2전공의 전체 기준·학생 증빙은 이 작업에서 확정할 수 없다. 영향: 해당 경로의 자동 학점 인정과 전체 졸업 가능 판정 금지. 원문 정정/공식 지정 자료와 학생별 적용 증거가 확보되면 독립적으로 검증해 확장한다.
- **Gate — 9단계 BLOCKED:** PDF·DOCX·PNG는 브라우저의 파일 선택→후보 추출→사용자 확인→질문→판정 경로를 검증했다. HWP 5는 공개 표본의 텍스트 추출과 후보 0건까지만 확인했다. 과목코드가 있는 적법한 HWP 5 양성 표본 또는 작성 환경이 없어 HWP의 후보→확인→판정 경로를 PASS 처리하지 않는다. 추출 후보는 모든 형식에서 자동 이수 확정하지 않는다.
- **Gate — 10·11단계 BLOCKED / 최종 판정 FAIL:** 112개 회귀 테스트와 제한된 평가 10/10은 통과했다. 과거 적용자·다전공·공식 동일/대체와 HWP 양성 경로, 승인 요청서 전체 사례의 판정 정확도는 검증되지 않았다. 따라서 프로젝트 전체를 **“프로토타입 완료”로 판정하지 않는다.** 2026 컴퓨터공학과 단일전공의 확인된 구조화 입력·로컬 채팅·PDF/DOCX/PNG 업로드 범위만 재현 가능한 부분 프로토타입이다. 원본 교육과정 PDF와 평가 PDF는 변경하지 않았다.

## Core Prototype 최종 Quality Gate (2026-09-29)

이 구간은 직전의 전체 제품 FAIL 이후 **현재 자료로 검증 가능한 Core 범위를 별도로 판정**한 기록이다. 기존의 9·11단계 `BLOCKED`는 Extended Scope를 포함한 전체 제품 기준이며, Core의 PASS를 전체 제품 완료로 확대하지 않는다. 정확한 입력 경계는 `docs/design/core_scope.md`에 둔다.

- **Builder:** 2026 컴퓨터공학과 단일전공의 합성 완전 입력 fixture와 `scripts/demo_core.ps1`을 만들었다. 실제 엔진에서 130학점 `ELIGIBLE_PDF`, 필수 과목 1개 제거 시 127학점 `NOT_ELIGIBLE_PDF`, 부분 성적표 `UNKNOWN`, 127→130학점 가상 추가와 원본 불변, 제2전공 `UNKNOWN`을 재현했다. 수강 대상이 제한된 교양의 과목 조회 답변에 대상 조건을 표시하고, 졸업 판정 전에 적용 범위 검증 결과를 `COVERAGE_CHECK` 실행 이벤트와 구체적 정보 부족 사유로 남긴다.
- **Reviewer:** 유학생 전용·비공학 전용 과목 조회가 학생별 인정 가능성을 숨기던 문제를 수정했다. 적용 과목표가 2025인 졸업 질문에서 `COVERAGE_CHECK` 누락으로 서버 예외가 나던 조기 종료 결함을 재현·수정했다. 해당 경우는 `UNKNOWN`과 적용 교육과정 확인 필요를 반환한다. 필수 규칙 하나가 적재에서 빠져도 양성 졸업 판정이 가능했던 경로를 막았다. AI 교양·교양 상한·심화전공 규칙을 각각 제거한 반례는 모두 `UNKNOWN`과 누락 규칙 ID를 반환한다. 필수 적용 증빙과 전체 성적표 증빙을 제거한 반례, 조작된 실행 기록, 제2전공 경계도 검사했다.
- **Verifier:** 실제 PDF 해시·과목 출처 대조를 포함한 자동 테스트, SQLite 반환 관계→`EvidenceBundle`→규칙 결과→결정→답변·실행 기록 검증기를 재실행했다. 브라우저에서 합성 47과목 입력과 한국어 졸업 질문을 실행해 130학점 결론, 규칙 19건, `COVERAGE_CHECK`를 확인했다. 브라우저 SVG의 160간선·161노드는 독립 API 재실행의 사용 관계·노드 수와 같았다. PDF 23·33·34·261·262·565·569·577쪽 등 링크가 실제 근거로 표시됐다. 로컬 `qwen3:8b` 켜기/끄기의 결정·학점·근거·trace·정형 답변이 동일했고 모델 제안은 검증 후 채택됐다.
- **검증 명령/결과:** `./scripts/demo_core.ps1` 5/5 경로 PASS; `python scripts/verify_core_live.py 18473` PASS (결정 ID `DEC-77a77c68c79c6d4a`, 19개 규칙, 117개 실행 이벤트, 과거 과목표 입력 `UNKNOWN`); `python scripts/verify_live_integration.py 18473` 업로드→질문 PASS; `python -m unittest discover -s tests -q` **120 tests OK**; `node --check logs/ui-check.js` PASS. `scripts/benchmark_local_llm.py`의 평가 문항과 다른 질문 **8/8 허용 의도**, 모델 호출 7건 중앙 **0.279초**, 최대 **0.542초**. 평가 전용 상세 문항은 공개 기록에서 제외한다.
- **Quality Gate: Core Prototype PASS.** 구조화 입력이 실제로 검증된 2026 컴퓨터공학과 국내 일반 단일전공·2026 학점/과목표 적용자이고, 학적 예외가 없으며, 전체 성적표·공식 동일/대체 검토·논문·인증의 학생별 증거가 확인된 경우에 한해 PDF 기준 졸업 가능/미충족/정보 부족을 결정적으로 구분한다. 합성 fixture는 실제 학생 졸업 가능성을 입증하지 않는다.

### Extended Scope 분류와 재개 조건

| 항목 | 분류와 현재 처리 | 재개에 필요한 것 |
| --- | --- | --- |
| 다른 2026 학과와 다전공 정적 규칙 | 현재 PDF로 추가 구현 가능; 4단계 `IN PROGRESS`. 제2전공 전체 판정은 `UNKNOWN`. | 다른 학과 과목·요건 전수 구조화, 다전공 규칙 엔진과 독립 반례 |
| 과거 적용자의 과목별 판정 | 외부 공식 자료 부족으로 해당 경로 `BLOCKED`; 연도별 학점표 조회만 지원 | 해당 연도의 공식 과목표·전필·경과조치 및 학생별 적용연도 증빙 |
| 공식 동일·대체 지정 쌍 | 외부 공식 자료 부족으로 자동 인정 `BLOCKED`; 처리 원칙 조회만 지원 | 지정 목록과 학생별 인정 결과 |
| `GEA8617` 코드 충돌 | 현 PDF 내부 충돌로 자동 산입 `BLOCKED` | 발행기관의 정정 또는 학생 과목 식별 공식 증거 |
| 다전공 학생별 판정 | 학생 공식 자료 부족으로 `BLOCKED` | 제2전공 선발연도, 이수·중복 인정 기록, 적용 요건 증거 |
| HWP 5 과목 양성 경로 | 검증 표본 부족으로 9단계 전체 `BLOCKED`; 텍스트 파싱만 확인 | 과목코드 포함 적법한 HWP 5 표본 또는 재현 가능한 작성 환경 |
| 승인 요청서 전체 평가·일반화 | 외부자료 부족 아님; 10단계 `IN PROGRESS` | 전체 문항 독립 채점·오류 분석·새 반례·재평가 |
| 전체 제품 최종 검수 | 위 Extended Scope 의존으로 11단계 `BLOCKED` | 각 경로의 공식 자료와 Quality Gate 통과 |

현재 학생 업로드 후보나 사용자가 직접 입력한 `VERIFIED` 표시는 공식 증빙의 진위를 자동 검증하지 않는다. 학생별 자료가 없으면 실제 졸업 가능이라고 확정하지 않는다. 원본 교육과정 PDF와 평가 PDF는 변경하지 않았다.

## Core 독립 Red-Team / Acceptance Test (2026-09-29)

- **범위:** `docs/design/core_scope.md`의 2026 컴퓨터공학과 국내 일반 학생 단일전공 Core만 검수했다. 전체 제품의 4·10단계 `IN PROGRESS`, 9·11단계 `BLOCKED`는 Extended Scope 기준으로 유지한다. 상세 결과는 `evaluation/results/core_acceptance_redteam_2026-09-29.md`에 기록했다.
- **Builder → Reviewer:** 새로운 반례 8개를 `tests/test_core_acceptance.py`에 추가했다. 과목·자유선택 배열 순서에 따라 판정/실행 ID가 달라지던 문제, “전공 점수/얼마나 인정돼/졸업될까” 해석 문제, 0학점 필수과목 추가 가정의 요건 변화와 가정 관계가 화면에서 빠지던 문제를 수정했다. 원문 규칙·평가 정답을 추가하지 않았다.
- **Verifier:** PDF 261·577쪽 수치와 그래프 규칙값, 세 질문의 답변→결정→규칙 결과→반환 관계→출처, UI 다섯 시나리오의 그래프 간선/노드·규칙·실행 이벤트·PDF 링크를 독립 API 재실행과 대조했다. PDF·DOCX·PNG의 브라우저 파일 선택→추출→후보 확인→학생 상태→질문→판정을 각각 다시 실행했다. `qwen3:8b` ON/OFF 다섯 질문의 결정·수치·근거·실행기록·정형 답변이 같았다. 평가자료의 런타임/데이터/fixture 유입 흔적을 찾지 못했다.
- **검증 명령:** `python -m unittest discover -s tests -q` **128 tests OK**; `./scripts/demo_core.ps1` 5/5 PASS; `python scripts/verify_redteam_live.py 18473`, `python scripts/verify_core_live.py 18473`, `python scripts/verify_live_integration.py 18473`, 현행 UI JavaScript `node --check` PASS. 원본 PDF와 평가 PDF는 변경하지 않았다.
- **Quality Gate: CORE ACCEPTANCE PASS.** 합성 입력으로 현 Core를 로컬 데모·범위가 명시된 학술/프로젝트 시연에 사용할 수 있다. 실제 학생의 공식 증빙 진위는 자동 검증하지 않으며, 과거 적용자·다전공·공식 동일/대체 지정·`GEA8617` 충돌·HWP 양성 경로·전체 승인 요청서 평가는 `Extended Scope`의 `BLOCKED` 또는 미완료로 유지한다.

## 독립 50문항 사용자 시나리오 평가 (2026-09-29)

- **Builder:** `evaluation/core_scenarios/`의 독립 JSON 50문항을 `scripts/evaluate_independent_scenarios.py`로 실제 `/api/query` 자연어 입력 경로에 보냈다. VERIFIED 카탈로그·기존 합성 fixture에서 학생 상태를 생성하고 질문 해석, 조회 계획, 그래프 근거, 규칙 결과, 판정, 한국어 답변, 실행 기록을 `evaluation/results/independent_scenario_results.json`에 저장했다. 요약은 `evaluation/results/independent_scenario_report.md`에 있다. 결과는 **PASS 33 / FAIL 16 / SKIP 1**이다.
- **Reviewer:** 원래 50문항과 다른 경계값·증빙 누락·0학점 필수·중복·미확인 과목·대화 맥락 반례 **15개를 추가해 15/15 통과**했다. 평가 과정에서 개인 상태 질문을 정책 조회로 오해하거나, 복합 가정 질문에서 가정 부분을 버리거나, 카탈로그 편성 학점 합계를 최소 졸업학점으로 답하는 결함을 발견했다. 마지막 사례는 집계 기능이 없으므로 수치를 꾸며내지 않고 `CATALOG_AGGREGATE_UNSUPPORTED`로 명시적으로 미해결 처리했다.
- **Verifier:** 판정이 나온 **33문항**의 반복 실행·LLM ON/OFF 결정/수치/근거/trace 일치가 모두 통과했고, 입력 배열 순서 변경 비교 **27건**도 모두 같았다. 로컬 모델의 표현 상태는 **33건 VERIFIED_STYLE**이었다. PDF 해시와 실제 인용 페이지, 261·577쪽 VERIFIED 학점표 행, `GRAPH_QUERY` 반환 관계와 `EvidenceBundle`·규칙 결과·`AnswerPayload`·`ExecutionTrace`를 대조했다. 브라우저에서 과목 조회의 펼쳐보기 패널을 열어 결정 ID `DEC-070a1cc9ee6806a5`, 관계 3건, 실행 순서 `QUERY_PLAN→GRAPH_QUERY→DECISION`, PDF 262쪽이 같은 학생 상태의 독립 API 호출과 일치함을 확인했다. 런타임 소스·스크립트·처리 데이터·테스트에서 평가 전용 자료나 독립 질문세트의 유입 흔적은 찾지 못했다. 승인 요청서 내용은 열지 않았다.
- **회귀:** `python -m unittest discover -s tests -q` **132 tests OK**. 실제 서버에서 `verify_redteam_live.py`, `verify_core_live.py`, `verify_live_integration.py`가 각각 통과했다. 평가기는 결과 파일을 쓴 후 FAIL이 있으면 종료 코드 1을 반환한다. 한 문항은 누락 학기 때문에 특정 필수과목의 미이수를 공식적으로 확정할 수 없어 **SKIP**했다.
- **Quality Gate: FAIL (독립 50문항 수용).** 기존 2026 단일전공의 명시된 구조화 판정 경로에서 잘못된 `ELIGIBLE_PDF` 확정은 발견되지 않았다. 그러나 카탈로그 집계·전체 요건 열거·목표 과목이 불분명한 가정·메타/실행 설명 질문 등 **16문항**의 사용자 요청을 아직 처리하지 못한다. 따라서 이전의 제한적 Core Acceptance PASS를 50문항 자연어 수용 PASS로 확대하지 않는다. 10단계는 `IN PROGRESS`를 유지하고 실패 ID·사유는 결과 문서에 남긴다.

## 독립 50문항 실패 수정 및 재검증 (2026-09-29)

- **Builder:** 수정 전 `33 PASS / 16 FAIL / 1 SKIP` 원본 JSON·보고서를 `_before` 파일로 보존하고, 각 실패의 이전/현재 질문 구조·대상 식별·계획·실패 계층을 `evaluation/results/independent_failure_analysis.md`에 기록했다. 카탈로그 VERIFIED 행의 COUNT/SUM, VERIFIED 요건 목록, 과목 존재 확인, 일관성 및 실제 trace 설명 의도를 추가했다. `WHAT_IF`는 명시 다중 과목·유일 미충족 필수 후보를 검증해 계산하고, 미지정·모호·미확인 과목은 실제 상태만 반환하며 `NEEDS_TARGET`으로 남긴다. 코드 없는 이수기록은 제외 이유와 함께 보존하고 관련 결과를 `NEEDS_INFORMATION`으로 둔다. 기존 졸업 기준값과 필수 규칙은 변경하지 않았다.
- **Reviewer:** 평가 50문항 밖의 새 반례 **16개**를 실제 `/api/query` 경로에 추가했다. 서로 다른 전공 분류 집계, 과거 과목표, 교양 집계 미지원, 복수 과목, 두 미충족 후보, 0학점 후보 없음, 코드 없는 공식 표시, 확인된 미충족과 부분 성적표 공존, 명시 미확인 코드의 대화 맥락 우선순위, 공식 잔여학점 입력 순서를 검사했다. 명시 미확인 코드를 이전 과목으로 해석할 수 있던 결함과 “들었다고 하면” 표현 누락을 재현·수정한 뒤 **16/16 PASS**했다. 이전 15개 반례를 합쳐 **31/31 PASS**다.
- **Verifier:** 교육과정 원본 PDF 해시, VERIFIED 과목/학점·PDF 261·577쪽 행, 실제 `QUERY_PLAN`·`GRAPH_QUERY`·집계/규칙 이벤트, EvidenceBundle·Decision·AnswerPayload·ExecutionTrace 일치를 평가기와 검증기로 확인했다. 49건의 LLM ON/OFF 핵심 결과·근거·trace와 반복 실행, 입력 순서 비교 40건, 동등 의미 표현 비교 6쌍이 일치했다. 목표 과목이 없는 5건은 **부분 답변 PASS**이며 가상 수치 계산이 수행됐다는 뜻이 아니다. `CTX_04`는 누락 학기에 특정 전필 미이수의 공식 증거가 없어 **SKIP** 유지. 평가 승인 요청서 내용은 열지 않았고 런타임·처리 데이터·테스트의 평가자료 유입 정적 검사는 PASS했다.
- **검증:** `python -m unittest discover -s tests -q` **138 tests OK**; `python scripts/evaluate_independent_scenarios.py --port 18473` **49 PASS / 0 FAIL / 1 SKIP**; `python scripts/verify_redteam_live.py 18473`, `verify_core_live.py 18473`, `verify_live_integration.py 18473` PASS. 결과는 `evaluation/results/independent_scenario_results.json`과 보고서에 남긴다.
- **Quality Gate: 독립 50문항 Core 수용 PASS.** 기존 FAIL 16건은 일반화된 해석·대상·조회·입력 계약 수정과 재검증으로 해소됐다. 이는 현재 2026 컴퓨터공학과 국내 일반 단일전공 Core의 **확정 가능 질문과 안전한 부분 답변** 범위에 한한다. 4·9·11단계의 Extended Scope 제약과 전체 제품 10단계의 후속 평가 작업은 그대로 유지하므로 단계 10은 `IN PROGRESS`다.

## 공식 문서집합·RuleSet 버전 도입 (2026-09-29)

- **Builder:** `CURRICULUM-2026` 한 건을 `ADS-CE-2026-CORE` v1의 유일한 공식 문서로 등록했다. 원본 SHA-256과 PDF locator를 확인한 19개 VERIFIED 요건 중 단일전공 학생에 적용 가능한 18개를 `CRS-CE-2026-CORE` v1에 연결했다. 확인되지 않은 발행기관·시행일·개정값은 `null`로 보존하고, 과거 과목표·공식 동일/대체 지정·제2전공 자료와 `GEA8617` 충돌은 기존 Core 범위 밖/확인 필요로 유지한다. `RuleSetStore`의 내용 해시 스냅샷과 활성 포인터, 판정·실행기록의 집합/RuleSet 버전, 학생별 적용 Rule ID, 펼쳐보기의 문서 출처 표시를 구현했다. 새 문서는 PDF/텍스트 추출·해시·미검증 관련 후보를 거친 뒤 검토된 관계·원문 locator·변경만 새 버전으로 발행한다. 기존 버전과 결정의 선택적 보관·차이 비교를 지원한다.
- **Reviewer:** 합성 `TEST FIXTURE` 공식 문서로 무관 문서, SUPPLEMENTS, CLARIFIES, OVERRIDES, CONFLICTS_WITH, v1 재현, v1/v2 차이, 평가자료 배제, 출처 파일 변조, 범위 불일치, 미검증 관계를 검사했다. 추가 반례에서 미검증 새 locator, 새 문서를 인용하지 않은 문서 관계, 규칙과 실행 범위 불일치, 과거 스냅샷 변조를 거부하도록 보강했다. 초기에 `RULESET_SELECTION`을 새 trace 이벤트로 삽입해 기존 첫 그래프 조회 위치 테스트 2건이 깨졌고, 선택 정보를 실제 `QUERY_PLAN` 이벤트에 기록해 회귀를 수정했다. 일부 범위만 대체하면 다른 학생 범위의 원래 규칙이 지워질 수 있어 그 자동 발행을 거부하고 별도 범위 규칙 모델이 필요하다고 문서화했다.
- **Verifier:** 교육과정 PDF SHA-256 ↔ 문서 엔티티 ↔ v1 문서집합 ↔ v1 RuleSet ↔ 규칙별 출처 locator ↔ Decision/ExecutionTrace/AnswerPayload를 검사했다. 합성 v2의 기존 규칙 유지·새 규칙 추가·두 문서 출처·검증된 대체·미해결 충돌 `UNKNOWN`·과거 v1 재실행을 확인했다. 실제 브라우저의 합성 부분 성적표 질문에서 펼쳐보기의 `ADS-CE-2026-CORE` v1, `CRS-CE-2026-CORE` v1, 규칙별 문서 ID, 실행 순서, PDF 페이지 링크를 확인했다. `evaluation/document_registry.json`의 평가 문서는 `EVALUATION_ONLY`로만 표기하며 원문 내용/해시를 읽지 않았고 런타임 집합에는 넣지 않았다.
- **검증:** 새 버전/충돌 반례 **20개 PASS**. 전체 회귀 테스트 **158개 PASS**; 합성 Core 데모 5/5, 라이브 Core·Red-Team·업로드 통합 검사 PASS; 독립 질문세트 **49 PASS / 0 FAIL / 1 SKIP**, LLM ON/OFF 49/49 일치, 평가자료 누수 정적 검사 PASS. 현행 UI JavaScript `node --check` PASS. 실제 추가 공식 문서는 없으므로 v2 실운영 발행은 수행하지 않았다.
- **Quality Gate: 현재 PDF 한 건의 Core RuleSet v1 및 안전한 버전 전환 기반 PASS.** Core의 학점·요건·졸업 결론은 유지된다. 추가 공식 문서의 실제 규칙 해석은 그 문서가 제공되고 검증될 때 진행한다. 일부 학생 범위만 덮어쓰는 동일 Rule ID의 자동 대체는 현재 **지원 범위 제한**이며, 이를 새 버전에 임의 적용하지 않는다. 기존 4·9·10·11단계의 Extended Scope 상태는 변경하지 않는다.

## 실제 학생 입력 검증 1단계: 성적표 → StudentState (2026-09-29)

- **Builder:** 업로드 원본의 학생 식별·학과·입학연도와 과목코드·이름·취득학점·학기·이수표시·이수구분·OCR 점수를 후보로 추출하고, 공식 2026 과목표와 정확한 코드/이름으로 연결한다. 새 `/api/normalize-upload`는 같은 파일 해시를 재확인한 뒤 사용자 검토 결과로 **새** `StudentState`를 만들며 기존 합성 예시를 섞지 않는다. 중복·미등록·원문 누락·정정값은 미확인으로 두고, 전체 성적표/적용 교육과정도 자동 확인하지 않는다.
- **Reviewer:** 독립 합성 반례 10개로 과목명·학점 불일치, 두 학기 중복, 코드/학점/이수표시 누락, 이름만 있는 행, 읽을 수 없는 PDF 페이지, 학생 정보 누락, 문자열 확인값 위장, 이수 상태 미확인을 검사했다. 2쪽 PDF fixture 생성 오류는 테스트 자료를 실제 빈 둘째 쪽이 생기도록 수정한 뒤 다시 통과했다.
- **Verifier:** 합성 DOCX를 실제 HTTP `extract → normalize-upload → query`로 실행해 4행 중 1행만 사용 가능, 중복 2행·미등록 1행은 미확인임을 확인했다. 새 상태는 `PARTIAL`/적용 `UNVERIFIED`이고 졸업 질의는 `UNKNOWN`/`NEEDS_INFORMATION`이다. RuleSet v1 유지, 파일 해시 변경 거부, 전체 자동 테스트 **168개 PASS**, UI JavaScript 구문 검사 PASS, 기존 Core 라이브 3종 PASS, 독립 50문항 49 PASS·0 FAIL·1 SKIP을 확인했다. 개인 업로드 세부 기록은 비공개로 보존한다.
- **Quality Gate: 합성 API 정규화 경로 PASS; 실제 학생 자료 수용 BLOCKED.** 작업공간에 실제 학생 성적표가 없어 실제 자료의 원문↔추출↔StudentState 대조는 수행하지 못했다. 이 PC의 Chrome 확장 프로그램 파일 URL 접근 제한과 인앱 브라우저 파일 선택 이벤트 문제로 이번 브라우저 파일 선택→정규화 화면 E2E도 미검증이다. 실제 학생의 졸업 가능 여부는 이번 단계에서 확정하지 않는다.

### 후속 개인 업로드 검수 (세부 결과 비공개)

- **Builder → Reviewer → Verifier:** 실제 업로드 원문과 추출·정규화 후보를 대조하고, 표 열의 과목명·학점·학기·성적 추출 오류를 수정했다. 확인되지 않은 과목 연결, 반복 이수와 적용 교육과정은 미확인으로 유지한다. 개인 이수 내역과 상세 수치는 공개 저장소에 기록하지 않는다.
- **Quality Gate:** 실제 PDF의 행 추출·후보 변환 검수는 PASS. 공식 적용 과목표, 미등록 과목의 인정 관계, 반복 처리, 전체 성적표 범위와 전공유형이 확인되지 않아 해당 학생의 졸업판정 입력은 BLOCKED로 남겼다. 상세 기록은 로컬 비공개 영역에 보존한다.

## 개인 업로드의 별도 2026 가정 검수 (2026-09-30)

- **Builder:** 실제 업로드 StudentState를 수정하지 않고 별도의 2026학번 가정 객체를 만들어 CRS-CE-2026-CORE v1로 질의했다. 원문 필드·검증 상태·과목표별 이수구분을 분리해 보존하고 후보 카탈로그 조회를 판정 조회와 구분했다. 개인별 JSON과 상세 보고서는 Git 제외 logs/private/에만 둔다.
- **Reviewer → Verifier:** 합성 반례와 실제 실행 기록으로 원본 상태 불변, 미연결·반복 후보의 임의 인정 방지, 가정 입학 이전 이수의 공식 인정 보류를 확인했다. 학생 증빙과 적용 조건이 부족해 최종 상태는 NEEDS_INFORMATION이다. 이것은 실제 학생의 졸업 가능 여부 판정이 아니다.
- **Quality Gate:** 가정 실행과 원본 보존 PASS; 실제 졸업 가능 판정 보류. 개별 이수 수치와 PDF 지문은 공개 문서에서 제외한다.

## 2026 공식 Core 모의 PDF 업로드 판정 검증 (2026-09-30)

- **Builder:** `scripts/generate_mock_2026_transcripts.py`가 고정된 `CRS-CE-2026-CORE` v1의 VERIFIED 과목과 19개 Rule IR을 읽어, 공식 증명서로 오인되지 않는 모의 PDF 4종과 기대 JSON을 생성했다. `scripts/verify_mock_2026_pdf_e2e.py`는 실제 HTTP `/api/extract → /api/normalize-upload → /api/query`를 거쳐 원문 6개 열값, 과목 연결, 19개 요건 결과, 판정, 근거와 LLM ON/OFF를 비교한다. PDF만으로는 적용연도·전체 성적표·논문·인증 등을 확정할 수 없어 4건 모두 `UNKNOWN`이며, 완전 시나리오의 결론은 별도의 **테스트 전용** 학생 증빙을 명시적으로 추가한 뒤에만 생성된다. 결과는 `evaluation/results/mock_2026_pdf_e2e_results.json`과 보고서에 있다.
- **결과:** complete 43행·131학점·전공 96학점 `ELIGIBLE_PDF`(18개 SATISFIED, 1개 NOT_APPLICABLE); partial 28행·74학점·전공 39학점 `NOT_ELIGIBLE_PDF`(6개 UNSATISFIED); boundary 42행·131학점 `NOT_ELIGIBLE_PDF`, 0학점 필수 `CDA0034` 추가 시 필수 요건만 UNSATISFIED→SATISFIED, 별도 졸업 질의는 `ELIGIBLE_PDF`, 원본 불변; missing_info 43행·표기 131학점, 42행 연결, 총 확정학점 미정, `UNKNOWN`(2개 NEEDS_INFORMATION). 4/4 기대값과 실제 API 결과가 일치한다.
- **Reviewer:** 공식 카탈로그 기반으로 중복 이수, 코드/이름 충돌, 다른 0학점 필수 누락, 입력 순서 반전, 미등록 코드, 업로드 이수구분 충돌, 코드 없는 0학점 행의 7개 추가 PDF 반례를 실제 업로드 HTTP 경로로 시험했다. 마지막 반례에서 코드 빈 행의 원문 학점 0이 파서에서 누락됨을 발견해 표의 확인된 학점 열만 읽도록 수정했다. 수정 후 **7/7 PASS**이고 미확인 행은 학점 인정·졸업 가능으로 승격되지 않는다.
- **Verifier:** 생성된 PDF 전 페이지의 모의자료 경고를 시각/텍스트로 확인했다. 각 PDF의 원문 행을 코드·이름·학점·학기·분류·성적 단위로 추출 후보와 대조하고, 선택된 모든 고유 과목의 코드·출처 페이지가 현행 공식 PDF/VERIFIED 카탈로그와 일치함을 확인했다. `EvidenceBundle`의 공식 문서 ID, 각 요건의 source refs, 실제 `QUERY_PLAN`·`GRAPH_QUERY`·`RULE_EVALUATION` 및 시나리오 trace를 검사했다. 별도 인앱 브라우저에서 boundary PDF 파일 선택→42행 추출→정규화→질문→가정 delta→펼쳐보기의 판정 ID·관계 148개·노드 149개·실행 218건·PDF 페이지 집합을 같은 API 결과와 대조했다. 원래 사용자 탭의 업로드 상태가 합성 fixture와 섞이지 않았음을 마지막에 재확인했다. 평가 전용 원문은 열지 않았고 합성 파일/런타임에 평가 경로·실제 학생 표식의 유입이 없음을 정적 검사했다.
- **검증 명령/결과:** `scripts/generate_mock_2026_transcripts.py`, `scripts/verify_mock_2026_pdf_e2e.py` 4/4 PASS; `python -m unittest discover -s tests -q` **179 tests OK**; `scripts/demo_core.py` 5/5 PASS; `scripts/verify_core_live.py 18473` PASS; `scripts/evaluate_independent_scenarios.py --port 18473` **49 PASS / 0 FAIL / 1 SKIP**, LLM 일치 49/49, 누수 검사 PASS. 4개 E2E의 LLM ON/OFF 판정·수치·요건·근거·trace도 모두 일치한다. 현재 PC에서는 `python`이 WindowsApps 별칭이라 실제 검증에는 번들 Python 실행 파일을 사용했다.
- **Quality Gate: 2026 컴퓨터공학과 국내 일반 단일전공 Core의 합성 PDF 입력→판정 경로 PASS.** 모든 적용 VERIFIED 요건과 별도 학생별 증빙이 확인된 테스트 상태에서만 `ELIGIBLE_PDF`가 나온다. 실제 학생의 판정, 타 학과/과거 교육과정/다전공/공식 대체 관계/HWP 양성 경로 등 Extended Scope는 기존 `BLOCKED` 또는 `IN PROGRESS` 상태를 유지한다. 전체 제품의 단계 10·11을 이번 합성 검증만으로 DONE으로 변경하지 않는다.

## 남은 요건과 이수 후보 계산 검증 (2026-09-30)

- **Builder:** 기존 Rule Engine의 19개 RequirementResult를 `RemainingRequirementSummary`로 투영하고, VERIFIED 카탈로그와 실제 SQLite `SATISFIES` 관계를 조회해 `REQUIRED / ELIGIBLE_OPTION / ALREADY_COMPLETED / NOT_APPLICABLE` 후보를 분류했다. 학년은 계산 입력으로 쓰지 않는다. 자연어 `REMAINING_PLAN`, 영역별 진행도, 실제 과목별 근거, 가정 이수의 총·전공학점 및 졸업판정 미리보기 delta를 API·UI 계약에 연결했다. 개설·선수과목은 `NOT_VERIFIED`다. `scripts/generate_remaining_fixtures.py`는 RuleSet v1에서만 10개 합성 StudentState와 독립 기대값을 생성한다.
- **실행:** `scripts/verify_remaining_2026_e2e.py`가 자체 HTTP 서버의 실제 `/api/query`로 10개 상태×7개 한국어 질문 **70/70 PASS**, LLM ON/OFF 핵심 판정·수치·요건·후보·근거 **10/10 일치**를 확인했다. 실제 로컬 모델 표현 상태도 `VERIFIED_STYLE` 10/10이다. `year4_late` 43과목·131학점은 모든 적용 VERIFIED 요건 충족으로 `ELIGIBLE_PDF`; 총학점 131인 `required_missing`은 0학점 지정 필수 1과목 누락으로 미충족; `credit_or_general_short` 128학점은 교양/총학점 각각 2학점 부족이다. 프로필별 전체 요건·후보·실제 질문 결과는 `evaluation/results/remaining_2026_e2e_results.json`과 보고서에 기록했다.
- **Reviewer:** 학년 라벨만 변경, 같은 학년의 다른 이수내역, 입력 순서 역전, 중복 이수, 미등록 코드, 두 과목 동시 가정, 앞선 대화 과목의 근거 질문 **7/7 반례 PASS**. 초기 검수에서 합성 fixture의 영어 면제 검토 부재, 축약형 전필 질문의 기존 의도 회귀, 일관성 검사 래퍼의 졸업 미리보기 검증 충돌을 발견했다. fixture에 명시적 테스트 전용 면제 검토를 추가하고, 의도 형태를 일반적으로 분리하며, 래퍼에 원판정 상태를 보존해 수정·재검증했다.
- **Verifier:** 공식 교육과정 PDF SHA-256과 VERIFIED 카탈로그 **323과목 전부**의 과목코드/출처 페이지를 직접 대조했다. 각 활성 후보의 실제 그래프 조회 `SATISFIES` 간선, 미충족 Rule ID, Rule 출처, `EvidenceBundle`, `ExecutionTrace`, 결정 해시를 출력 전 검증한다. 별도 인앱 브라우저의 합성 `year1_early` 질문에서 결정 ID `DEC-bf0c3e261a9df57d`, 실제 조회 관계 2081건, 실행 이벤트 49건, 총학점 진행 7/130, `SATISFIES` 관계와 PDF 링크 22개가 동일 StudentState의 API 응답과 일치함을 확인했다. 관계 2081개를 한꺼번에 나열하던 UI 결함은 실제 관계 중 80개를 종류별로 표시하고 전체 수와 API 경로를 명시하도록 수정했다. 합성 자료와 개인 업로드 세션을 혼합하지 않았고 평가 전용 문서 내용은 열지 않았다. UI JavaScript 구문 검사 PASS, 전체 `python -m unittest discover -s tests -q` **188 tests OK**. 독립 50문항은 현재 코드의 별도 로컬 HTTP 서버에서 **49 PASS / 0 FAIL / 1 SKIP**, 누수 검사 PASS다.
- **Quality Gate: 이번 2026 Core 남은 요건·후보 기능 PASS.** 학년 라벨에 의존하지 않는 결정적 결과, 원본 StudentState 불변, LLM 불변, VERIFIED PDF 출처, 실제 그래프 관계와 실행 기록, 70개 API 질문이 일치한다. 선택 후보는 수강 우선순위·실제 학기 개설 정보가 아니다. `CTX_04`의 기존 SKIP과 전체 제품 단계 10·11의 Extended Scope 상태는 유지한다.

- **최종 fixture 수정·재검증:** 초기 학년의 합성 상태가 완전 졸업 fixture의 논문·인증 완료 표시를 물려받은 결함을 발견했다. 이를 명시적인 테스트 전용 미완료 증빙으로 고치고 RuleSet v1 기반 기대값을 다시 계산했다. 수정 후 HTTP 질문 70/70, Reviewer 반례 7/7, 전체 회귀 188/188, UI JavaScript 문법 검사와 `git diff --check`가 통과했다. 앞선 브라우저 결정 ID는 수정 전 합성 fixture의 화면↔API 대조 기록이며, 수정 후 기대값은 결과 JSON에 있다.

- **Reviewer 추가 수정 및 최종 Gate:** 가상 이수에서 지정 필수 한 과목이 해결되어도 다른 필수가 남아 전체 요건 상태가 `UNSATISFIED`이면 변화가 드러나지 않는 결함을 찾았다. 가정 전후 미이수 필수 목록과 해결된 과목 ID를 `SCENARIO_COMPARISON`/답변/UI에 추가하고 양쪽 `DeterministicDecision`으로 검증했다. 새 반례 테스트를 유지한다. 최종 재검증은 **189 tests OK**, 10개 fixture의 실제 HTTP 질문 **70/70 PASS**, Reviewer **7/7 PASS**, 독립 평가 **49 PASS / 0 FAIL / 1 SKIP**, LLM ON/OFF 핵심 일치 **10/10**, UI JavaScript 문법 검사 PASS, 평가 누수 검사 PASS다. 이번 기능 Gate는 PASS이며, 미확인 개설 정보와 기존 Extended Scope는 그대로 보류한다.

## 학생용 남은 요건 답변·UI 검수 (2026-09-30)

- **Builder:** 기존 `DeterministicDecision`, `RemainingRequirementSummary`, `CandidateCourse`, RuleSet v1을 변경하지 않고 표시 전용 `remaining_presentation`을 추가했다. 기본 답변을 현재 상태→반드시 이수→부족 학점→전공/교양 요건별 선택 후보 수→확인 필요의 다섯 구획으로 구성했다. 수백 개 선택 과목명은 기본 답변에서 제거하고, 펼쳐보기에서 전체 후보를 지연 표시하며 스크롤 영역으로 제한했다. 각 후보 행에는 실제 조회된 `SATISFIES` 관계, 미충족 Rule, 과목표·규칙 PDF 링크를 표시한다. 개설·선수과목·시간표 충돌은 미확인으로 표시하며 순위를 만들지 않는다. 학생 표현 3종의 누락된 계획 의도도 기존 `REMAINING_PLAN`으로 연결했다.
- **Reviewer:** 10개 합성 StudentState에 지정한 10개 문장을 실제 `/api/query`로 **100/100 PASS**. 학년 라벨 교체에도 동일 결과, 같은 학년의 다른 이수내역에는 다른 결과, 전체 요건 충족 시 선택 후보 0건, 특정 후보 설명의 실제 관계·Rule·PDF 출처를 확인하는 독립 반례 **4/4 PASS**. 발견한 UX 문제는 기본 답변의 후보 이름 나열, 펼쳐보기 35개 제한, 긴 펼친 페이지, `졸업까지/어느 정도/4학년인데` 등의 의도 누락, 정보 부족 시 미이수 전필 0개로 오해할 위험이었다. 일반적 표시·해석 수정 후 재검증했다.
- **Verifier:** 표시 투영을 원래 결정값으로 재계산하는 payload verifier를 연결했다. 각 후보군/요건별 개수는 반환된 `ELIGIBLE_OPTION`과 `satisfies_requirement_ids`로 확인한다. 별도 로컬 브라우저의 합성 1학년 상태에서 기본 답변 5구획·735자, 교양 전체 후보 **274행**, 380px 스크롤, 실제 SATISFIES·Rule·PDF 링크를 확인했다. 실제 업로드 탭은 건드리지 않았다. LLM ON/OFF의 결정·수치·요건·후보·근거·trace는 10/10 일치한다.
- **Quality Gate: 이번 답변·UI 개선 PASS.** `scripts/verify_remaining_ux_2026.py` 100/100, 기존 남은 요건 E2E 70/70, 전체 회귀 **191 tests OK**, 독립 50문항 **49 PASS / 0 FAIL / 1 SKIP**, UI JavaScript 문법·`git diff --check` PASS. 결과는 `evaluation/results/remaining_2026_ux_results.json`과 보고서에 기록했다. Core Acceptance의 결정적 판정 범위는 유지하고 학생용 설명만 개선했다. 다음 학기 개설·선수과목·시간표 검증은 공식 자료가 없어 미지원이다.

## 승인 요청서 평가 전 최종 baseline (2026-09-30)

- **상태: 승인 요청서 평가 전 baseline 고정 완료.** 활성 `ADS-CE-2026-CORE` v1과 `CRS-CE-2026-CORE` v1, 공식 PDF 및 RuleSet 스냅샷 해시를 대조했다. 상세 기능·범위·제한·재현 명령은 `evaluation/results/pre_approval_core_baseline_2026-09-30.md`에 고정했다.
- **재검증:** 전체 회귀 **191 tests OK**, 합성 Core 데모 **5/5**, 학생용 실제 `/api/query` **100/100**, Reviewer 반례 **4/4**, 남은 요건 E2E **70/70** 및 Reviewer **7/7**, 모의 2026 PDF 업로드 E2E **4/4**, 독립 50문항 **49 PASS / 0 FAIL / 1 SKIP**. LLM ON/OFF 핵심 결과는 독립 문항 49/49, 남은 요건 프로필 10/10, 모의 PDF 4/4 일치했다. UI JavaScript 문법·Git diff 공백 검사와 평가자료 런타임 유입 검색도 통과했다.
- **Quality Gate:** 명시된 2026 컴퓨터공학과 국내 일반 단일전공 **Core baseline PASS**. `CTX_04` SKIP과 Extended Scope의 `BLOCKED`/미완료 항목은 유지한다. 이번 baseline 검증에서 승인 요청서 PDF는 파일 존재 메타데이터만 확인했고 본문·문항·정답을 열지 않았다. 승인 요청서 평가는 아직 시작하지 않는다.

## 공식 PDF 근거 정책 보강 및 평가 후 검증 (2026-09-30)

- **Builder:** 기존 `ADS-CE-2026-CORE` v1과 실행 요건을 그대로 보존하고, 공식 PDF 33쪽의 교양 예외·상한 초과분 처리 사실 두 건을 추가한 불변 `CRS-CE-2026-CORE` v2를 활성화했다. 정책 질문은 학생 상태 없이 조회하고, 개인 정보가 없는 복합 질문은 확인된 정책만 부분 답변한다. 적용 대상·연도, 교양 상한/잔여, 전공·졸업 잔여 구조를 결정적 계산 객체로 남긴다. 과거 전체 RuleSet과 공식 동일·대체 목록은 임의 보완하지 않는다.
- **Reviewer:** 승인 요청서 문항에서 복제하지 않은 조건부 적용·수치 경계·정책/개인 분리·부분 답변 반례 24개와 스냅샷 변경 제한 반례를 포함한 전체 215개 테스트가 통과했다. 문서 보강 migration이 정책 사실 외 카탈로그 필드를 변경할 수 있던 위험을 발견해 차단했다.
- **Verifier:** v1/v2 카탈로그 차이는 `curriculum_ruleset` 메타데이터와 새 `policy_facts` 두 건뿐이다. 공식 PDF SHA-256, RuleSet 요구값 불변, 원문 locator·계산 이벤트·결정 payload를 대조했다. 전체 회귀 215/215, 독립 50문항 49 PASS·1 SKIP, 학생용 실제 API 100/100와 Reviewer 4/4, 모의 PDF 업로드 E2E 4/4 및 LLM ON/OFF 판정 일치가 통과했다. 평가 질문만 런타임으로 전달한 재평가와 별도 평가기 채점 결과는 공개되지 않는 `evaluation/results/approval_after_results.json` 및 보고서에 보존한다. 질문·답변 원문과 평가 전용 자료는 런타임·공식 문서집합에 들어가지 않았다.
- **Quality Gate:** 이번 공식 PDF 근거 구조 수정은 **PASS**. 2026 컴퓨터공학과 일반 단일전공 Core 판정은 보존됐다. 추가 공식 지정표·최종 승인 기록·상담 세부 지침과 일부 평가 답변 충돌/판독 문제는 별도 비공개 평가 보고서의 `B/C` 항목으로 남긴다. 따라서 전체 제품의 10단계 `IN PROGRESS`, Extended Scope의 `BLOCKED` 상태를 완료로 변경하지 않는다. 43문항 재평가는 사전 10문항 요약 노출 이력이 있어 엄밀한 첫 노출 블라인드 점수로 취급하지 않는다.

## Core v2 하나의 채팅방 UI 개편 (2026-10-01)

- **상태: DONE / scoped Quality Gate PASS.** ADS v1·CRS v2·공식 데이터·판정·질문 해석 계약은 유지했다. 전체 제품 단계와 Extended/B/C의 BLOCKED를 완료로 변경하지 않는다.
- **Builder:** 상단 상태/설정·중앙 대화/파일 카드·하단 첨부/여러 줄 질문으로 재배치했다. JSON·LLM 설정과 긴 검토 표는 필요할 때 열고, 업로드 후보와 적용 학생·context·답변 당시 snapshot을 분리했다. 새 학생은 명시적 교체이며 이전 대화/근거를 보존한다. 페이지 메모리만 사용한다.
- **Reviewer:** 파일/학생 교체, 정정 후 staged 적용, 재추출·재정규화 중 이전 후보, 늦은 응답, 중복 전송, 잘못된 JSON/PDF, 읽기 스크롤·초안·초기화 반례를 검토하고 수정했다. 같은 작업자의 역할별 검토이며 독립 외부 검수로 주장하지 않는다.
- **Verifier:** 합성 PDF 43행·DOCX·PNG를 실제 선택→추출→정규화→적용→질문 경로로 검증했다. 남은 요건/과목/simulation의 화면과 실제 payload·Rule·SVG 관계·PDF·v2를 대조했다. 360/390/768/1280px와 43행 검토 패널 가로 넘침 없음. 최종 브라우저 probe 21/21, 전체 회귀 217/217, 학생용 API 100/100·반례 4/4, 모의 PDF 4/4, 독립 49 PASS·0 FAIL·1 SKIP. LLM ON/OFF 핵심 결과 일치. 공식 PDF/RuleSet 해시·평가 누수 검사·JS 문법·diff 검사를 확인했다.
- **남은 제한:** 실제 OS 한글 IME 및 모바일 가상 키보드 실기기 검수는 수행하지 않았다. 조합 중 Enter 보호는 실제 클라이언트 함수 반례로 검증했다. HWP 등의 기존 제한은 유지한다. 실제 학생 탭·업로드·평가 승인 요청서를 열거나 사용하지 않았다. 상세 상태 계약과 검수는 `docs/design/chat_session_ui.md`, `evaluation/results/chat_ui_acceptance_2026-10-01.md`에 있다.
