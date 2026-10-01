# 교육과정 편성 학년·학기

## 의미와 경계

| 정보 | 현재 근거와 상태 | 사용 |
| --- | --- | --- |
| 교육과정상 편성 | 공식 PDF의 편성표 셀과 각주 | 과목 안내, 학년·학기 필터, 남은 요건 후보 묶기 |
| 특정 연도·학기의 실제 개설 | 자료 없음: `NOT_VERIFIED` | 개설을 보장하지 않음 |
| 학생의 실제 수강 가능 | 선수조건·시간표·수강 제한 자료 없음: `NOT_VERIFIED` | 수강 가능을 보장하지 않음 |

편성 학년은 권장·편성 위치이지 수강 제한 규칙이 아니다. 편성정보 부족은 졸업 미충족 조건이 아니다. 학생 입학연도나 현재 날짜로 다음 학기를 추측하지 않는다.

## 원문 검증과 보강

- 컴퓨터공학과 43행: PDF 262–263쪽(인쇄 254–255), 편성 학년·학기 셀과 병합 구획, `※ 부전공 필수` 각주 대조. PDF 264쪽의 기존 경과조치를 편성 제한으로 바꾸지 않는다.
- 전공 표 하단 계수: 1학기만 15, 2학기만 16, 양 학기 8, 하계·동계 4. 양 학기 과목은 각각의 목록에 포함되지만 고유 과목 수는 43이다.
- 교양 편성표 PDF 34–45쪽(인쇄 26–37): 기존 카탈로그 280개 행에 누락된 개설학기 원문 셀을 추가한다. 이 표에는 편성 **학년 열이 없다**. `개설학기`라는 표 머리글은 해당 교육과정의 편성정보로 기록하며 특정 연도의 실시간 개설 확정으로 해석하지 않는다.
- GEA8694(35쪽), GEA8818·GEA8689(45쪽)의 원문 `이룸`은 그대로 보존한다. 학기 매핑은 `UNVERIFIED`다. GEA8617의 두 이름 충돌은 기존 `known_conflicts`에 보존하며 카탈로그 적재에서 제외한다.
- `data/processed/curriculum_placement_2026.json`은 교양 셀·페이지·원문 상태·PDF 해시의 검토 기록이다. 자동 추출 후 위 전체 페이지를 렌더링해 직접 대조했다. 자동 추출만으로 VERIFIED로 승격하지 않는다.

## 계약과 정규화

기존 `CatalogEntry.grade_term`과 교양의 `placement_term_raw`를 보존한다. `placement.py`가 조회된 원문으로 다음 읽기 전용 투영을 만든다.

```json
{
  "normalization_version": "1",
  "curriculum_id": "CURRICULUM-CE-2026",
  "raw_grade_term": "2-2",
  "raw_term": null,
  "grade_scope": "LIST",
  "grades": [2],
  "slots": [{"grade": 2, "grade_scope": "LIST", "term": "SEMESTER_2"}],
  "term_verification_status": "VERIFIED",
  "grade_verification_status": "VERIFIED",
  "fact_id": "CE-2026-COURSE-CDA0143",
  "source": {"document_id": "CURRICULUM-2026", "pdf_page": 262, "printed_page": 254},
  "actual_offering_status": "NOT_VERIFIED",
  "student_eligibility_status": "NOT_VERIFIED"
}
```

- `전-1,2`는 명시적 `ALL` 학년과 두 정규학기, `2·3·4-하·동`은 해당 학년과 두 계절학기다.
- 복수 조합은 각 `slot`의 쌍을 보존한다. `1-1;2-2`를 1학년 2학기로 확대하지 않는다(이 문자열은 정규화 경계용 TEST FIXTURE).
- 공란은 `MISSING`, 해석 불가 셀은 `UNVERIFIED`; 교양의 학년 미기재는 학기 VERIFIED와 별도다. 누락을 전 학년·전 학기로 채우지 않는다.
- 원문 과목/편성 셀이 미검증·충돌 상태면 읽을 수 있는 문자열이라도 확정 필터 결과로 승격하지 않는다.

## 조회와 후보

`PLACEMENT_LOOKUP`은 StudentState 없이 허용한다. 서버 소유 QueryPlan이 기존 `FETCH_CATALOG_SET`으로 교육과정·분류를 조회한 후 `FILTER_CURRICULUM_PLACEMENT`와 `GROUP_CURRICULUM_PLACEMENT`를 실행한다. 필터는 `grade: 1..4`, `terms: SEMESTER_1 | SEMESTER_2 | SUMMER | WINTER`, `term_match: ANY | ALL`만 받는다. 지원하지 않는 학과·교육과정·학년과 자유 쿼리는 실행하지 않는다.

개인별 질의는 기존 `REMAINING_PLAN`의 전체 요건·후보를 계산한 뒤 요청한 과목 분류·편성조건에 맞는 `placement_view`를 별도로 만든다. `REQUIRED/ELIGIBLE_OPTION`과 요청 조건의 교집합만 표시한다. 전체 부족 학점·필수 목록·졸업판정은 필터로 바꾸지 않는다. 이미 이수한 과목은 추천하지 않는다.

선택 결과는 `matched_course_ids`, `needs_verification_course_ids`, `excluded_course_ids`로 나눈다. 학기/학년이 부족한 후보는 확인 필요 목록에서 접근 가능하다. `다음 학기` 기준 미지정이면 `next_term_basis: UNSPECIFIED`로 학기별 편성만 제공한다. 후보는 필수/선택 구분 안에서 코드순이며 수강 추천 순위가 아니다.

## 근거와 UI

`CandidateCourse`에 원문 `grade_term`, `curriculum_placement`, 수강 가능 확인 상태를 전달한다. 편성표 출처와 기존 `HAS_ENTRY → FOR_COURSE / CLASSIFIED_AS → SATISFIES` 관계를 재사용한다. 새 학기 노드는 필요하지 않다.

실제로 읽은 CatalogEntry 전체를 EvidenceBundle에 넣고 `PLACEMENT_SELECTION` 이벤트에 입력 entry ID, 필터, 일치/보류/제외 결과를 기록한다. verifier가 원문 투영·후보·필터 결과·이벤트를 재대조한다. UI는 학기별 전체 목록과 PDF 링크를 지연 표시하고, 관계 그림은 실제 반환 관계 중 최대 12개 편성 과목/후보 연결임을 알린다. 전체 근거 JSON은 계속 접근 가능하다.

## 버전과 재현

활성 ADS v1은 그대로다. 데이터 변경은 불변 **CRS-CE-2026-CORE v3**에 저장한다. v1/v2 스냅샷은 수정하지 않으며 19개 실행 규칙·요구값·policy facts·적용 범위는 v2와 같다. migration은 신규 편성 필드만 허용하고 기존 과목/규칙 변경을 거부한다. 서버 시작 시 활성 버전에 고정되고 과거 Decision은 당시 버전을 보존한다. 기존 실행 서버는 재시작 전의 버전을 사용한다.

```powershell
python scripts/refine_curriculum_placement.py  # 검토 기록을 적용; 재실행 시 변경 없음
python scripts/verify_curriculum_placement.py --port 18473
python -m unittest discover -s tests -p test_curriculum_placement.py -q
```
