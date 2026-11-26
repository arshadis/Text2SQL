"""Post-hoc cross-check of *unseen* probe outputs against the read-only dataset.

This test is intentionally separate from the public 17-case evaluator and from
production inference. It NEVER sends reference SQL or expected rows to GapGPT.
It checks six human-written, distinct natural-language holdout questions using
independent SQL as an auditor would do after collecting model responses.
"""
from __future__ import annotations
import argparse
import json
from collections import Counter
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.db import execute_readonly

ROOT=Path(__file__).resolve().parents[1]
# These are independent holdout smoke questions, not evaluator prompts. The
# server/Dockerfile never imports this test, and it has no model or HTTP calls.
REFERENCE_SQL={
    'stadiums': '''SELECT s.name_fa, COUNT(m.match_id) FROM stadium s
        LEFT JOIN "match" m ON m.stadium_id=s.stadium_id AND m.status='finished'
        GROUP BY s.stadium_id''',
    'var': 'SELECT COUNT(*) FROM var_decision',
    'fixtures': '''SELECT home.name, away.name, m.match_date FROM "match" m
        JOIN team home ON home.team_id=m.home_team_id
        JOIN team away ON away.team_id=m.away_team_id
        WHERE m.round=2 AND m.status='finished' ''',
    'standings': 'SELECT team, played, points FROM v_standings',
    'substitutions': 'SELECT COUNT(*) FROM substitution',
    'coaches': '''SELECT DISTINCT c.name_fa,t.name_fa FROM match_coach mc
        JOIN coach c ON c.coach_id=mc.coach_id JOIN team t ON t.team_id=mc.team_id''',
}


def main(argv=None):
    parser=argparse.ArgumentParser(description='Independently verify 6 non-eval SQL probe outputs')
    parser.add_argument('report',nargs='?',default='reports/generalization_probe.json')
    args=parser.parse_args(argv)
    path=Path(args.report)
    payload=json.loads(path.read_text(encoding='utf-8'))
    observed={case['id']:case for case in payload['probes']}
    passed=0
    for name,query in REFERENCE_SQL.items():
        if name not in observed:raise SystemExit('Missing independent probe: '+name)
        answer=observed[name]['response']
        expected=execute_readonly(query)
        actual=answer.get('rows',[])
        # Do not require unspecified row ordering; compare values and multiplicities.
        normalize=lambda rows:Counter(json.dumps(row,ensure_ascii=False,sort_keys=True) for row in rows)
        okay=(answer.get('action')=='answer_from_query'
              and answer.get('validation')=='passed'
              and normalize(actual)==normalize(expected['rows'])
              and not answer.get('truncated'))
        print(('PASS' if okay else 'FAIL'),name,'observed=',len(actual),'independent=',len(expected['rows']))
        passed+=bool(okay)
    print(f'Independent value-level checks: {passed}/{len(REFERENCE_SQL)}')
    print('These six hand-checked probes are not a general model-accuracy score.')
    return 0 if passed==len(REFERENCE_SQL) else 1

if __name__=='__main__':
    import sys
    sys.exit(main())
