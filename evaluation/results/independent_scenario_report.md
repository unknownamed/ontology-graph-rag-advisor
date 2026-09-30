# 독립 50문항 사용자 시나리오 평가

- 질문세트: `evaluation\core_scenarios\독립_검증_질문세트_50문항.json` (SHA-256 `1d38df8647c1f3d4ac6d2754ede66018540fbff342a64520a2edce2cebd1ca73`)
- 실제 `/api/query` 경로 결과: PASS 49 / FAIL 0 / SKIP 1
- 수정 전 보존 결과: PASS 33 / FAIL 16 / SKIP 1 (`independent_scenario_results_before.json`)
- 목표가 확정되지 않은 가정 질문 5건: 현재 상태만 확인하고 가상 수치 계산은 보류 (SIM_03, SIM_04, SIM_05, SIM_08, CTX_05)
- LLM ON/OFF 일치: {'True': 49}
- 동일 입력 반복: {'True': 49}; 이수 입력 순서: {'True': 40}
- PDF 출처 확인: {'True': 49}
- Reviewer 반례 전체: 31/31 PASS (이번 수정에서 추가한 반례: 16/16)
- 평가자료 누수 정적 검사: PASS

- PDF 원문 수치 행 대조: True / True
- 같은 fixture·의도 표현 비교: 6/6 비교 가능 쌍 일치; 0쌍은 질문 해석 실패로 비교 불가

## 범주별 결과

| 범주 | PASS | FAIL | SKIP | 통과율(PASS/전체) |
| --- | ---: | ---: | ---: | ---: |
| boundary | 8 | 0 | 0 | 8/8 |
| compound | 2 | 0 | 1 | 2/3 |
| context | 2 | 0 | 0 | 2/2 |
| direct_fact | 8 | 0 | 0 | 8/8 |
| explainability | 3 | 0 | 0 | 3/3 |
| natural_language | 8 | 0 | 0 | 8/8 |
| simulation | 8 | 0 | 0 | 8/8 |
| student_state | 8 | 0 | 0 | 8/8 |
| unsupported_scope | 2 | 0 | 0 | 2/2 |

## 실패 유형별 수정 전후

| 유형 | 수정 전 FAIL | 수정 후 FAIL |
| --- | ---: | ---: |
| entity_resolution_error | 8 | 0 |
| insufficient_information_error | 2 | 0 |
| intent_error | 4 | 0 |
| unsupported_scope_error | 2 | 0 |

## 실패와 SKIP

| ID | 상태 | 유형 | 이유 |
| --- | --- | --- | --- |
| CTX_04 | SKIP | insufficient_information_error | A missing semester cannot prove the named required course is absent without independent official evidence |

## 신규 Reviewer 반례

| ID | 반례 | 결과 |
| --- | --- | --- |
| REV_01 | Conflicted attempt ID | PASS |
| REV_02 | Same course in different attempts | PASS |
| REV_03 | Missing official equivalence review evidence | PASS |
| REV_04 | Missing student-category evidence | PASS |
| REV_05 | Different catalog version | PASS |
| REV_06 | Unverified completion record | PASS |
| REV_07 | Zero-credit required course missing | PASS |
| REV_08 | Known false official outcome plus incomplete transcript | PASS |
| REV_09 | Official residual overlaps curriculum course | PASS |
| REV_10 | Official residual one credit above threshold | PASS |
| REV_11 | Unreviewed academic event | PASS |
| REV_12 | Zero-credit scenario changes rule, not credits | PASS |
| REV_13 | Unknown Korean course name is not invented | PASS |
| REV_14 | Mixed current and unspecified simulation asks for target | PASS |
| REV_15 | Verified prior entity survives a follow-up simulation | PASS |
| REV2_01 | Required-only catalog count | PASS |
| REV2_02 | Elective-only catalog credit sum | PASS |
| REV2_03 | Old catalog cannot inherit 2026 aggregate | PASS |
| REV2_04 | Unimplemented general catalog sum cannot become minimum | PASS |
| REV2_05 | Two explicit courses produce one hypothetical state | PASS |
| REV2_06 | Repeated explicit target is not double credited | PASS |
| REV2_07 | Two missing required candidates stay ambiguous | PASS |
| REV2_08 | No missing zero-credit course is invented | PASS |
| REV2_09 | Verified flag does not repair missing course identity | PASS |
| REV2_10 | Verified unmet and unknown transcript coexist | PASS |
| REV2_11 | Unknown code with Korean particle stays unverified | PASS |
| REV2_12 | Unknown explicit simulation target is not invented | PASS |
| REV2_13 | New explicit course overrides previous context | PASS |
| REV2_14 | Trace explanation cites only executed rules | PASS |
| REV2_15 | Order invariance includes official residual records | PASS |
| REV2_16 | Unknown explicit code overrides remembered course | PASS |

## Builder → Reviewer → Verifier → Quality Gate

- **Builder:** 질문세트 50개를 각각 실제 `/api/query` 사용자 문장 경로로 실행하고, fixture는 기존 합성 입력과 VERIFIED 카탈로그·요건에서 생성했다. HTTP 실패·해석 실패도 FAIL로 보존했다.
- **Reviewer:** 질문세트 밖의 상태·경계·모호성·맥락 반례 31개를 API로 실행했다. 31개 통과했다.
- **Verifier:** 실제 `QUERY_PLAN`·`GRAPH_QUERY`·`RULE_EVALUATION` 이벤트와 EvidenceBundle·RequirementResult·Decision·AnswerPayload를 대조했다. 원문 PDF 해시, 과목코드 인용 페이지, 261·577쪽 학점표도 별도 확인했다.
- **Quality Gate: PASS.** 독립 질문 50건 중 실행 가능한 49건의 API 경로, 새 Reviewer 반례, 출처 및 LLM 불변 검사가 통과했다. 목표 과목이 없는 가정 질문의 PASS는 수치 시뮬레이션 성공이 아니라 안전한 부분 답변을 뜻한다. CTX_04는 누락 학기에 특정 필수과목을 이수하지 않았다는 공식 증거가 없어 SKIP으로 유지한다.


## 판정 기준

질문세트의 개념적 의도는 `INTENT_FAMILIES`의 일반 의미군으로 현재 API 의도와 비교했다. 단순 문장 일치나 Rule Engine 직접 호출은 PASS 근거가 아니다.
기대 학점 기준은 VERIFIED 카탈로그의 졸업 요건값과 합성 fixture에서 유도했다. 출처는 교육과정 PDF의 SHA-256, 반환된 원문 페이지 및 실제 조회·규칙 이벤트와 대조했다. 독립 시나리오 평가기는 승인 요청서를 입력으로 사용하지 않았다. 상세 API 응답과 모든 검사는 JSON 결과 파일을 참조한다.
