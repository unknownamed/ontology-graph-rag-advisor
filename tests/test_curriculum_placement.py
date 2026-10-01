"""Placement expectations transcribed from PDF 262–263/34–45, not engine output."""
from __future__ import annotations

import json
import sys
import tempfile
import threading
import unittest
import urllib.request
from copy import deepcopy
from http.server import HTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'scripts')]
from curriculum_assistant.authority import RuleSetStore
from curriculum_assistant.engine import execute
from curriculum_assistant.graph import Graph
from curriculum_assistant.nlp import interpret
from curriculum_assistant.placement import normalize_placement, placement_match, select_placement
from curriculum_assistant.server import Handler, catalog_query_context
from curriculum_assistant.verifier import verify_payload
from refine_curriculum_placement import refined_catalog

# Original PDF p.263 footer: 1-only 15, 2-only 16, both 8, seasonal 4.
SECOND_REQUIRED = {'CDA0143', 'CDA0017', 'CDA0023', 'CDA0034', 'CDA0088'}
THIRD_FIRST = {'CDA0016', 'CDA0027', 'CDA0028', 'CDA0065', 'CDA0164', 'CDA0165', 'CDA0167', 'CDA0147', 'CDA0173', 'CDA0088'}
BOTH_MAJOR = {'CDA0155', 'CDA0156', 'CDA0167', 'CDA0034', 'CDA0168', 'CDA0147', 'CDA0173', 'CDA0088'}
SEASONAL_MAJOR = {'CDA0144', 'CDA0145', 'CDA0171', 'CDA0172'}
FIRST, SECOND = 'SEMESTER_1', 'SEMESTER_2'


def fixture(name='year1_early'):
    return json.loads((ROOT / f'evaluation/fixtures/remaining_2026/{name}.json').read_text(encoding='utf-8'))['student_state']


class PlacementAPICases(unittest.TestCase):
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
        with urllib.request.urlopen(req, timeout=60) as response:
            result = json.load(response)
        if 'decision' in result:
            verify_payload(result)
        return result

    def ids(self, result):
        return set(result['decision']['lookup_result']['selection']['matched_course_ids'])

    def test_single_course_direct_answer_and_source(self):
        result = self.ask('고자구가 편성된 학년과 학기를 확인해 줘')
        p = result['decision']['lookup_result']['curriculum_placement']
        self.assertEqual('2-2', p['raw_grade_term'])
        self.assertEqual([{'grade': 2, 'grade_scope': 'LIST', 'term': SECOND}], p['slots'])
        self.assertEqual(262, p['source']['pdf_page'])
        self.assertIn('2학년 2학기', result['answer_text'])
        self.assertIn('미확인', result['answer_text'])

    def test_second_semester_required_intersection_from_source(self):
        self.assertEqual(SECOND_REQUIRED, self.ids(self.ask('2학기에 편성된 전필 과목 목록')))

    def test_grade_and_term_includes_multiple_and_all_grade_entries(self):
        r = self.ask('3학년 1학기 전공 편성 과목')
        self.assertEqual(THIRD_FIRST, self.ids(r))

    def test_both_terms_are_all_match_not_any(self):
        self.assertEqual(BOTH_MAJOR, self.ids(self.ask('1학기와 2학기 모두 편성된 전공 과목은?')))

    def test_seasonal_not_regular_terms(self):
        self.assertEqual(SEASONAL_MAJOR, self.ids(self.ask('동계에 편성된 전공 과목 목록')))
        self.assertFalse(SEASONAL_MAJOR & self.ids(self.ask('2학기 전공 편성 과목 목록')))

    def test_footer_counts_independent_of_duplicate_semester_memberships(self):
        r = self.ask('전공 후보를 편성학기별로 보여줘')
        self.assertEqual(43, len(self.ids(r)))
        courses = r['decision']['lookup_result']['courses']
        counts = {}
        for c in courses:
            terms = tuple(sorted({s['term'] for s in c['curriculum_placement']['slots']}))
            counts[terms] = counts.get(terms, 0) + 1
        self.assertEqual({(FIRST,): 15, (SECOND,): 16, (FIRST, SECOND): 8, ('SUMMER', 'WINTER'): 4}, counts)

    def test_term_only_general_cell_not_promoted_to_all_grade(self):
        r = self.ask('대학영어Ⅰ는 몇 학년 몇 학기에 편성돼?')
        p = r['decision']['lookup_result']['curriculum_placement']
        self.assertEqual('1,2', p['raw_term'])
        self.assertEqual('MISSING', p['grade_scope'])
        self.assertEqual('MISSING', p['grade_verification_status'])
        self.assertEqual('VERIFIED', p['term_verification_status'])
        self.assertIn('학년 미기재', r['answer_text'])

    def test_unclassified_source_label_preserved_and_not_regular_semester(self):
        r = self.ask('GEA8694의 편성학기는?')
        p = r['decision']['lookup_result']['curriculum_placement']
        self.assertEqual('이룸', p['raw_term'])
        self.assertEqual('UNVERIFIED', p['term_verification_status'])
        listed = self.ask('2학기 교양 편성 과목 목록')['decision']['lookup_result']
        self.assertNotIn('GEA8694', listed['selection']['matched_course_ids'])
        self.assertIn('GEA8694', listed['selection']['needs_verification_course_ids'])

    def test_general_seasonal_cells_from_original_pages(self):
        r = self.ask('하계에 편성된 교양 과목은?')
        self.assertEqual({'GEA8655', 'GEA8833', 'GEA8834', 'GEA5049', 'GEA7334', 'GEA8678', 'GEA5052'}, self.ids(r))

    def test_remaining_required_term_filter_preserves_whole_requirements(self):
        state = fixture()
        before = deepcopy(state)
        full = self.ask('앞으로 뭐 더 들어야 해?', state)
        filtered = self.ask('내 남은 전필 중 2학기 편성 과목만 알려줘', state)
        d = filtered['decision']
        self.assertEqual(SECOND_REQUIRED, set(d['placement_view']['selection']['matched_course_ids']))
        self.assertEqual(full['requirement_results'], filtered['requirement_results'])
        self.assertEqual(full['credited_amount'], filtered['credited_amount'])
        self.assertEqual(state, before)

    def test_completed_required_course_not_in_filtered_candidates(self):
        state = fixture('year4_late')
        r = self.ask('미이수 전필 중 2학기 편성만 보여 줘', state)
        self.assertEqual([], r['decision']['placement_view']['selection']['matched_course_ids'])
        self.assertEqual('SATISFIED', r['decision']['decision_status'])

    def test_remaining_term_groups_and_true_satisfies_relations(self):
        r = self.ask('남은 요건을 채울 후보를 편성학기별로 묶어줘', fixture())
        pv = r['decision']['placement_view']
        self.assertTrue(pv['groups'])
        selected = set(pv['selection']['matched_course_ids'])
        candidates = [c for c in r['decision']['candidate_courses'] if c['course_id'] in selected]
        edges = {e['id']: e for e in r['evidence']['relationship_details']}
        self.assertTrue(all(c['relationship_ids'] and c['curriculum_placement']['source']['pdf_page'] for c in candidates))
        self.assertTrue(all(edges[id]['kind'] == 'SATISFIES' for c in candidates for id in c['relationship_ids']))

    def test_next_term_no_reference_does_not_pick_a_semester(self):
        r = self.ask('다음 학기에 편성된 전공 과목은?')
        self.assertEqual('UNSPECIFIED', r['decision']['lookup_result']['next_term_basis'])
        self.assertEqual([], r['interpretation']['structured_query']['placement_filter']['terms'])
        self.assertIn('특정 학기를 선택하지 않았습니다', r['answer_text'])

    def test_context_course_reference(self):
        r = self.ask('그 과목의 편성학기는?', context={'last_course_id': 'CDA0034'})
        self.assertEqual('CDA0034', r['decision']['lookup_result']['course_id'])
        self.assertIn('4학년 1학기·2학기', r['answer_text'])

    def test_no_state_is_required_for_general_placement(self):
        r = self.ask('4학년 2학기 전공선택 편성 목록')
        self.assertFalse(r['requirement_results'])
        self.assertIsNone(r['credited_amount'])
        self.assertEqual({'CDA0150','CDA0153','CDA0166','CDA0175','CDA0168','CDA0147','CDA0173'}, self.ids(r))

    def test_unsupported_grade_not_widened_to_all(self):
        r = self.ask('9학년 1학기 전공 편성 과목')
        self.assertIsNone(r['interpretation']['structured_query'])

    def test_other_department_not_silently_mapped_to_computer_engineering(self):
        r = self.ask('기계공학과의 2학기 전필 편성 목록을 보여 줘')
        self.assertIsNone(r['interpretation']['structured_query'])
        self.assertIn('CATALOG_DEPARTMENT_UNVERIFIED', r['interpretation']['ambiguities'])

    def test_specific_general_classification_filter_is_preserved(self):
        r = self.ask('2학기에 편성된 균형교양 과목 목록')
        self.assertEqual(['GENERAL_BALANCED'], r['interpretation']['structured_query']['classifications'])
        result = r['decision']['lookup_result']
        self.assertTrue(result['courses'])
        self.assertTrue(all(c['classification'] == 'GENERAL_BALANCED' for c in result['courses']))

    def test_general_placement_lookup_not_blocked_by_historical_student(self):
        state = fixture()
        state.update(entry_year=2022, credit_policy_year=2022, catalog_year=2022,
                     applicability_status='UNVERIFIED')
        original = deepcopy(state)
        r = self.ask('고급자료구조는 몇 학년 몇 학기에 편성돼?', state)
        self.assertEqual('FOUND', r['decision']['lookup_status'])
        self.assertEqual('CURRICULUM-CE-2026', r['decision']['lookup_result']['curriculum_id'])
        self.assertEqual([], r['requirement_results'])
        self.assertIn('2026 교육과정', r['answer_text'])
        self.assertEqual('NEEDS_INFORMATION', self.ask('지금 졸업 가능해?', state)['decision']['decision_status'])
        self.assertEqual(state, original)

    def test_grade_filter_keeps_general_unknown_grade_separate(self):
        result = self.ask('3학년 1학기 교양 편성 과목')['decision']['lookup_result']
        self.assertEqual([], result['selection']['matched_course_ids'])
        self.assertIn('GEA8001', result['selection']['needs_verification_course_ids'])
        self.assertTrue(all(c['curriculum_placement']['grade_verification_status'] == 'MISSING'
                            for c in result['needs_verification'] if c['course_id'] == 'GEA8001'))

    def test_remaining_elective_placement_does_not_mix_required_candidates(self):
        state = fixture()
        full = self.ask('전공에서 남은 거 알려줘', state)
        r = self.ask('남은 전공선택 중 2학기 편성 후보만 보여 줘', state)
        ids = set(r['decision']['placement_view']['selection']['matched_course_ids'])
        # PDF 262–263: 19 electives; CDA0157 already completed, CDA0167
        # is a non-required 0-credit course and cannot fill these credit rules.
        self.assertEqual(19 - 1 - 1, len(ids))
        self.assertNotIn('CDA0157', ids)
        self.assertNotIn('CDA0167', ids)
        self.assertTrue(all(c['course_classification']=='MAJOR_ELECTIVE'
                            for c in r['decision']['candidate_courses'] if c['course_id'] in ids))
        self.assertEqual(full['requirement_results'], r['requirement_results'])
        self.assertEqual(full['credited_amount'], r['credited_amount'])

    def test_remaining_balanced_placement_does_not_mix_basic_general(self):
        r = self.ask('남은 균형교양 중 1학기에 편성된 후보만 알려 줘', fixture())
        selected = r['decision']['placement_view']['selection']
        ids = set(selected['matched_course_ids']+selected['needs_verification_course_ids'])
        self.assertTrue(ids)
        self.assertTrue(all(c['course_classification']=='GENERAL_BALANCED'
                            for c in r['decision']['candidate_courses'] if c['course_id'] in ids))

    def test_unallowlisted_placement_filters_cannot_be_executed(self):
        for filters in ({'grade': True}, {'terms': ['AUTUMN']}, {'cypher': 'MATCH (n) RETURN n'}):
            request = {'intent': 'PLACEMENT_LOOKUP', 'curriculum_id': 'CURRICULUM-CE-2026',
                       'department_id': 'DEPT-COMPUTER-ENGINEERING', 'classifications': ['MAJOR_REQUIRED'],
                       'placement_filter': filters}
            with self.assertRaises(urllib.error.HTTPError) as caught:
                self.ask('', structured_query=request)
            self.assertEqual(400, caught.exception.code)

    def test_unverified_schedule_tamper_is_blocked(self):
        r = self.ask('고자구 편성학기를 알려줘')
        r['evidence']['facts'][0]['curriculum_placement']['slots'][0]['term'] = FIRST
        with self.assertRaises(ValueError):
            verify_payload(r)

    def test_filter_tamper_is_blocked(self):
        r = self.ask('2학기 전필 편성 목록')
        r['decision']['lookup_result']['selection']['matched_course_ids'].append('CDA0008')
        with self.assertRaises(ValueError):
            verify_payload(r)


class PlacementReviewerCases(unittest.TestCase):
    def entry(self, raw=None, **fields):
        return {'grade_term': raw, 'verification_status': 'VERIFIED', 'source': {'document_id': 'TEST_FIXTURE', 'pdf_page': 1}, 'fact_id': 'TEST_ONLY', **fields}

    def test_blank_and_unreadable_never_all_terms(self):
        for raw, status in ((None,'MISSING'), ('판독불가','UNVERIFIED'), ('2-1,3','UNVERIFIED')):
            p = normalize_placement(self.entry(raw))
            self.assertEqual(status, p['term_verification_status'])
            self.assertEqual([], p['slots'])
            self.assertEqual('NEEDS_VERIFICATION', placement_match(p, {'terms': [SECOND]}))

    def test_grade_term_pairs_do_not_form_fictitious_cross_product(self):
        p = normalize_placement(self.entry('1-1;2-2'))
        self.assertEqual('NO_MATCH', placement_match(p, {'grade':1, 'terms':[SECOND]}))
        self.assertEqual('MATCH', placement_match(p, {'grade':2, 'terms':[SECOND]}))

    def test_unknown_grade_cannot_hide_known_term_exclusion(self):
        p = normalize_placement(self.entry(placement_term_raw='1'))
        self.assertEqual('NO_MATCH', placement_match(p, {'grade':3, 'terms':[FIRST,SECOND], 'term_match':'ALL'}))
        self.assertEqual('NEEDS_VERIFICATION', placement_match(p, {'grade':3, 'terms':[FIRST]}))

    def test_unverified_course_does_not_promote_readable_schedule(self):
        for fields in ({}, {'placement_verification_status': 'VERIFIED'}):
            p = normalize_placement(self.entry('3-1', verification_status='UNVERIFIED', **fields))
            self.assertEqual('NEEDS_VERIFICATION', placement_match(p, {'terms':[FIRST]}))

    def test_missing_schedule_candidate_kept_separately(self):
        candidate = {'course_id': 'TEST_COURSE', 'curriculum_placement': normalize_placement(self.entry())}
        r = select_placement([candidate], {'terms':[SECOND]})
        self.assertEqual(['TEST_COURSE'], r['needs_verification_course_ids'])
        self.assertEqual([], r['excluded_course_ids'])

    def test_catalog_refinement_cannot_overwrite_credits_or_rules(self):
        base = RuleSetStore(ROOT / 'data/processed/ruleset_versions').load_version(2)
        with tempfile.TemporaryDirectory() as directory:
            store = RuleSetStore(Path(directory))
            store.initialize(base)
            refined = refined_catalog(base)
            refined['courses'][0]['catalog_credits'] += 1
            with self.assertRaises(ValueError):
                store.activate_placement_refinement(refined)
            refined = refined_catalog(base)
            refined['courses'][0]['placement_verification_status'] = 'UNVERIFIED'
            with self.assertRaises(ValueError):
                store.activate_placement_refinement(refined)

    def test_v2_snapshot_and_graduation_simulation_values_reproducible(self):
        store = RuleSetStore(ROOT / 'data/processed/ruleset_versions')
        old, current = store.load_version(2), store.load_active()
        self.assertEqual(old['requirements'], current['requirements'])
        self.assertEqual(old['authoritative_document_set'], current['authoritative_document_set'])
        a, b = Graph(Path(':memory:'), old), Graph(Path(':memory:'), current)
        try:
            for name in ('year1_early','year2_late','year4_late','required_missing'):
                for query in ({'intent':'GRADUATION_STATUS'},{'intent':'WHAT_IF','course_id':'CDA0143'}):
                    left, right = execute(a,fixture(name),query), execute(b,fixture(name),query)
                    for key in ('decision_status','graduation_outcome','credited_amount','missing_courses','requirement_results','needs_information'):
                        self.assertEqual(left['decision'][key],right['decision'][key])
                    self.assertEqual(left['scenario_delta'],right['scenario_delta'])
        finally:
            a.close(); b.close()

    def test_semester_queries_do_not_change_existing_aggregate_policy(self):
        catalog = RuleSetStore(ROOT / 'data/processed/ruleset_versions').load_active()
        for question, intent in (('2026학년도 교양 잔여학점 편성 기준을 알려줘','POLICY_LOOKUP'),
                                 ('전공에 편성된 과목 학점 총합은?','CATALOG_AGGREGATE')):
            self.assertEqual(intent, interpret(question,catalog)['structured_query']['intent'])


if __name__ == '__main__':
    unittest.main()
