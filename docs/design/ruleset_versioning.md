# RuleSet 버전과 판정 재현

## 현재 v1

`CRS-CE-2026-CORE` v1은 공식 문서집합 `ADS-CE-2026-CORE` v1의 VERIFIED 2026 컴퓨터공학과 요건을 고정한다. 과거 연도 과목별 기준, 다전공 전체 판정, 공식 동일·대체 지정 쌍, 원문 내부 충돌은 v1의 Core 판정 범위에 포함되지 않는다. 학생별 적용 ID는 학과, 학점·과목표 연도, 전공 유형 등의 확인된 조건으로 좁힌다. 범위가 불명확하면 요건을 미충족으로 처리하지 않는다.

`RuleSetStore`는 완전한 카탈로그를 내용 해시가 붙은 JSON 스냅샷으로 저장하고 `active.json`을 원자적으로 바꾼다. 로드할 때 파일 내용, 파일명 해시, 공식 원본 해시를 다시 검사한다. `serve.py`는 활성 버전을 로드한다. v1 스냅샷은 새 버전 활성화 뒤에도 `load_version(1)`로 재실행할 수 있다. `archive_decision`은 명시적으로 호출한 경우에만 결정·실행 기록을 서로 다른 파일로 보존한다. 실제 학생 상태는 자동 저장하지 않으므로 과거 판정 재현에는 그 당시 정규화된 학생 입력도 필요하다.

## 규칙 계보와 변경

규칙은 안정된 `rule_id`와 별도의 `rule_version`을 가진다. `SUPPLEMENTS`는 새 ID를 추가하고 기존 규칙을 유지한다. `CLARIFIES`는 의미·요구값을 그대로 두고 새 공식 출처를 연결한 다음 버전을 만든다. 검증된 `OVERRIDES`만 요구값 등을 바꾼 다음 버전을 만들며 `supersedes`와 `rule_lineage`에 이전 버전을 남긴다. `CONFLICTS_WITH` 후보는 기존 규칙을 바꾸지 않고 `unresolved_conflicts`에 남긴다. 새 문서가 Core와 무관해도 문서집합과 RuleSet 버전은 증가하지만 Core 결과는 변하지 않는다.

현재 그래프는 한 Rule ID에 동시에 한 실행 버전만 적재한다. 따라서 기존 규칙의 **적용 범위 일부만** 명확화·대체하는 문서는 다른 학생의 기준을 지우지 않도록 자동 발행을 거부한다. 이런 경우 범위별 규칙 분할과 별도 원문 검증을 구현하거나 미해결 충돌로 유지해야 한다. 범위가 정확히 같은 검증된 대체는 v2로 발행할 수 있다.

모든 `DeterministicDecision`과 `ExecutionTrace`는 문서집합 ID·버전, RuleSet ID·버전, 학생 상태 해시를 포함한다. `compare_decisions`는 같은 학생 상태의 두 실행에서 추가/변경 규칙, 요건 상태, 최종 결론, 변경된 규칙의 출처 문서를 비교한다. 서로 다른 학생 상태의 비교는 거부한다. 화면의 펼쳐보기는 실행에 고정된 문서와 RuleSet 버전을 표시한다.

## 운영 명령

`python scripts/stage_official_document.py --file <공식문서.pdf> --id <문서ID> --title <제목> --type OFFICIAL_NOTICE`는 **검토 대기 후보만** 만든다. 검토 후 `python scripts/publish_official_ruleset.py --review <review.json>`으로 검증된 관계·출처·변경을 포함한 새 버전을 활성화한다. 이후 서버를 재시작한다. 승인 요청서와 학생 업로드는 이 경로에서 거부된다. 공식 문서가 추가로 존재하지 않아 현재 활성 버전은 v1이다.
