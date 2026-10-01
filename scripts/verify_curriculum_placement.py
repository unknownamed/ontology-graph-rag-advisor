"""Actual /api/query placement acceptance using public synthetic inputs only."""
from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from curriculum_assistant.graph import canonical
from curriculum_assistant.verifier import verify_payload

# Expected codes directly cross-checked against PDF rows, not calculated by the API.
CASES = [
    ('고급자료구조는 몇 학년 몇 학기에 편성돼?', None, None),
    ('2학기에 편성된 전공필수 과목을 보여줘.', None, ['CDA0017','CDA0023','CDA0034','CDA0088','CDA0143']),
    ('3학년 1학기 편성 전공 과목은 뭐야?', None, ['CDA0016','CDA0027','CDA0028','CDA0065','CDA0088','CDA0147','CDA0164','CDA0165','CDA0167','CDA0173']),
    ('1학기와 2학기 모두 편성된 전공 과목은?', None, ['CDA0034','CDA0088','CDA0147','CDA0155','CDA0156','CDA0167','CDA0168','CDA0173']),
    ('하계와 동계 모두 편성된 전공 과목은?', None, ['CDA0144','CDA0145','CDA0171','CDA0172']),
    ('내 남은 전필 중 2학기 편성 과목만 알려줘.', 'year1_early', ['CDA0017','CDA0023','CDA0034','CDA0088','CDA0143']),
    ('남은 요건을 채울 후보를 편성학기별로 묶어줘.', 'year2_late', None),
    ('GEA8694의 편성학기를 알려줘.', None, None),
    ('하계 편성 교양 과목은?', None, ['GEA5049','GEA5052','GEA7334','GEA8655','GEA8678','GEA8833','GEA8834']),
    ('다음 학기에 편성된 전공 과목은?', None, None),
]


def post(port, data):
    request = urllib.request.Request(f'http://127.0.0.1:{port}/api/query',
        data=json.dumps(data,ensure_ascii=False).encode(), headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(request,timeout=60) as response:
        result = json.load(response)
    verify_payload(result)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=18473)
    args = parser.parse_args()
    results = []
    for question, fid, expected in CASES:
        state = (json.loads((ROOT / f'evaluation/fixtures/remaining_2026/{fid}.json').read_text(encoding='utf-8'))['student_state'] if fid else None)
        request = {'utterance':question,'use_local_llm':False, **({'student_state':state} if state else {})}
        initial = canonical(state)
        off = post(args.port,request)
        on = post(args.port,{**request,'use_local_llm':True})
        for key in ('decision','evidence','execution_trace','requirement_results','credited_amount','scenario_delta'):
            assert off[key] == on[key], (question,key,'LLM invariant')
        assert on['llm_expression']['status'] == 'VERIFIED_STYLE', on['llm_expression']
        repeat = post(args.port,request)
        assert canonical(off) == canonical(repeat), (question,'repeat invariant')
        if state:
            permuted = deepcopy(state)
            permuted['course_attempts'].reverse()
            reordered = post(args.port,{**request,'student_state':permuted})
            assert off['decision'] == reordered['decision'] and off['evidence'] == reordered['evidence']
        assert canonical(state) == initial
        decision = off['decision']
        view = decision.get('placement_view') or decision['lookup_result']
        selected = view.get('selection',{}).get('matched_course_ids')
        if expected is not None:
            assert selected == expected, (question,selected,expected)
        row = {'question':question,'fixture_id':fid,'structured_query':off['interpretation']['structured_query'],
               'selected_course_ids':selected,'answer_text':off['answer_text'],
               'ruleset_version':decision['ruleset_version'],'decision_id':decision['decision_id'],
               'data_snapshot_id':decision['data_snapshot_id'],
               'query_plan':next(e for e in off['execution_trace']['events'] if e['event_type']=='QUERY_PLAN'),
               'selection_events':[e for e in off['execution_trace']['events'] if e['event_type']=='PLACEMENT_SELECTION'],
               'placement_facts':[{k:e[k] for k in ('course_id','entry_id','curriculum_placement','relationship_ids')}
                                  for e in off['evidence']['facts'] if e.get('entry_id') and
                                  (selected is None or e['course_id'] in selected)],
               'status':'PASS','llm_on_off':'PASS','repeat':'PASS','input_order':'PASS' if state else 'NOT_APPLICABLE',
               'provenance':'PASS','llm_expression':on['llm_expression']}
        results.append(row)
        print('PASS',question,flush=True)
    path = ROOT / 'evaluation/results/curriculum_placement_api_results.json'
    path.write_text(json.dumps({'notice':'SYNTHETIC INPUTS ONLY; official PDF cells are placement, not live offerings', 'results':results},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(f'PASS: {len(results)} API scenarios, LLM ON/OFF, repeated execution and provenance')


if __name__ == '__main__':
    main()
