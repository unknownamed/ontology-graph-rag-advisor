# 공식 문서 충돌 처리

## 충돌을 만드는 조건

같은 학생 범위에 적용될 수 있는 두 공식 출처가 서로 양립할 수 없는 요건을 제시하면 `RuleConflict`를 만든다. 충돌에는 ID, 기존 Rule 버전과 새 문서 후보, 영향 범위, 두 문서 ID, 원문 위치, 충돌 유형, `resolution_status=UNRESOLVED`, 미확인 `resolution_basis`를 남긴다. 별개 학과·전공 유형에 적용되는 수치를 같은 규칙의 충돌로 묶지 않는다.

새 문서의 `issued_at`이 늦다는 사실만으로 우선순위를 주지 않는다. `RESOLVED_BY_OVERRIDE`, `RESOLVED_BY_SCOPE`, `RESOLVED_BY_EFFECTIVE_DATE`, `RESOLVED_BY_OFFICIAL_CLARIFICATION`은 공식성·범위·시행/개정 관계·원문 근거가 확인된 별도 새 RuleSet에서만 사용한다. 기존 스냅샷을 소급 수정하지 않는다.

## 판정 안전장치

미해결 충돌의 범위가 학생과 겹치면 Core 졸업 결론을 `UNKNOWN`, 결정 상태를 `NEEDS_INFORMATION`으로 고정한다. 이미 확인된 개별 요건의 `UNSATISFIED`와 부족 정보는 `RequirementResult`에 남기되, 충돌 자체를 미충족으로 간주하지 않는다. `RULE_CONFLICT` 실행 이벤트는 실제 선택한 RuleSet의 충돌 ID, 양쪽 문서·출처 참조를 기록한다. 적용 범위가 겹치지 않는 충돌은 해당 학생의 Core 결론을 막지 않는다.

검토자는 새 문서의 해당 페이지·절, 기존 규칙의 근거, 적용 학생 범위, 시행시점 또는 개정 관계의 증빙을 확인해 해결한다. 모호한 OCR이나 LLM 요약만으로 `VERIFIED` 또는 우선 관계를 부여하지 않는다. 현재 v1에는 추가 공식 문서 충돌 객체가 없다. PDF 내부의 기존 `GEA8617` 코드 충돌은 별도 미확인 자료로 남아 있으며 이 문서 간 해결 모델이 자동으로 해소하지 않는다.
