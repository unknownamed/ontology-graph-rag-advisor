# 2026 Core 합성 PDF 업로드 E2E 검증

모든 자료는 테스트용 모의 성적표이며 실제 학생 자료가 아니다.

| fixture | PDF 후보/연결 | 원문학점 | PDF 단독 | 기대 | 실제 | LLM 일치 |
| --- | ---: | ---: | --- | --- | --- | --- |
| mock_2026_complete | 43/43 | 131 | UNKNOWN | ELIGIBLE_PDF | ELIGIBLE_PDF | PASS |
| mock_2026_partial | 28/28 | 74 | UNKNOWN | NOT_ELIGIBLE_PDF | NOT_ELIGIBLE_PDF | PASS |
| mock_2026_boundary | 42/42 | 131 | UNKNOWN | NOT_ELIGIBLE_PDF | NOT_ELIGIBLE_PDF | PASS |
| mock_2026_missing_info | 43/42 | 131 | UNKNOWN | UNKNOWN | UNKNOWN | PASS |

합성 학생 범위·논문·인증·동일과목 검토는 PDF에서 자동 추론하지 않고 테스트 fixture의 명시적 확인 입력으로 제공했다. 그러므로 PDF 단독은 4건 모두 UNKNOWN이다.

## mock_2026_complete

- 읽힌 페이지 2쪽, 후보 43건, 확정 연결 43건, 요건 상태 {"SATISFIED": 18, "NOT_APPLICABLE": 1}.
- 총 인정학점 131, 전공 인정학점 96; 부족 학점 {}, 미이수 필수 {}.
- 실행 EX-86dbddd91fbc3140: 실제 이벤트 109건, 관계 148개, 공식 PDF 근거 위치 8개.

## mock_2026_partial

- 읽힌 페이지 1쪽, 후보 28건, 확정 연결 28건, 요건 상태 {"UNSATISFIED": 6, "NOT_APPLICABLE": 1, "SATISFIED": 12}.
- 총 인정학점 74, 전공 인정학점 39; 부족 학점 {"R-CE-2026-ADVANCED-CREDITS": 33, "R-CE-2026-MAJOR-ELECTIVE-CREDITS": 3, "R-CE-2026-MAJOR-REQUIRED-CREDITS": 3, "R-CE-2026-MAJOR-TOTAL-CREDITS": 39, "R-GRAD-2026-TOTAL-CREDITS": 56}, 미이수 필수 {"R-CE-2026-REQUIRED-COURSES": ["CDA0143"]}.
- 실행 EX-a30d3f735a79f8d8: 실제 이벤트 80건, 관계 106개, 공식 PDF 근거 위치 8개.

## mock_2026_boundary

- 읽힌 페이지 2쪽, 후보 42건, 확정 연결 42건, 요건 상태 {"SATISFIED": 17, "NOT_APPLICABLE": 1, "UNSATISFIED": 1}.
- 총 인정학점 131, 전공 인정학점 96; 부족 학점 {}, 미이수 필수 {"R-CE-2026-REQUIRED-COURSES": ["CDA0034"]}.
- 실행 EX-5285df7f3cdfa019: 실제 이벤트 108건, 관계 148개, 공식 PDF 근거 위치 8개.

- 가정 과목 CDA0034: 졸업 상태 NOT_ELIGIBLE_PDF → ELIGIBLE_PDF; 학점 변화 0, 변경 요건 [{"rule_id": "R-CE-2026-REQUIRED-COURSES", "before": "UNSATISFIED", "after": "SATISFIED"}].

## mock_2026_missing_info

- 읽힌 페이지 2쪽, 후보 43건, 확정 연결 42건, 요건 상태 {"SATISFIED": 16, "NOT_APPLICABLE": 1, "NEEDS_INFORMATION": 2}.
- 총 인정학점 None, 전공 인정학점 96; 부족 학점 {}, 미이수 필수 {}.
- 실행 EX-930d5366099da836: 실제 이벤트 108건, 관계 145개, 공식 PDF 근거 위치 8개.
