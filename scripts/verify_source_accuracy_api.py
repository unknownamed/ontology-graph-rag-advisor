"""Source correction API, model invariance and preservation checks (synthetic only)."""
from __future__ import annotations
import argparse
import json
import sys
import urllib.request
from copy import deepcopy
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tests')]
from test_source_accuracy import complete, waived, outcome
from curriculum_assistant.verifier import verify_payload

def post(port,request):
    req=urllib.request.Request(f'http://127.0.0.1:{port}/api/query',
        data=json.dumps(request,ensure_ascii=False).encode(),headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=180) as r:return json.load(r)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--port',type=int,default=18576)
    args=parser.parse_args();dest=ROOT/'logs/accuracy_corrections';dest.mkdir(parents=True,exist_ok=True)
    replay=[]
    if (dest/'before.json').exists():
        for original in json.loads((dest/'before.json').read_text(encoding='utf-8')):
            response=post(args.port,original['request']);verify_payload(response)
            replay.append({'audit_id':original['audit_id'],'request':original['request'],
                           'before':original['response'],'after':response})
    (dest/'replayed-v4.json').write_text(json.dumps(replay,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    unresolved=waived();unresolved['official_outcomes']['english_course_exemption']=outcome(True,'UNVERIFIED')
    exceeded=complete();exceeded['exceeded_standard_duration']=True
    clean=complete();clean.pop('equivalence_review_status');clean.pop('equivalence_review_evidence_id')
    disability=complete();disability['disability_status']=outcome(True);disability['official_outcomes'].pop('graduation_certification_passed')
    cases=[('normal','지금 졸업 가능해?',complete(),'ELIGIBLE_PDF'),
           ('waiver_supplement','지금 졸업 가능해?',waived(),'ELIGIBLE_PDF'),
           ('waiver_short','지금 졸업 가능해?',waived(False),'NOT_ELIGIBLE_PDF'),
           ('waiver_unknown','지금 졸업 가능해?',unresolved,'UNKNOWN'),
           ('duration','지금 졸업 가능해?',exceeded,'UNKNOWN'),
           ('clean_no_internal_review','지금 졸업 가능해?',clean,'ELIGIBLE_PDF'),
           ('disability_exempt','지금 졸업 가능해?',disability,'ELIGIBLE_PDF'),
           ('year_mismatch','2022학번인 내 졸업 가능 여부를 확인해줘.',complete(),'UNKNOWN'),
           ('historical_policy','2022 교육과정 적용자의 전공선택과 교양 최소학점은?',None,'NOT_REQUESTED'),
           ('comparison','2022와 2026 교육과정의 교양 최소학점을 비교해줘.',None,'NOT_REQUESTED'),
           ('english_policy','토익 700점이면 대학영어 면제 기준을 충족해?',None,'NOT_REQUESTED'),
           ('remaining_waived','앞으로 뭐 더 들어야 해?',waived(False),'NOT_REQUESTED'),
           ('simulation','CDA0143 하나 더 들으면 어떤 요건이 바뀌어?',waived(False),'NOT_REQUESTED'),
           ('source_conflict','GEA8617은 실제 있는 과목이야?',None,'NOT_REQUESTED')]
    rows=[]
    for fid,question,state,expected in cases:
        saved=deepcopy(state)
        request={'utterance':question,'use_local_llm':False,**({'student_state':state} if state else {})}
        off=post(args.port,request);on=post(args.port,{**request,'use_local_llm':True})
        verify_payload(off);verify_payload(on)
        assert off['decision']['graduation_outcome']==expected,(fid,off['decision']['graduation_outcome'])
        for key in ('decision','evidence','execution_trace','requirement_results','credited_amount','scenario_delta'):
            assert off[key]==on[key],(fid,key,'LLM invariance')
        assert on['llm_expression']['status']=='VERIFIED_STYLE',(fid,on['llm_expression'])
        again=post(args.port,request)
        assert off==again,(fid,'repeat')
        if state:
            reversed_state=deepcopy(state);reversed_state['course_attempts'].reverse()
            reordered=post(args.port,{**request,'student_state':reversed_state})
            for key in ('decision','evidence','execution_trace','scenario_delta'):assert off[key]==reordered[key],(fid,key,'order')
        assert state==saved,(fid,'input mutated')
        if fid=='waiver_supplement':
            assert off['credited_amount']['total']==130 and off['credited_amount']['by_area']['GENERAL_TOTAL']==34
        if fid=='historical_policy':
            assert '26' in off['answer_text'] and '57' in off['answer_text'] and '교양: 최소 34' not in off['answer_text']
        if fid=='source_conflict':
            assert off['decision']['lookup_status']=='CONFLICTED' and '3학점' in off['answer_text'] and '2학점' not in off['answer_text']
        rows.append({'fixture_id':fid,'question':question,'expected_outcome':expected,'actual_outcome':off['decision']['graduation_outcome'],
                     'decision_id':off['decision']['decision_id'],'ruleset_version':off['decision']['ruleset_version'],
                     'status':'PASS','llm_on_off':'PASS','repeat':'PASS','order':'PASS' if state else 'NOT_APPLICABLE',
                     'input_preservation':'PASS','provenance':'PASS','llm_expression':on['llm_expression'],
                     'answer_text':off['answer_text']})
        (dest/f'api-{fid}.json').write_text(json.dumps({'request':request,'off':off,'on':on},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        print('PASS',fid,flush=True)
    summary={'notice':'PUBLIC SYNTHETIC INPUTS ONLY; no real student or assessment reference used',
             'ruleset_version':4,'replayed_defects':len(replay),'cases':rows,'pass_count':len(rows),'fail_count':0}
    (ROOT/'evaluation/results/source_accuracy_v4_api_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

if __name__=='__main__':main()
