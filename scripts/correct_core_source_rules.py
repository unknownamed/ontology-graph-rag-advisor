"""Reviewed v3 -> v4 correction from the existing official PDF only."""
from __future__ import annotations

import json
import sys
from copy import deepcopy
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from curriculum_assistant.authority import RuleSetStore, rule_ref, validate_registry

CONFLICT_ROWS=[
    {'pdf_page':42,'printed_page':34,'course_id':'GEA8617','name':'수식없는물리로보는세상',
     'classification':'GENERAL_BALANCED','credits':3,'theory':3,'practice':0,'term_raw':'2'},
    {'pdf_page':45,'printed_page':37,'course_id':'GEA8617','name':'융합프로젝트Ⅰ',
     'classification':'GENERAL_EXPANDED','credits':3,'theory':3,'practice':0,'term_raw':'이룸'}]
CONFLICT_REASON='PDF 42: 수식없는물리로보는세상, 균형교양, 3학점, 이론3/실기0, 2학기; PDF 45: 융합프로젝트Ⅰ, 확대교양, 3학점, 이론3/실기0, 학기 원문 이룸. Same code has conflicting names/classifications; recognition remains on hold.'


def corrected_catalog(base: dict) -> dict:
    validate_registry(base)
    if base['curriculum_ruleset']['ruleset_version']!=3:
        raise ValueError('Reviewed source correction requires the immutable v3 baseline')
    out=deepcopy(base)
    locators=[('ENGLISH-EXEMPTION-2026',33,'교양 §2-1나 공인시험표·다른 교양 보충 단서'),
              ('CERT-DISABILITY-EXEMPTION-2026',569,'졸업 §3-2(3) 장애 학생 면제')]
    for rid,page,note in locators:
        out['source_locators'].append({'id':rid,'title':note,'pdf_page_start':page,'pdf_page_end':page,
            'printed_page_start':page-8,'printed_page_end':page-8,'table_section_note':note,
            'verification':'visual_cross_check','source_document_id':base['source_document_id'],
            'source_hash':base['source_sha256']})
    facts=[{'policy_fact_id':'PF-ENGLISH-EXEMPTION-2026','topic':'ENGLISH_EXEMPTION',
            'predicate':'ENGLISH_COURSE_EXEMPTION','source_refs':['ENGLISH-EXEMPTION-2026'],
            'value':{'exempt_course_ids':['GEA8704','GEA8705'],'waived_credit_amount':2,
                     'automatic_credit_award':0,'replacement_classifications':['GENERAL_BASIC','GENERAL_BALANCED','GENERAL_EXPANDED'],
                     'total_minimum_rule_id':'R-GE-2026-TOTAL-CREDITS',
                     'criteria':[{'exam':'TOEIC','minimum':700,'display':'TOEIC 700점'},
                         {'exam':'TOEIC_SPEAKING','minimum':130,'display':'TOEIC Speaking 130'},
                         {'exam':'TOEFL_IBT','minimum':79,'display':'TOEFL IBT 79'},
                         {'exam':'TEPS','minimum':494,'display':'TEPS 494'},
                         {'exam':'NEW_TEPS','minimum':264,'display':'New TEPS 264'},
                         {'exam':'OPIC','minimum_level':'IM1','display':'OPIc IM1'},
                         {'exam':'G_TELP_2','minimum':65,'display':'G-TELP Level 2: 65'},
                         {'exam':'G_TELP_3','minimum':85,'display':'G-TELP Level 3: 85'},
                         {'exam':'FLEX','minimum':630,'display':'FLEX 630'}]}},
           {'policy_fact_id':'PF-CERT-DISABILITY-EXEMPTION-2026','topic':'GRADUATION_CONDITIONS',
            'predicate':'CERTIFICATION_DISABILITY_EXEMPTION','source_refs':['CERT-DISABILITY-EXEMPTION-2026'],
            'value':{'condition_key':'disability_status','condition_value':True,
                     'affected_rule_id':'R-GRAD-2026-CERTIFICATION'}}]
    for f in facts:
        f.update({'department_id':base['department']['department_id'],'verification_status':'VERIFIED'})
    out['policy_facts'].extend(facts)
    for r in out['requirements']:
        original=deepcopy(r)
        if r['rule_id']=='R-GE-2026-BASIC-CREDITS':
            r['conditional_adjustments']=[{'condition_key':'english_course_exemption','expected_value':True,
                'required_verification_status':'VERIFIED','requires_evidence_id':True,
                'operation':'REDUCE_REQUIRED_CREDITS','amount':2,'automatic_credit_award':0,
                'policy_fact_id':'PF-ENGLISH-EXEMPTION-2026','affected_rule_id':r['rule_id'],
                'compensated_by_rule_id':'R-GE-2026-TOTAL-CREDITS',
                'source_refs':['ENGLISH-EXEMPTION-2026']}]
            r['source_refs'].append('ENGLISH-EXEMPTION-2026')
        elif r['rule_id']=='R-GE-2026-ENGLISH':
            r['exemption_policy_fact_id']='PF-ENGLISH-EXEMPTION-2026'
            r['source_refs'].append('ENGLISH-EXEMPTION-2026')
        elif r['rule_id']=='R-GRAD-2026-CERTIFICATION':
            r['conditional_exemptions']=[{'condition_key':'disability_status','expected_value':True,
                'policy_fact_id':'PF-CERT-DISABILITY-EXEMPTION-2026',
                'source_refs':['CERT-DISABILITY-EXEMPTION-2026']}]
            r['source_refs'].append('CERT-DISABILITY-EXEMPTION-2026')
        if r!=original:
            r['rule_version']=original['rule_version']+1
            r['supersedes']=rule_ref(original)
            r['supporting_evidence']=[{'document_id':base['source_document_id'],'source_ref':ref} for ref in r['source_refs']]
            out['rule_lineage'].append({'from':rule_ref(original),'to':rule_ref(r),
                'relation':'SUPERSEDED_BY','source_refs':r['source_refs'],
                'reason':'CORRECT_EXISTING_OFFICIAL_SOURCE_INTERPRETATION'})
    out['coverage_policy']={'version':1,'scope':'DOMESTIC_REGULAR_SINGLE_2026_WITH_VERIFIED_OFFICIAL_RESULTS',
        'equivalence_review_required':'ONLY_WHEN_RECOGNITION_CLAIMS_REQUIRE_DESIGNATION',
        'certification_mode':'OFFICIAL_RESULT_INPUT_OR_VERIFIED_PDF_EXEMPTION',
        'certification_subrules_computed':False}
    out['catalog_conflicts']=[{'course_id':'GEA8617','verification_status':'CONFLICTED',
                             'reason':CONFLICT_REASON,'source_rows':CONFLICT_ROWS}]
    out['source_correction_history']=[{'correction_id':'SOURCE-CORRECTION-GEA8617-2026-10-01',
        'previous_ruleset_version':3,'pdf_pages':[42,45],'corrected_credit_amount':3,
        'previous_error':'42쪽 학점2라고 기록했으나 2는 학기 열이다.',
        'conflict_resolution_status':'UNRESOLVED_NAMES_AND_CLASSIFICATIONS'}]
    out['curriculum_ruleset']['ruleset_version']=4
    out['curriculum_ruleset']['created_at']='2026-10-01'
    out['curriculum_ruleset']['verification_summary']['verified_policy_facts']=len(out['policy_facts'])
    validate_registry(out)
    return out


def main():
    store=RuleSetStore(ROOT/'data/processed/ruleset_versions')
    active=store.load_active()
    if active['curriculum_ruleset']['ruleset_version']==4:
        print('Source correction v4 already active');return
    out=corrected_catalog(active)
    store.activate_rule_correction(out)
    path=ROOT/'data/processed/general_education_2026.json'
    ge=json.loads(path.read_text(encoding='utf-8'))
    conflict=next(c for c in ge['known_conflicts'] if c['course_id']=='GEA8617')
    conflict['reason']=CONFLICT_REASON;conflict['source_rows']=CONFLICT_ROWS
    conflict['correction_record_id']='SOURCE-CORRECTION-GEA8617-2026-10-01'
    path.write_text(json.dumps(ge,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('Activated CRS-CE-2026-CORE v4; same official PDF / ADS v1; v1/v2/v3 preserved')


if __name__=='__main__':
    main()
