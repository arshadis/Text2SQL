"""Offline dataset integrity check, never used in API or model prompts.

Only this offline validation script reads the supplied evaluation gold_sql.
It confirms that football.db matches the supplied reference snapshot; it does
NOT measure SQL generation quality and cannot replace the live 17-question eval.
"""
from __future__ import annotations
import json
import sys
from collections import Counter
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from app.db import execute_readonly, ro_connection


def main():
    cases=json.loads((ROOT/'data/eval_questions.json').read_text(encoding='utf8'))
    assert len(cases)==17, 'Expected the complete 17-question source evaluation set'
    db=ro_connection()
    try:
        counts={name:db.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0] for name in ('team','player','match')}
        assert counts=={'team':18,'player':531,'match':306},f'Unexpected snapshot counts: {counts}'
    finally:db.close()
    print('Snapshot: 18 teams, 531 players, 306 fixtures')
    passes=0
    for case in cases:
        gold=case.get('gold_sql')
        if not gold:
            assert case.get('expected_behaviour'),f'Missing trap declaration in {case["id"]}'
            print(f'{case["id"]}: expected refusal (no gold SQL)')
            continue
        outcome=execute_readonly(gold)
        rows=outcome['rows']
        # Source-defined SQL has a definite order; this is an integrity check,
        # not a ranking inference or a generated answer.
        assert rows==case['expected_rows'],f'Baseline changed in {case["id"]}: {rows[:2]}'
        print(f'{case["id"]}: source reference matches ({len(rows)} rows)')
        passes+=1
    assert passes==15
    print('PASS: 15/15 reference queries consistent; 2/2 trap definitions present.')
    print('Note: This is NOT an LLM evaluation. Run scripts/evaluate_live.py for that.')

if __name__=='__main__':main()
