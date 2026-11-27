#!/usr/bin/env python3
"""Post-hoc semantic audit from public HTTP traces, independent of eval gold.

This offline utility deliberately ignores expected_rows and benchmark case IDs.
It never runs in the model prompt/inference path, and it never alters rows or SQL.
It helps separate detectable SQL contradictions from unknown equivalence failures.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.semantic_checks import inspect


def audit_cases(cases):
    report=[]
    for case in cases:
        response=case.get('response',case)
        q=case.get('question') or response.get('question') or ''
        sql=response.get('sql')
        if response.get('action')!='answer_from_query' or not sql:
            report.append({'question':q,'action':response.get('action'),
                           'issues':[], 'status':'no_query'})
            continue
        # All rows are the actually recorded public response, not re-executed
        # reference SQL and never an imported expected answer.
        observed={'rows':response.get('rows') or [],
                  'columns':response.get('columns') or [],
                  'row_count':response.get('row_count',len(response.get('rows') or [])),
                  'fields':response.get('fields') or []}
        issues=inspect(q,sql,observed)
        report.append({'question':q,'action':response.get('action'),
                       'issues':issues,'status':'warnings' if issues else 'no_obvious_contradiction'})
    return report


def main(argv=None):
    parser=argparse.ArgumentParser(description='Audit recorded SQL semantics without benchmark gold')
    parser.add_argument('reports',nargs='+',help='live eval_report.json or generalization_probe.json')
    args=parser.parse_args(argv)
    for file in args.reports:
        source=Path(file)
        data=json.loads(source.read_text(encoding='utf-8'))
        cases=data.get('probes') or data.get('results') or []
        result=audit_cases(cases)
        print(f'{source}: {len(result)} real public responses checked')
        for item in result:
            print('  ',item['status'],item['question'][:75])
            for issue in item['issues']:
                print('     -',issue)
        print('Important: zero warnings DOES NOT prove that result values match the question.')
    return 0

if __name__=='__main__':
    raise SystemExit(main())
