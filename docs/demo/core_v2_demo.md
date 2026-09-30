# Core Prototype v2 데모 진행 안내

모든 데모 입력은 **테스트용 합성 학생이며 실제 학생 자료가 아니다**. 공식 증명서·학교 승인으로 설명하지 않는다. 기준은 `ADS-CE-2026-CORE v1`과 `CRS-CE-2026-CORE v2`다.

## 실행과 입력

1. PowerShell에서 `./scripts/serve.ps1 -Port 18473`을 실행하고 `http://127.0.0.1:18473/`을 연다.
2. 과목·정책 질문은 빈 상태로 시작한다. 개인 질문은 fixture의 `student_state` 객체만 학생 상태 JSON에 붙여넣는다. fixture 전체 객체를 붙여넣지 않는다.
3. 새 fixture로 바꿀 때 새 탭/새로고침으로 대화 맥락을 분리한다. 실제 학생 자료가 있는 탭은 데모에 사용하지 않는다.
4. 질문 후 기본 답변을 읽고 **판단 과정과 원문 근거 펼쳐보기**에서 적용 버전, Rule, 계산, 실제 관계, PDF 링크를 확인한다.

모델을 사용하려면 로컬 Ollama의 `qwen3:8b`가 필요하다. LLM 체크를 끄면 동일한 결정적 판정 경로를 실행한다. Python 경로가 다르면 `CURRICULUM_PYTHON`을 실제 Python 3.12 이상 경로로 지정한다.

## 대표 시나리오 10개

| ID | 입력 / 질문 | 데모 확인점 |
| --- | --- | --- |
| D01 | 학생 없음 / 고자구 몇 학점이야? | 고급자료구조 3학점, 2026 전공필수, PDF 262쪽 |
| D02 | 학생 없음 / 교양 47학점 취득한 경우 인정 한도는? | 인정 42·초과 제외 5, 계산과 PDF 33쪽 |
| D03 | `year1_early` / 지금 졸업 가능해? | 총 7·전공 6학점, 확인된 미충족 |
| D04 | 같은 상태 / 앞으로 뭐 더 들어야 해? | 필수 9과목, 부족량, 전공 31·교양 274 선택 후보를 개수로 요약 |
| D05 | 같은 상태 / 교양 뭐 더 들어야 해? | 교양 부족 33학점과 세부 영역별 후보·Rule 연결 |
| D06 | `year3_late` / 전공에서 남은 거 알려줘. | 총 102·전공 75, 전공 부족 3, 0학점 필수 2과목 |
| D07 | `required_missing` / 전필 뭐 남았어? | 총 131학점이어도 졸업논문(CDA0034)이 필수 후보로 남음 |
| D08 | 아래의 가정 전 기준 상태 / CDA0088 추가로 들으면 졸업 가능해? | 0학점 추가, 지정 필수 충족 변화, 졸업 미리보기 미충족→가능, 원본 보존 |
| D09 | `core_eligible_synthetic` / 지금 졸업 가능해? | 총 130·전공 96, 18개 적용 조건 충족·1개 비적용, PDF 기준 졸업 가능 |
| D10 | `mock_2026_missing_info.pdf` 업로드 / 지금 졸업 가능해? | 2쪽·43후보·42연결·1미확인, 적용·전체 범위 미확인으로 UNKNOWN |

`year1_early`, `year3_late`, `required_missing`은 `evaluation/fixtures/remaining_2026/`의 JSON이다. D09는 `tests/fixtures/core_eligible_synthetic.json`이다. D08은 D09를 별도 객체로 복사하고 이수기록 중 `CDA0088`만 제외한다. 실제 학생 객체를 변경하지 않는다:

```powershell
$demo = (Get-Content tests/fixtures/core_eligible_synthetic.json -Raw | ConvertFrom-Json).student_state
$demo.student_state_id = 'TEST-DEMO-V2-BOUNDARY'
$demo.course_attempts = @($demo.course_attempts | Where-Object course_id -ne 'CDA0088')
$demo | ConvertTo-Json -Depth 30
```

## 업로드와 자연스러운 시연 흐름

D10 파일은 `evaluation/fixtures/student_records/mock_2026_missing_info.pdf`다. 파일 선택→후보 추출→원문과 대조 가능한 42행만 확인하고 미확인 행은 보류→학생 정보와 2026 학점기준/과목표·단일전공 확인→StudentState 생성→질문 순서로 진행한다. 학생 정보 확인은 적용 증빙·전체 성적표·졸업인증 승인을 뜻하지 않는다. 그러므로 이 PDF만으로 졸업 가능이라고 판정하지 않는다.

D03→D04를 같은 학생 상태로 이어가면 결론→필수·부족 학점→선택 후보 수를 확인할 수 있다. D04의 펼쳐보기에서 후보 하나의 `SATISFIES`·Rule·PDF를 확인하고 `CDA0143 추가로 들으면 뭐가 바뀌어?`를 묻는다. 총 7→10·전공 +3 가정 후에도 실제 상태는 3개 이수기록·7학점을 유지한다. 다시 현재 졸업 여부를 물어 실제/가정 차이를 설명한다.

## 시연 범위와 제한

검증된 범위는 **2026 컴퓨터공학과 국내 일반 학생 단일전공**이며, 졸업 가능에는 전체 이수와 별도 증빙이 필요하다. 후보는 졸업요건상 선택지이며 순위·다음 학기 개설·선수과목·시간표를 보장하지 않는다. 타 학과/과거 전체 규칙·다전공 개인 판정·공식 동일/대체·원문 충돌·HWP 전체 양성 경로는 [Core 범위 문서](../design/core_scope.md)의 Extended/B/C 제한을 유지한다.

검수 결과와 재현 명령은 [v2 데모 baseline](../../evaluation/results/core_v2_demo_baseline.md)에 있다. 승인 요청서 질문·정답과 실제 학생 자료는 이 안내·fixture·런타임에 포함하지 않는다.
