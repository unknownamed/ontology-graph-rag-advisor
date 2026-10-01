"""Run existing API/PDF regression suites into new, isolated v4 records.

Only public synthetic fixtures and the official curriculum are accessed.
Earlier evaluation artifacts and the user's running browser are untouched.
"""
from __future__ import annotations
import argparse
import importlib
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
DEST=ROOT/'logs/accuracy_corrections'

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('suite',choices=['independent','ux','pdf','placement'])
    parser.add_argument('--port',type=int,default=18576)
    args=parser.parse_args()
    DEST.mkdir(parents=True,exist_ok=True)
    names={'independent':'evaluate_independent_scenarios','ux':'verify_remaining_ux_2026',
           'pdf':'verify_mock_2026_pdf_e2e','placement':'verify_curriculum_placement'}
    module=importlib.import_module(names[args.suite])
    if args.suite=='placement':
        sys.argv=[names[args.suite],'--port',str(args.port),'--output',str(DEST/'placement-v4.json')]
    else:
        module.RESULTS=DEST/f'{args.suite}-v4.json'
        module.REPORT=DEST/f'{args.suite}-v4.md'
        sys.argv=[names[args.suite],'--port',str(args.port)] if args.suite=='independent' else [names[args.suite]]
    module.main()

if __name__=='__main__':
    main()
