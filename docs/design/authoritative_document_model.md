# 공식 규정 문서 모델

## 현행 기준 집합

`AuthoritativeDocumentSet → CurriculumRuleSet → 학생별 적용 RuleSet → DeterministicDecision`으로 기준을 고정한다. `ADS-CE-2026-CORE` v1은 `CURRICULUM-2026` 한 건만 포함한다. 파일 SHA-256은 `source_index.json`과 대조한다. 문서의 발행기관, 발행일, 시행일, 종료일, 개정 표기는 현재 원문 확인 범위에서 확정하지 않았으므로 `null`과 `metadata_missing`으로 둔다. `verification_status=VERIFIED`는 **파일 정체성과 현재 구조화 사실의 원문 대조**를 뜻하며 누락 메타데이터를 확인했다는 뜻이 아니다.

`AuthoritativeDocument`는 ID, 제목, 유형, 발행기관, 발행·시행 기간, 개정, 원본 경로/해시, `verification_status`, `authority_status`, `ingestion_status`, 공식성 확인 근거를 가진다. 상태는 `AUTHORITATIVE | NON_AUTHORITATIVE | EVALUATION_ONLY | USER_UPLOADED_CONTEXT`로 분리한다. 평가 승인 요청서는 `evaluation/document_registry.json`에서 `EVALUATION_ONLY`로 표기하며 런타임의 공식 문서집합에는 적재하지 않는다. 파일 내용과 해시는 이번 모델 생성에 사용하지 않는다.

## 추가 문서의 검토 경로

`stage_official_document.py`는 PDF 또는 UTF-8 텍스트의 서명/해시를 확인하고 원문 텍스트와 유형 후보를 `data/raw/authority_staging/`에 저장한다. 현행 요건의 출처 제목과 겹치는 어휘는 **UNVERIFIED 관련 후보**로만 표시한다. 파일명, 추출 텍스트, LLM 제안으로 공식성이나 규칙을 확정하지 않는다.

검토자가 문서의 공식성 근거, 적용 범위, 문서 관계, 원문 위치, 규칙 변경을 명시한 review JSON을 만들면 `publish_official_ruleset.py`가 이를 검증한다. 검증된 문서만 새 집합 버전에 들어간다. 기존 문서 메타데이터와 과거 스냅샷은 수정하지 않는다. 새 `source_locators[]`는 `verification_status=VERIFIED`, `source_document_id`, `source_hash`, PDF 페이지/절을 가져야 하며 각 규칙의 `supporting_evidence[]`와 일치해야 한다. 문서 관계도 새 문서의 검증된 locator를 하나 이상 인용해야 한다. 학생 업로드는 이 경로에 들어가지 않는다.

## 문서 관계

`SUPPLEMENTS`, `CLARIFIES`, `OVERRIDES`, `CONFLICTS_WITH`, `APPLIES_TO`, `SUPERSEDES`는 문서 ID 양쪽, 영향 범위, 검증 상태, 출처 위치를 가진다. `OVERRIDES`와 `SUPERSEDES`에는 공식성, 범위 겹침, 시행/개정 관계와 그 근거가 모두 필요하다. 후발 문서라는 이유만으로 기존 규칙을 덮어쓰지 않는다. 실제 추가 공식 문서는 아직 등록하지 않았다.
