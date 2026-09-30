# Core v2 하나의 채팅방 UI 검수

## 범위와 결과

**Quality Gate: PASS — 기존 Core v2의 화면·페이지 상태 개편 범위.** 기준 커밋 `34ec091f78062380ee574054f424439491ebef89`, ADS-CE-2026-CORE v1 / CRS-CE-2026-CORE v2를 유지했다. 기존 19 Rule과 공식 카탈로그, 서버·Rule Engine·질문 해석·렌더러 코드는 변경하지 않았다. 실제 학생 탭·자료와 평가 승인 요청서는 사용하지 않았다. 모든 업로드와 학생 상태는 기존 공개 합성 fixture다.

Builder·Reviewer·Verifier는 같은 작업자의 역할별 구현·비판 검토·실행 대조다. 독립 외부 검수나 별도 에이전트 검수로 주장하지 않는다. 참고 이미지의 시각 방향은 사용자 설명에 따랐으며 이미지 속 개인정보·서비스 기능을 복제하지 않았다.

## Builder

- 상단 실제 학생 상태와 설정, 중앙 시간순 대화와 파일 카드, 하단 첨부·여러 줄 입력·전송으로 배치했다. 연한 블루그레이 배경, 왼쪽 밝은 조교 카드와 오른쪽 사용자 메시지를 사용한다.
- StudentState JSON·로컬 LLM은 설정에, 긴 원문/연결/정정 검토는 대화상자에 옮겼다. 10MB 제한과 기존 확장자·HWP 5 제한은 유지했다.
- 파일 선택·추출·정규화 후보·학생 적용을 분리했다. 학생 적용은 교체이며 대화는 보존하고 이전 context는 무효화한다. 답변은 당시 학생·RuleSet·payload에 고정한다.
- 적용 정보 비우기·업로드만 폐기·전체 초기화의 범위를 각각 안내한다. 페이지 메모리만 사용하고 새로고침 복원 기능은 만들지 않았다.
- 기존 후보 전체 조회와 관계 그래프·계산·PDF·실행 기록을 유지했다. 기본 답변의 수치·문장은 서버의 검증된 값을 사용한다.

## Reviewer와 수정

| 반례 / 문제 | 실제 결과 |
| --- | --- |
| 새 파일 선택·추출이 대화/적용 학생을 지움 | 분리 후 기존 대화와 3행 적용 상태 유지; 새 43행은 검토 후보만 생성 |
| 학생 교체가 이전 학생과 합쳐짐 | 3→43→1행 교체 확인; 이전 답변의 학생 ID·payload 유지 |
| 이전 학생의 과목 context 사용 | 학생 교체 후 last_course_id 제거; 이전 CDA0143을 임의 가정하지 않음 |
| 정규화 후 정정 / 정규화 중 정정 | 적용 후보 무효화; 늦게 반환한 이전 정정 결과 폐기 |
| 같은 파일 재추출 / 재정규화 중 이전 후보 적용 | 시작 시 staged 결과·적용 버튼 무효화; 재추출 완료 전 이전 검토 접근 차단 |
| 이전 파일의 늦은 추출 결과 | 파일 generation 불일치로 폐기; 새 파일 후보에 섞이지 않음 |
| 학생 변경·전체 초기화 중 늦은 질문 응답 | 이전 요청 취소·revision 검사; 새 상태/빈 대화에 반영되지 않음 |
| 응답 중 중복 전송 | 전송 비활성화 및 active 요청 검사; 질문 한 건만 생성 |
| 잘못된 JSON / 잘못된 PDF | 오류 안내, 기존 적용 학생 보존, 재조작 가능 |
| Shift+Enter / 한국어 질문 Enter | 줄바꿈은 초안 유지, Enter는 한 번 전송 |
| 이전 메시지를 읽을 때 새 응답 | scrollTop 0 유지; 새 메시지 버튼으로만 아래 이동 |
| 작은 화면의 긴 placeholder·필드명·포커스 | 간결한 안내, 필드 줄바꿈, 키보드 포커스 표시 보강 |

21건의 최종 브라우저 판별값은 [JSON 기록](chat_ui_acceptance_2026-10-01.json)에 있다. 초기에 JSON 오류 안내의 문구를 임의 가정한 검수 probe는 실제 오류 안내와 기존 판정 불변 검증으로 바로잡았다. 애플리케이션 요구값·판정 테스트를 완화하지 않았다.

## Verifier: 실제 브라우저와 API 대조

| 검증 | 결과 |
| --- | --- |
| 학생 자료 없는 과목·정책 질문 | COURSE_LOOKUP / POLICY_LOOKUP 정상; 개인 질문만 자료 필요 안내 |
| PDF 파일 선택→추출→정정/확인→정규화→적용→질문 | mock_2026_complete.pdf: 2쪽·43후보·읽기 실패 없음; 확인 후 43 usable; 적용 교육과정 UNVERIFIED는 보존되어 전체 판정 UNKNOWN |
| DOCX 동일 경로 | synthetic-transcript.docx: 1후보; 미확인 행을 정상 이수로 자동 인정하지 않고 unresolved 유지 |
| PNG 동일 경로 | synthetic-ocr.png: 1후보·OCR confidence 약 0.62; 확인하지 않은 행·성적/학기 미확인 보존 |
| 실제/가상 분리 | 고자구 조회→그 과목 들으면: 실제 7학점 유지, 가상 10학점; 3개 실제 기록 불변 |
| 전체 교양 후보 접근 | 274행 모두 열림; 과목·학점·SATISFIES·Rule·PDF가 API와 일치 |
| 답변별 근거 대조 | 남은 요건·과목 조회·simulation의 answer_text, Rule 결과, SVG 노드/간선, PDF 페이지, RuleSet v2 일치. 남은 요건 화면의 Rule 19개·그래프 간선 77개 확인 |
| 로컬 LLM 실제 ON/OFF | qwen3:8b VALIDATED_SUGGESTION / VERIFIED_STYLE 실행; 동일 질문의 Decision·EvidenceBundle 불변 |
| 패널·학생만 비우기·전체 초기화·새로고침 | 안내된 범위와 일치; 패널 토글은 초안 유지, 새로고침은 빈 상태 |
| 360 / 390 / 768 / 1280px | 실제 앱 iframe의 innerWidth로 측정. 페이지 가로 넘침 없음; 실제 추출 43행 검토 패널의 clientWidth=scrollWidth; 입력창 화면 안에 유지 |

IAB의 viewport override가 실제 폭을 바꾸지 않아 이 측정을 통과로 사용하지 않았다. 기존 실제 Handler와 같은 출처의 **테스트 전용 responsive wrapper**에서 CSS viewport를 정확히 설정했다. 해당 wrapper는 제품 코드·공개 파일에 포함하지 않는다. 늦은 응답 반례는 실제 Handler에 2초 지연만 추가한 테스트 서버로 재현했고 응답 내용은 모의 생성하지 않았다. 지연은 성능 측정이 아니다.

한글 composition 이벤트·isComposing·keyCode 229 보호는 실제 클라이언트 함수의 Node 반례로 검증했다. 자동 브라우저의 한국어 텍스트/Enter 검수와 실제 OS 한글 IME·모바일 실기기 가상 키보드 검수는 구분하며 후자를 실행했다고 주장하지 않는다.

## 회귀와 Gate

| 실행 | 결과 |
| --- | --- |
| `python -m unittest discover -s tests -q` | 217/217 PASS; 기존 215개 유지, 클라이언트 lifecycle·비영구 저장 검증 2개 추가 |
| `python scripts/verify_remaining_ux_2026.py` | 실제 API 100/100, 기존 반례 4/4, LLM 10/10 일치 |
| `python scripts/verify_mock_2026_pdf_e2e.py` | 4/4, LLM 4/4 일치; PDF 단독 UNKNOWN과 별도 합성 증빙 후 결과 구분 |
| `python scripts/evaluate_independent_scenarios.py --port 18473` | 49 PASS / 0 FAIL / 1 SKIP, 기존 Reviewer 31/31, LLM 49/49 일치 |
| JavaScript 문법 / `git diff --check` | PASS |
| 공식 데이터·규칙·API 코드 변경 검사 | UI 외 src 변경 없음, data 변경 없음; 공식 PDF·스냅샷 해시 불변 |
| 평가자료 누수 정적 검사 | src/scripts/data/processed/tests에 평가 전용 자료 경로·정답 의존 일치 없음 |

CTX_04 SKIP과 기존 Extended/B/C 제한을 유지한다. HWP 5의 전체 양성 E2E, JPG/WEBP 자료 유형별 양성 검수, 실제 개설·선수과목·시간표는 추가 검증/공식 자료가 필요하다. 로그인·음성·모델 목록·요금제·클라우드·과거 채팅·공유/통화 기능은 만들지 않았다. 새 지원 범위나 규칙을 추가하지 않았다.

재현: `./scripts/serve.ps1 -Port 18473` 후 별도 탭을 열고 [데모 안내](../../docs/demo/core_v2_demo.md)를 사용한다. 기존 실제 학생 탭은 자동 새로고침하지 않는다. 합성 화면 스크린샷은 로컬 `logs/chat-ui-desktop.jpg`에만 저장하며 공개 Git에는 포함하지 않는다.
