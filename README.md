# Ontology Graph RAG Academic Advisor

*Ontology and Knowledge Graph based academic advisor with deterministic curriculum rule evaluation, explainable Graph RAG, and local LLM support.*

## 프로젝트 소개

이 프로젝트는 공식 교육과정의 과목·이수구분·졸업요건·적용 대상을 관계로 구조화하고 학생의 이수 상태를 검증합니다. 일반적인 PDF 문단 검색형 RAG만으로는 학점 합산, 필수과목 누락, 중복 인정과 적용연도 판단을 재현하기 어렵습니다. 따라서 **지식그래프는 사실과 관계를 조회하고, 결정적 Rule Engine은 조건을 계산**합니다. Graph RAG는 조회한 관계와 PDF 출처를 답변에 연결합니다.

로컬 LLM(qwen3:8b, 선택 사항)은 한국어 질문 해석과 검증된 결과의 문장 표현만 맡습니다. 졸업판정·학점·요건 상태는 LLM이 생성하지 않습니다. 모델을 끄거나 바꿔도 동일한 구조화 입력과 데이터·규칙 버전의 결정적 결과는 같아야 합니다.

## 현재 Core 기능

- AuthoritativeDocumentSet **ADS-CE-2026-CORE v1**에는 「2026년도 교육과정」 PDF 한 건만 있습니다. 검증된 규칙은 **CRS-CE-2026-CORE v1**에 고정됩니다. 새 공식 문서는 범위·시행·충돌 관계를 확인한 뒤 새 버전으로 반영하며 과거 판정은 당시 버전을 참조합니다.
- StudentState는 실제 이수, 학생 증빙, 적용 교육과정을 분리합니다. SQLite 속성 그래프의 허용된 조회와 Rule Engine이 DeterministicDecision을 만듭니다.
- RemainingRequirementSummary는 충족·미충족·정보 부족과 영역별 부족 학점을, CandidateCourse는 남은 요건에 연결되는 필수·선택 과목을 계산합니다. “앞으로 뭐 더 들어야 해?”에 대한 후보는 **졸업요건상 후보**이며 실제 다음 학기 개설이나 수강 가능 여부가 아닙니다.
- 과목 추가 simulation은 원래 StudentState를 바꾸지 않고 전후 요건·학점·판정 차이를 계산합니다. ExecutionTrace와 provenance는 실제 그래프 관계, 적용 Rule, 계산, PDF 페이지를 연결합니다.
- 한국어 채팅 UI는 간결한 결론과 요건별 후보 개수를 먼저 보여주고, 펼쳐보기에서 전체 후보·관계 그래프·규칙 계산·PDF 근거를 표시합니다. PDF/DOCX/PNG 업로드의 후보 추출→사용자 확인·정정→StudentState 정규화 경로를 검증했습니다. HWP 5와 JPG/WEBP 추출 경로는 구현되어 있으나 실제 자료 유형별 양성 검증은 완료되지 않았습니다.

## 판정 범위와 검증 상태

검증된 Core 범위는 **2026 컴퓨터공학과 국내 일반 학생의 단일전공**입니다. 적용 조건과 전체 이수·별도 증빙이 확인된 경우에만 해당 PDF·RuleSet 기준의 졸업 가능, 미충족, 정보 부족을 구분합니다. 합성 fixture의 VERIFIED는 실제 학생 증빙 검증을 뜻하지 않습니다. 과거 연도 학생의 전체 판정, 타 학과·다전공, 공식 동일·대체 지정, PDF 내부 GEA8617 코드 충돌은 지원 범위 제한 또는 공식 자료 확인 대상으로 남아 있습니다.

승인 요청서 평가 **이전 baseline**에서 전체 회귀 **191개 PASS**, 독립 50문항 **49 PASS / 0 FAIL / 1 SKIP**, 학생용 /api/query **100/100**, 1~4학년 합성 상태 질문 **70/70**, 모의 2026 PDF 업로드 E2E **4/4**가 기록되었습니다. 가능한 항목의 LLM ON/OFF 핵심 판정·수치·근거가 일치했습니다. 자세한 조건과 미완료 항목은 [baseline 보고서](evaluation/results/pre_approval_core_baseline_2026-09-30.md)와 [PLAN.md](PLAN.md)에 있습니다.

## 실행과 테스트

Windows PowerShell과 Python 3.12 이상을 사용합니다. python이 WindowsApps 별칭이면 CURRICULUM_PYTHON에 실제 인터프리터 경로를 지정하세요. Ollama와 qwen3:8b는 LLM 표현 기능을 사용할 때만 필요합니다.

~~~powershell
./scripts/serve.ps1 -Port 18473
# 브라우저: http://127.0.0.1:18473/
./scripts/demo_core.ps1
./scripts/run.ps1 ./tests/fixtures/structured_request.json
python -m unittest discover -s tests -q
~~~

합성 PDF 업로드 경로는 python scripts/verify_mock_2026_pdf_e2e.py, 남은 요건 경로는 python scripts/verify_remaining_2026_e2e.py, 학생용 표현은 python scripts/verify_remaining_ux_2026.py로 검증합니다. 이 스크립트의 옵션과 실행 환경은 [PLAN.md](PLAN.md)를 참고하세요. 공개 fixture는 실제 학생 자료가 아닙니다.

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
