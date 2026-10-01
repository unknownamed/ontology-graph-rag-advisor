"""Source-semantic regressions: PDF 13, 33, 42/45, 264, 565/569.

Expected amounts are independently transcribed from those pages, not produced
by the engine. All personal inputs are copies of the public synthetic fixture.
"""
from __future__ import annotations

import json
import sys
import threading
import unittest
import urllib.request
from copy import deepcopy
from http.server import HTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'scripts')]
from curriculum_assistant.authority import RuleSetStore
from curriculum_assistant.graph import Graph
from curriculum_assistant.server import Handler
from curriculum_assistant.verifier import verify_payload


def complete():
    return json.loads((ROOT / 'tests/fixtures/core_eligible_synthetic.json').read_text(encoding='utf-8'))['student_state']


def outcome(value, status='VERIFIED'):
    return {'value': value, 'verification_status': status, 'evidence_id': 'SYNTHETIC-SOURCE-COUNTEREXAMPLE'}


def waived(replace=True):
    s = complete()
    s['course_attempts'] = [a for a in s['course_attempts'] if a['course_id'] != 'GEA8704']
    s['official_outcomes']['english_course_exemption'] = outcome(True)
    if replace:
        # PDF 34: AI융합아카데미, 균형교양, 2 credits. Not actual student data.
        s['course_attempts'].append({'attempt_id': 'SYNTHETIC-REPLACEMENT-GE', 'course_id': 'GEA8801',
            'earned_credits': 2, 'completion_status': 'COMPLETED', 'verification_status': 'VERIFIED',
            'evidence_id': 'SYNTHETIC-REPLACEMENT-GE-EVIDENCE'})
    return s


def rule(p, suffix):
    return next(r for r in p['requirement_results'] if r['rule_id'].endswith(suffix))


class SourceAccuracyAPI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = RuleSetStore(ROOT / 'data/processed/ruleset_versions').load_active()
        class Bound(Handler):
            pass
        cls.server = HTTPServer(('127.0.0.1', 0), Bound)
        ready = threading.Event()
        def run():
            graph = Graph(Path(':memory:'), cls.catalog)
            Bound.graph = graph
            ready.set()
            try:
                cls.server.serve_forever()
            finally:
                graph.close()
        cls.thread = threading.Thread(target=run, daemon=True)
        cls.thread.start()
        assert ready.wait(10)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.thread.join(10)
        cls.server.server_close()

    def ask(self, question, student=None, **extras):
        request = {'utterance': question, 'use_local_llm': False, **extras}
        if student is not None:
            request['student_state'] = student
        req = urllib.request.Request(f'http://127.0.0.1:{self.server.server_port}/api/query',
            data=json.dumps(request, ensure_ascii=False).encode(), headers={'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                result = json.load(r)
        except urllib.error.HTTPError as e:
            self.fail(e.read().decode())
        if 'decision' in result:
            verify_payload(result)
        return result

    def test_no_exemption_ordinary_english_completion(self):
        p = self.ask('지금 졸업 가능해?', complete())
        self.assertEqual('ELIGIBLE_PDF', p['decision']['graduation_outcome'])
        self.assertEqual(9, rule(p, 'BASIC-CREDITS')['required'])

    def test_waiver_other_general_supplement_is_sufficient(self):
        s = waived(); original = deepcopy(s)
        p = self.ask('지금 졸업 가능해?', s)
        self.assertEqual('ELIGIBLE_PDF', p['decision']['graduation_outcome'])
        self.assertEqual(130, p['credited_amount']['total'])
        self.assertEqual(7, rule(p, 'BASIC-CREDITS')['required'])
        self.assertEqual(7, rule(p, 'BASIC-CREDITS')['observed'])
        self.assertEqual(34, p['credited_amount']['by_area']['GENERAL_TOTAL'])
        self.assertEqual(original, s)

    def test_waiver_does_not_award_credits_without_supplement(self):
        p = self.ask('지금 졸업 가능해?', waived(False))
        self.assertEqual('NOT_ELIGIBLE_PDF', p['decision']['graduation_outcome'])
        self.assertEqual('SATISFIED', rule(p, 'BASIC-CREDITS')['status'])
        self.assertEqual(128, p['credited_amount']['total'])
        self.assertEqual(2, rule(p, 'GE-2026-TOTAL-CREDITS')['missing_amount'])

    def test_unknown_waiver_cannot_lower_a_confirmed_minimum(self):
        s = waived(); s['official_outcomes']['english_course_exemption'] = outcome(True, 'UNVERIFIED')
        p = self.ask('지금 졸업 가능해?', s)
        self.assertEqual('UNKNOWN', p['decision']['graduation_outcome'])
        self.assertEqual('NEEDS_INFORMATION', rule(p, 'BASIC-CREDITS')['status'])
        self.assertEqual('NEEDS_INFORMATION', rule(p, 'GE-2026-ENGLISH')['status'])

    def test_waiver_does_not_exempt_writing(self):
        s = waived(); s['course_attempts'] = [a for a in s['course_attempts'] if a['course_id'] != 'GEA8512']
        p = self.ask('어떤 요건이 부족해?', s)
        self.assertEqual('UNSATISFIED', rule(p, 'GE-2026-WRITING')['status'])

    def test_waiver_and_remaining_candidates_are_consistent(self):
        p = self.ask('앞으로 뭐 더 들어야 해?', waived(False))
        active = [c for c in p['decision']['candidate_courses'] if c['candidate_status'] in ('REQUIRED','ELIGIBLE_OPTION')]
        self.assertNotIn('R-GE-2026-ENGLISH', {r for c in active for r in c['satisfies_requirement_ids']})
        self.assertTrue(any(c['course_classification'] in ('GENERAL_BALANCED','GENERAL_EXPANDED') for c in active))
        self.assertEqual(2, p['decision']['remaining_requirements']['missing_credits_by_category']['GENERAL_TOTAL'])

    def test_exam_threshold_policy_without_student_does_not_grant_exemption(self):
        p = self.ask('토익 700점이면 대학영어 면제 기준을 충족해?')
        self.assertEqual('POLICY_LOOKUP', p['decision']['intent'])
        self.assertIn('700', p['answer_text'])
        self.assertIn('공식 면제', p['answer_text'])
        self.assertEqual('NOT_REQUESTED', p['decision']['graduation_outcome'])
        self.assertTrue(any(f['predicate'] == 'ENGLISH_COURSE_EXEMPTION' for f in p['evidence']['policy_facts']))

    def test_credit_policy_year_phrasings_not_replaced_by_2026(self):
        for q in ('2022 교육과정 적용자의 전공선택과 교양 최소학점은?',
                  '2022년도 기준 교양과 전공선택 학점은?', '2022학번 컴공 경과조치 학점은?'):
            with self.subTest(q=q):
                p = self.ask(q)
                self.assertIn('26', p['answer_text']); self.assertIn('57', p['answer_text'])
                self.assertNotIn('교양: 최소 34', p['answer_text'])
                self.assertNotEqual('APPLICABILITY_CHOICE', p['interpretation']['structured_query'].get('policy_focus'))

    def test_range_retains_applicable_years(self):
        p = self.ask('2021~2024 교육과정 적용자의 교양과 전공선택 기준은?')
        scopes = p['interpretation']['structured_query']['year_targets']
        self.assertEqual([2021,2022,2023,2024], [s['year'] for s in scopes])
        self.assertIn('57', p['answer_text']); self.assertNotIn('교양: 최소 34', p['answer_text'])

    def test_explicit_year_comparison_is_not_ambiguous(self):
        p = self.ask('2022와 2026 교육과정의 교양 최소학점을 비교해줘.')
        self.assertEqual('POLICY_LOOKUP', p['decision']['intent'])
        rows = p['decision']['lookup_result']['year_comparison']
        self.assertEqual([2022,2026], [r['target']['year'] for r in rows])
        self.assertIn('26', p['answer_text']); self.assertIn('34', p['answer_text'])

    def test_unsupported_year_never_uses_2026_thresholds(self):
        p = self.ask('1998년도 기준 교양 최소학점이 얼마야?')
        self.assertNotIn('34학점', p['answer_text'])
        self.assertEqual('NEEDS_INFORMATION', p['decision']['lookup_status'])

    def test_question_year_cannot_overwrite_actual_student(self):
        s = complete(); saved = deepcopy(s)
        p = self.ask('2022학번인 내 졸업 가능 여부를 확인해줘.', s)
        self.assertEqual('UNKNOWN', p['decision']['graduation_outcome'])
        self.assertTrue(any(n.startswith('QUESTION_STUDENT_SCOPE_CONFLICT') for n in p['needs_information']))
        self.assertEqual(saved, s)

    def test_internal_review_is_not_a_new_universal_school_obligation(self):
        s = complete(); s.pop('equivalence_review_status',None); s.pop('equivalence_review_evidence_id',None)
        p = self.ask('지금 졸업 가능해?', s)
        self.assertEqual('ELIGIBLE_PDF', p['decision']['graduation_outcome'])
        self.assertNotIn('OFFICIAL_EQUIVALENCE_REVIEW', p['needs_information'])

    def test_relevant_unhandled_condition_blocks_positive_outcome(self):
        s = complete(); s['exceeded_standard_duration'] = True; s['current_semester_registered_credits'] = 0
        p = self.ask('지금 졸업 가능해?', s)
        self.assertEqual('UNKNOWN', p['decision']['graduation_outcome'])
        self.assertFalse(p['decision']['coverage_complete'])
        self.assertTrue(p['decision']['coverage_details']['unhandled_conditions'])

    def test_irrelevant_metadata_does_not_force_unknown(self):
        s = complete(); s['nickname'] = '합성 테스트'; s['year_label'] = 1
        p = self.ask('지금 졸업 가능해?', s)
        self.assertEqual('ELIGIBLE_PDF', p['decision']['graduation_outcome'])

    def test_declared_disability_not_treated_as_certification_failure(self):
        s = complete(); s['disability_status'] = True
        s['official_outcomes']['graduation_certification_passed'] = outcome(False)
        p = self.ask('지금 졸업 가능해?', s)
        self.assertEqual('NEEDS_INFORMATION', rule(p, 'GRAD-2026-CERTIFICATION')['status'])
        self.assertEqual('UNKNOWN', p['decision']['graduation_outcome'])

    def test_official_result_path_is_explicitly_not_subrule_calculation(self):
        p = self.ask('지금 졸업 가능해?', complete())
        cert = rule(p, 'GRAD-2026-CERTIFICATION')
        self.assertEqual('OFFICIAL_RESULT_INPUT', cert['evaluation_basis'])
        self.assertFalse(p['decision']['coverage_details']['certification_subrules_computed'])

    def test_known_deficit_and_unknown_condition_both_preserved(self):
        s = complete(); s['exceeded_standard_duration'] = True
        s['course_attempts'] = [a for a in s['course_attempts'] if a['course_id'] != 'CDA0016']
        p = self.ask('지금 졸업 가능해?', s)
        self.assertEqual('NOT_ELIGIBLE_PDF', p['decision']['graduation_outcome'])
        self.assertIn('CDA0016', p['missing_courses']); self.assertTrue(p['needs_information'])

    def test_gea8617_corrected_metadata_does_not_activate_conflicted_course(self):
        metadata = json.loads((ROOT / 'data/processed/general_education_2026.json').read_text(encoding='utf-8'))
        reason = metadata['known_conflicts'][0]['reason']
        self.assertNotIn('2학점', reason); self.assertIn('3학점',reason)
        self.assertFalse(any(c['course_id']=='GEA8617' for c in self.catalog['courses']))
        p = self.ask('GEA8617은 실제 있는 과목이야?')
        self.assertNotEqual('FOUND', p['decision']['lookup_status'])


if __name__ == '__main__':
    unittest.main()
