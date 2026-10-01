"""Separate adversarial review cases; source expectations are PDF-derived.

This is a second review perspective in the same task, not an external audit.
"""
from __future__ import annotations
import hashlib
import json
import subprocess
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
import test_source_accuracy as source
from curriculum_assistant.authority import RuleSetStore
from curriculum_assistant.engine import execute
from curriculum_assistant.graph import Graph
from curriculum_assistant.verifier import verify_payload
from correct_core_source_rules import corrected_catalog


class SourceAccuracyReview(unittest.TestCase):
    setUpClass=classmethod(source.SourceAccuracyAPI.setUpClass.__func__)
    tearDownClass=classmethod(source.SourceAccuracyAPI.tearDownClass.__func__)
    ask=source.SourceAccuracyAPI.ask

    def test_verified_negative_exemption_retains_nine_credit_minimum(self):
        s=source.waived();s['official_outcomes']['english_course_exemption']=source.outcome(False)
        p=self.ask('현재 부족한 요건을 알려줘.',s)
        self.assertEqual(9,source.rule(p,'BASIC-CREDITS')['required'])
        self.assertEqual(2,source.rule(p,'BASIC-CREDITS')['missing_amount'])
        self.assertEqual('UNSATISFIED',source.rule(p,'GE-2026-ENGLISH')['status'])

    def test_exemption_with_ai_foundation_missing_keeps_independent_rule(self):
        s=source.waived()
        # PDF 33/34: CE-eligible AI foundation options, independently checked.
        s['course_attempts']=[a for a in s['course_attempts'] if a['course_id'] not in ('GEA8810','GEA8812','GEA8813','GEA8814')]
        p=self.ask('어떤 졸업요건이 부족해?',s)
        self.assertEqual('UNSATISFIED',source.rule(p,'GE-2026-AI-FOUNDATION')['status'])

    def test_unconfirmed_exemption_irrelevant_when_english_actually_completed(self):
        s=source.complete();s['official_outcomes']['english_course_exemption']=source.outcome(True,'UNVERIFIED')
        p=self.ask('지금 졸업 가능해?',s)
        self.assertEqual('ELIGIBLE_PDF',p['decision']['graduation_outcome'])
        self.assertEqual(9,source.rule(p,'BASIC-CREDITS')['required'])

    def test_supplement_credit_boundary_one_short(self):
        s=source.waived(False)
        # PDF 35: 생성형AI기초 is balanced GE, 1 credit; one credit remains short.
        s['course_attempts'].append({'attempt_id':'REVIEW-ONE','course_id':'GEA8834','earned_credits':1,
            'completion_status':'COMPLETED','verification_status':'VERIFIED','evidence_id':'REVIEW-SYNTHETIC'})
        p=self.ask('지금 졸업 가능해?',s)
        self.assertEqual(1,source.rule(p,'GE-2026-TOTAL-CREDITS')['missing_amount'])
        self.assertEqual('NOT_ELIGIBLE_PDF',p['decision']['graduation_outcome'])

    def test_source_cap_boundary_not_changed_by_exemption(self):
        for earned, recognized, excess in [(41,41,0),(42,42,0),(43,42,1)]:
            with self.subTest(earned=earned):
                p=self.ask(f'2026 교양 {earned}학점을 이수했으면 인정 상한은 어떻게 돼?')
                calc=next(c for c in p['decision']['lookup_result']['calculations'] if c['operation']=='APPLY_VERIFIED_CREDIT_CAP')
                self.assertEqual((recognized,excess),(calc['recognized_amount'],calc['excluded_amount']))

    def test_verified_disability_exemption_does_not_require_certification_result(self):
        s=source.complete();s['disability_status']=source.outcome(True)
        s['official_outcomes'].pop('graduation_certification_passed')
        p=self.ask('지금 졸업 가능해?',s)
        self.assertEqual('NOT_APPLICABLE',source.rule(p,'GRAD-2026-CERTIFICATION')['status'])
        self.assertEqual('ELIGIBLE_PDF',p['decision']['graduation_outcome'])
        self.assertEqual('VERIFIED_PDF_EXEMPTION',source.rule(p,'GRAD-2026-CERTIFICATION')['evaluation_basis'])

    def test_unconfirmed_disability_irrelevant_to_verified_positive_certification(self):
        s=source.complete();s['disability_status']=True
        p=self.ask('지금 졸업 가능해?',s)
        self.assertEqual('ELIGIBLE_PDF',p['decision']['graduation_outcome'])

    def test_condition_in_question_cannot_be_silently_ignored(self):
        for label in ('수업연한 초과자','재입학생','전과생'):
            with self.subTest(label=label):
                p=self.ask(f'{label}인 나 지금 졸업 가능해?',source.complete())
                self.assertNotEqual('ELIGIBLE_PDF',p['decision']['graduation_outcome'])
                self.assertTrue(p['needs_information'])

    def test_unknown_replacement_claim_is_not_internal_global_obligation(self):
        s=source.complete();s['replacement_recognition_claim']={'course_id':'CDA0016'}
        p=self.ask('지금 졸업 가능해?',s)
        self.assertEqual('UNKNOWN',p['decision']['graduation_outcome'])
        self.assertTrue(p['decision']['coverage_details']['equivalence_review_required'])
        self.assertNotIn('OFFICIAL_EQUIVALENCE_REVIEW',p['needs_information'])

    def test_policy_old_year_does_not_claim_personal_graduation_support(self):
        p=self.ask('2015년도 기준 교양과 전공선택 최소학점은?')
        self.assertIn('26',p['answer_text']);self.assertIn('48',p['answer_text'])
        s=source.complete();s['admission_year']=2015;s['credit_policy_year']=2015
        personal=self.ask('지금 졸업 가능해?',s)
        self.assertEqual('UNKNOWN',personal['decision']['graduation_outcome'])
        self.assertFalse(personal['decision']['coverage_complete'])

    def test_requested_applied_year_can_differ_from_admission_without_mutation(self):
        s=source.complete();s['admission_year']=2022
        p=self.ask('2026 교육과정 적용자의 교양 최소학점은?',s)
        self.assertIn('34학점',p['answer_text'])
        self.assertEqual('CREDIT_POLICY_YEAR',p['interpretation']['structured_query']['year_targets'][0]['basis'])
        self.assertEqual(2022,s['admission_year'])

    def test_missing_document_year_is_not_a_credit_policy_year(self):
        p=self.ask('2022년도 PDF의 교양 최소학점은?')
        self.assertEqual('DOCUMENT_YEAR',p['interpretation']['structured_query']['year_targets'][0]['basis'])
        self.assertEqual('NEEDS_INFORMATION',p['decision']['lookup_status'])
        self.assertNotIn('34학점',p['answer_text']);self.assertNotIn('26학점',p['answer_text'])

    def test_missing_document_cannot_yield_personal_eligibility(self):
        p=self.ask('2022년도 PDF 기준으로 내 졸업 가능 여부를 알려줘.',source.complete())
        self.assertEqual('UNKNOWN',p['decision']['graduation_outcome'])

    def test_claimed_verified_exemption_without_evidence_is_not_confirmed(self):
        s=source.waived();s['official_outcomes']['english_course_exemption'].pop('evidence_id')
        p=self.ask('지금 졸업 가능해?',s)
        self.assertEqual('NEEDS_INFORMATION',source.rule(p,'GE-2026-ENGLISH')['status'])
        self.assertEqual('UNKNOWN',p['decision']['graduation_outcome'])

    def test_unsupported_course_table_year_is_not_2026_classification(self):
        p=self.ask('2022 과목표의 CDA0016은 몇 학점이야?')
        self.assertEqual('NEEDS_INFORMATION',p['decision']['lookup_status'])
        self.assertIsNone(p['decision']['lookup_result'])

    def test_policy_catalog_context_does_not_invent_admission_year(self):
        p=self.ask('이 교육과정이 어떤 학생에게 적용돼?')
        self.assertIsNone(p['decision']['lookup_result']['entry_year'])
        self.assertEqual(2026,p['decision']['lookup_result']['policy_year'])

    def test_mixed_year_bases_remain_separate(self):
        p=self.ask('2022학번과 2026 교육과정 적용자의 교양 최소학점을 비교해줘.')
        targets=[r['target'] for r in p['decision']['lookup_result']['year_comparison']]
        self.assertEqual([{'year':2022,'basis':'ADMISSION_YEAR'},{'year':2026,'basis':'CREDIT_POLICY_YEAR'}],targets)

    def test_unknown_exemption_outcome_is_preserved_as_relevant_condition(self):
        s=source.complete();s['official_outcomes']['general_exemption']=source.outcome(True)
        p=self.ask('지금 졸업 가능해?',s)
        self.assertEqual('UNKNOWN',p['decision']['graduation_outcome'])
        self.assertIn('UNSUPPORTED_OUTCOME:general_exemption',p['decision']['coverage_details']['unhandled_conditions'])

    def test_year_mismatch_partial_calculation_is_labeled(self):
        p=self.ask('2022학번인 내 앞으로 필요한 학점을 알려줘.',source.complete())
        self.assertTrue(p['needs_information'])
        self.assertIn('부분 결과',p['answer_text'])

    def test_unverified_adjustment_rule_never_exempts_basic_minimum(self):
        catalog=deepcopy(self.catalog)
        next(r for r in catalog['requirements'] if r['rule_id']=='R-GE-2026-BASIC-CREDITS')['verification_status']='UNVERIFIED'
        graph=Graph(Path(':memory:'),catalog)
        try:
            p=execute(graph,source.waived(),{'intent':'GRADUATION_STATUS'})
            self.assertEqual('NEEDS_INFORMATION',source.rule(p,'BASIC-CREDITS')['status'])
            self.assertNotEqual('ELIGIBLE_PDF',p['decision']['graduation_outcome'])
        finally:graph.close()

    def test_unsupported_range_not_silently_expanded_or_replaced(self):
        p=self.ask('1990~2026 적용자의 교양 최소학점은?')
        self.assertEqual('NEEDS_INFORMATION',p['decision']['lookup_status'])
        self.assertNotIn('34학점',p['answer_text'])

    def test_year_scope_tampering_is_rejected(self):
        p=self.ask('2022와 2026 교육과정의 교양 최소학점을 비교해줘.')
        p['interpretation']['structured_query']['year_targets']=[{'year':2026,'basis':'CREDIT_POLICY_YEAR'}]
        with self.assertRaises(ValueError):verify_payload(p)

    def test_conditional_adjustment_trace_tampering_is_rejected(self):
        p=self.ask('지금 졸업 가능해?',source.waived())
        event=next(e for e in p['execution_trace']['events'] if e['event_type']=='RULE_CONDITIONAL_ADJUSTMENT')
        event['result']['effective_required_amount']=9
        with self.assertRaises(ValueError):verify_payload(p)

    def test_coverage_claim_tampering_is_rejected(self):
        p=self.ask('지금 졸업 가능해?',source.complete())
        p['decision']['coverage_details']['certification_subrules_computed']=True
        with self.assertRaises(ValueError):verify_payload(p)

    def test_immutable_previous_snapshots_match_git_baseline(self):
        for path in sorted((source.ROOT/'data/processed/ruleset_versions').glob('ruleset-v[123]-*.json')):
            rel=path.relative_to(source.ROOT).as_posix()
            original=subprocess.check_output(['git','show','a5c6098:'+rel],cwd=source.ROOT)
            self.assertEqual(hashlib.sha256(original).hexdigest(),hashlib.sha256(path.read_bytes()).hexdigest())
            catalog=json.loads(original)
            graph=Graph(Path(':memory:'),catalog)
            try:
                p=execute(graph,source.complete(),{'intent':'GRADUATION_STATUS'})
                self.assertEqual('ELIGIBLE_PDF',p['decision']['graduation_outcome'])
                verify_payload(p)
            finally:graph.close()

    def test_migration_rejects_silent_catalog_changes(self):
        previous=RuleSetStore(source.ROOT/'data/processed/ruleset_versions').load_version(3)
        with tempfile.TemporaryDirectory() as d:
            store=RuleSetStore(Path(d));store.initialize(previous)
            corrected=corrected_catalog(previous);corrected['courses'][0]['catalog_credits']+=1
            with self.assertRaises(ValueError):store.activate_rule_correction(corrected)

    def test_gea8617_source_rows_keep_real_conflict(self):
        conflict=self.catalog['catalog_conflicts'][0]
        self.assertEqual([(42,3,3,0,'2'),(45,3,3,0,'이룸')],[(r['pdf_page'],r['credits'],r['theory'],r['practice'],r['term_raw']) for r in conflict['source_rows']])
        self.assertNotEqual(conflict['source_rows'][0]['name'],conflict['source_rows'][1]['name'])
        self.assertEqual('CONFLICTED',conflict['verification_status'])
        p=self.ask('GEA8617은 실제 있는 과목이야?')
        self.assertEqual('CONFLICTED',next(e['result'] for e in p['execution_trace']['events']
            if e['event_type']=='ENTITY_RESOLUTION'))

    def test_unsupported_policy_year_never_invents_admission_year(self):
        p=self.ask('2030 교육과정 적용자의 교양 최소학점 기준은?')
        self.assertEqual('NEEDS_INFORMATION',p['decision']['lookup_status'])
        self.assertIn('학점기준 연도 2030 적용자',p['answer_text'])
        self.assertNotIn('2030학년도 입학생',p['answer_text'])
        self.assertNotIn('34학점',p['answer_text'])

if __name__=='__main__':unittest.main()
