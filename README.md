# Ontology Graph RAG Academic Advisor

*Ontology and Knowledge Graph based academic advisor with deterministic curriculum rule evaluation, explainable Graph RAG, and local LLM support.*

## 프로젝트 소개

이 프로젝트는 공식 교육과정의 과목·이수구분·졸업요건·적용 대상을 관계로 구조화하고 학생의 이수 상태를 검증합니다. 일반적인 PDF 문단 검색형 RAG만으로는 학점 합산, 필수과목 누락, 중복 인정과 적용연도 판단을 재현하기 어렵습니다. 따라서 **지식그래프는 사실과 관계를 조회하고, 결정적 Rule Engine은 조건을 계산**합니다. Graph RAG는 조회한 관계와 PDF 출처를 답변에 연결합니다.

로컬 LLM(qwen3:8b, 선택 사항)은 한국어 질문 해석과 검증된 결과의 문장 표현만 맡습니다. 졸업판정·학점·요건 상태는 LLM이 생성하지 않습니다. 모델을 끄거나 바꿔도 동일한 구조화 입력과 데이터·규칙 버전의 결정적 결과는 같아야 합니다.

## 현재 Core 기능

- AuthoritativeDocumentSet **ADS-CE-2026-CORE v1**에는 「2026년도 교육과정」 PDF 한 건만 있습니다. 현재 활성 버전은 **CRS-CE-2026-CORE v3**입니다. 기존 v2의 19개 실행 규칙과 정책 사실을 그대로 유지하고 교양 편성학기 데이터만 보강한 불변 스냅샷입니다. v1/v2와 과거 판정은 보존합니다. 새 공식 문서는 검증 후 새 버전으로 반영합니다.
- StudentState는 실제 이수, 학생 증빙, 적용 교육과정을 분리합니다. SQLite 속성 그래프의 허용된 조회와 Rule Engine이 DeterministicDecision을 만듭니다.
- RemainingRequirementSummary는 충족·미충족·정보 부족과 영역별 부족 학점을, CandidateCourse는 남은 요건에 연결되는 필수·선택 과목을 계산합니다. “앞으로 뭐 더 들어야 해?”에 대한 후보는 **졸업요건상 후보**이며 실제 다음 학기 개설이나 수강 가능 여부가 아닙니다.
- 과목 추가 simulation은 원래 StudentState를 바꾸지 않고 전후 요건·학점·판정 차이를 계산합니다. ExecutionTrace와 provenance는 실제 그래프 관계, 적용 Rule, 계산, PDF 페이지를 연결합니다.
- 공식 PDF의 **편성 학년·학기**를 과목 답변과 후보에 표시합니다. 학년·학기, 양 학기, 하계·동계 목록과 미이수 전필의 교집합을 결정적으로 조회합니다. 실제 개설·개인 수강 가능과 구분하며, 정보가 없는 과목은 확인 필요 목록에 남깁니다.
- 한국어 UI는 하나의 채팅방으로 구성했습니다. 첨부 파일은 대화 속 카드, 긴 이수기록 검토는 패널, StudentState JSON·로컬 LLM 설정은 상단 **학생 정보 · 설정**에 있습니다. 간결한 결론과 후보 개수를 먼저 보여주고, 답변별 **판단 근거 보기**에서 당시 학생 상태·전체 후보·관계·계산·PDF를 확인합니다. PDF/DOCX/PNG의 선택→추출→정정·확인→정규화→명시적 적용→질문 경로를 검증했습니다. HWP 5와 JPG/WEBP는 추출 경로가 있으나 자료 유형별 양성 검증은 완료되지 않았습니다.

## 판정 범위와 검증 상태

검증된 Core 범위는 **2026 컴퓨터공학과 국내 일반 학생의 단일전공**입니다. 적용 조건과 전체 이수·별도 증빙이 확인된 경우에만 해당 PDF·RuleSet 기준의 졸업 가능, 미충족, 정보 부족을 구분합니다. 합성 fixture의 VERIFIED는 실제 학생 증빙 검증을 뜻하지 않습니다. 과거 연도 학생의 전체 판정, 타 학과·다전공, 공식 동일·대체 지정, PDF 내부 GEA8617 코드 충돌은 지원 범위 제한 또는 공식 자료 확인 대상으로 남아 있습니다.

2026-09-30 **v2 데모 기준 재검증**: 전체 회귀 **215/215 PASS**, 실제 UI 시나리오 **10/10**, UI 안전 처리 반례 **4/4**, 학생용 실제 `/api/query` **100/100**와 Reviewer **4/4**, 독립 50문항 **49 PASS / 0 FAIL / 1 SKIP**, 모의 2026 PDF 업로드 E2E **4/4**입니다. LLM ON/OFF 핵심 판정·수치·요건·근거는 독립 문항 49/49, 학생 상태 10/10, 모의 PDF 4/4에서 일치했습니다. 상세 조건은 [v2 데모 검수 보고서](evaluation/results/core_v2_demo_baseline.md)에 있습니다. 과거 **191개** 결과는 [승인 요청서 평가 전 v1 baseline](evaluation/results/pre_approval_core_baseline_2026-09-30.md)의 역사적 기록입니다.

정책·과목 질문은 학생 입력 없이 바로 할 수 있습니다. 개인 판정에는 확인된 StudentState가 필요합니다. PDF 업로드만으로 적용 교육과정·전체 이수범위·논문/인증 증빙을 확정하지 않습니다. 알려진 제한과 공식 자료 대기(B)·사람 검토(C)는 [지원 범위](docs/design/core_scope.md)에 분리되어 있습니다. 평가 기록은 개발에 노출된 자료이므로 최초 블라인드 점수로 주장하지 않습니다.

2026-10-01 **채팅 UI 개편 검증**: 전체 회귀 **217/217 PASS**(기존 215개 유지), 학생용 실제 API **100/100**·반례 **4/4**, 독립 **49 PASS / 0 FAIL / 1 SKIP**, 모의 PDF E2E **4/4**를 재실행했습니다. 별도 합성 브라우저에서 파일 교체·학생 교체·과거 근거·늦은 응답·오류·초기화·360/390/768/1280px 화면을 확인했습니다. RuleSet과 결정적 판정 로직은 그대로입니다. [UI 검수 보고서](evaluation/results/chat_ui_acceptance_2026-10-01.md)에 실제 검증과 제한을 구분했습니다.

파일 선택·추출만으로 적용 학생과 대화가 바뀌지 않습니다. 학생 상태를 명시적으로 적용하면 교체하고 마지막 과목 참조를 초기화합니다. 이전 답변은 당시 결과를 유지합니다. **현재 페이지 메모리에서만 유지하며 새로고침하면 초기화됩니다.** 자동 저장이나 과거 채팅 복원은 없습니다.

2026-10-01 **편성정보 활용 검증(v3)**: 전체 회귀 **250/250 PASS**, 편성 전용 테스트 **33/33**, 실제 편성 `/api/query` **10/10** 및 로컬 LLM ON/OFF·반복·provenance 일치. 기존 학생용 API **100/100**·반례 **4/4**, 모의 PDF 업로드 **4/4**, 독립 **49 PASS / 0 FAIL / 1 SKIP**을 유지했습니다. PDF 262–264쪽과 교양 편성표 34–45쪽을 원문 대조했습니다. [검수 보고서](evaluation/results/curriculum_placement_acceptance.md)에 수정 전후 답변, 실제 브라우저 검수, 미확인 범위를 기록했습니다. 판정 규칙과 계산값은 v2와 같습니다.

## 실행과 테스트

Windows PowerShell과 Python 3.12 이상을 사용합니다. UI 상태 회귀 테스트에는 Node.js 18 이상도 필요합니다(서버 실행에는 필요하지 않음). python이 WindowsApps 별칭이면 CURRICULUM_PYTHON에 실제 인터프리터 경로를 지정하세요. Ollama와 qwen3:8b는 LLM 표현 기능을 사용할 때만 필요합니다.

~~~powershell
./scripts/serve.ps1 -Port 18473
# 브라우저: http://127.0.0.1:18473/
./scripts/demo_core.ps1
./scripts/run.ps1 ./tests/fixtures/structured_request.json
python -m unittest discover -s tests -q
~~~

합성 PDF 업로드 경로는 `python scripts/verify_mock_2026_pdf_e2e.py`, 남은 요건 경로는 `python scripts/verify_remaining_2026_e2e.py`, 학생용 표현은 `python scripts/verify_remaining_ux_2026.py`로 검증합니다. 실행 중인 서버의 데모 API 대조 자료는 `python scripts/verify_demo_v2_api.py --port 18473`으로 재생성합니다. 이 명령은 브라우저 검수까지 자동 통과시키지 않습니다.

편성정보 질문은 “고자구는 몇 학년 몇 학기에 편성돼?”, “3학년 1학기 전공 편성 과목”, “내 남은 전필 중 2학기 편성만”처럼 입력합니다. 앞의 두 질의는 학생 자료 없이 가능합니다. `python scripts/verify_curriculum_placement.py --port 18473`으로 현재 서버 경로를 재검증합니다. 기존 서버를 재시작해야 활성 v3를 읽습니다.

[데모 진행 안내](docs/demo/core_v2_demo.md)의 10개 시나리오를 사용할 수 있습니다. **학생 정보 · 설정 → 고급**의 JSON에는 공개 fixture의 **`student_state` 객체만** 붙여넣고 **학생 상태 적용**을 누르세요. 모든 공개 fixture와 모의 PDF는 실제 학생 자료가 아닙니다. 모델이 없으면 같은 설정 패널에서 로컬 LLM 체크를 끄고 결정적 경로를 실행할 수 있습니다. 기존 탭의 학생 자료를 보존하려면 새 탭에서 새 UI를 여세요.

## 저장소 구조와 자료 경계

| 경로 | 역할 |
| --- | --- |
| docs/curriculum/, docs/design/ | 공식 기준 PDF와 모델·아키텍처 문서 |
| data/raw/, data/processed/ | 추출 원자료와 출처가 연결된 검증 데이터·RuleSet 스냅샷 |
| src/, scripts/, tests/ | 애플리케이션, 실행·검증 도구, 자동 테스트 |
| evaluation/fixtures/, evaluation/results/ | 합성 fixture와 공개 가능한 검증 결과 |
| evaluation/reference/ | 평가 전용 원문. 공개·런타임 적재 금지 |
| logs/private/, uploads/, data/private/ | 로컬 전용 학생 자료·실행 결과. Git 제외 |

학생 업로드는 규칙 원천이 아닙니다. 평가 질문·정답도 그래프, RuleSet, 프롬프트, 별칭 데이터에 넣지 않습니다. 공개 전 테스트와 민감정보 검사를 통과한 완료 작업만 main에 반영합니다.
