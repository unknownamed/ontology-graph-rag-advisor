# Core v4 원문 의미 정정 검증

2026-10-01. ADS-CE-2026-CORE v1 / CRS-CE-2026-CORE v4. 기존 공식 교육과정만 사용했으며 실제 학생과 승인 요청서는 이번 검증에 사용하지 않았다.

| 검증 | 실제 결과 |
| --- | --- |
| 전체 회귀 (기존250 + 신규47) | 297/297 PASS, 28.585초 |
| Builder 원문 의미 API / Reviewer 반례 | 19/19 · 28/28 PASS |
| 새 실제 API·qwen3:8b ON/OFF | 14/14 PASS, 판정·요건·수치·근거·trace 일치 |
| 독립50 회귀 / Reviewer | 49 PASS · 0 FAIL · 1 SKIP / 31/31 PASS |
| 학생용 질문 / UX 반례 | 100/100 · 4/4 PASS |
| 모의 PDF 실제 추출→판정 | 4/4 PASS, LLM4/4 일치 |
| 편성 API | 10/10 PASS, LLM·반복·근거 일치 |
| 별도 합성 브라우저 | 정책·면제보충 판정·후보·연도비교·초과학제5흐름 확인 |
| 공개 전 검사 | 변경32개 파일의 민감정보·제외 경로·staged v4 해시·원본/과거 버전 보존 PASS |

PDF33·42·45 등의 이미지 대조, 실제 그래프/Rule/출처 검증, 원본 입력·v1/v2/v3 버전 보존을 포함한다. API 및 원문 의미 기대값과 수정 전후는 [정정 보고서](../../docs/design/source_accuracy_corrections.md), 새14문항 실행 요약은 [API 기록](source_accuracy_v4_api_summary.json)에서 확인한다. 기존 평가 결과를 덮어쓰지 않았다. 이전 평가세트 재실행을 새 블라인드 평가라고 주장하지 않는다.

**Quality Gate: 이번 결함 수정 범위 PASS.** 인증 세부 직접 계산, 초과학제 등록/재입학·전과 상세 적용, 과거 전체 RuleSet·공식 동일/대체 지정 및 원문 충돌은 여전히 제한이다. 전체 PDF의 모든 세부 구현 완료로 확대하지 않는다. 같은 작업자의 Builder/Reviewer/Verifier 관점별 검토이며 외부 독립 검수는 아니다.
