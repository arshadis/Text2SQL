"""Run ALL 17 supplied questions against HTTP live system (never sends gold SQL).

Example: python scripts/evaluate_live.py https://YOUR-APP.darkube.ir
Writes reports/eval_report.json and reports/eval_report.md.
"""
import argparse
import http.client
import json
import os
import sys
import time
from collections import Counter
from pathlib import Path
from urllib.error import HTTPError,URLError
from urllib.request import Request,urlopen

ROOT=Path(__file__).resolve().parents[1]
CASES=json.loads((ROOT/'data/eval_questions.json').read_text(encoding='utf8'))
RANK_TERMS=['top','most','best','برتر','بیشترین','بهترین','صدرنشین']

def normalize_row(v):
    return tuple(json.dumps(x,ensure_ascii=False,sort_keys=True) for x in v)

def score(case, payload):
    if case.get('expected_behaviour'):
        ok=(payload.get('action') in ('refuse_write','refuse_out_of_scope')
            and payload.get('sql') is None and payload.get('database_executed') is False)
        return ok, 'Correct refusal, no SQL executed' if ok else 'Trap failed: query or data execution was not refused'
    if payload.get('action')!='answer_from_query':
        return False,'Not answered: '+str(payload.get('answer',''))[:180]
    if payload.get('validation')!='passed' or payload.get('dry_run')!='ok':
        return False,'Validation or dry-run did not pass'
    observed=[normalize_row(r) for r in payload.get('rows',[])]
    expected=[normalize_row(r) for r in case['expected_rows']]
    question=case['question_en'].lower()+' '+case.get('question_fa','')
    ranking=any(t in question for t in RANK_TERMS)
    ok=(observed==expected if ranking else Counter(observed)==Counter(expected))
    return ok, ('Rows matched expected_rows' if ok else
                f'Row mismatch: got {len(observed)} rows, expected {len(expected)}; first got={observed[:2]}, expected={expected[:2]}')

def _write_report(path: Path, doc: dict, *, markdown: bool = False) -> None:
    """Atomic snapshots survive SIGTERM/HTTP disconnect without claiming success."""
    path.parent.mkdir(exist_ok=True)
    part=path.with_name(path.name+'.tmp')
    if markdown:
        text=[f"# Live evaluation — {doc['generated_at']}",
              f"Address: {doc['url']}",
              f"Status: {doc['status']}; passed: {doc['passed']}/{doc['total']}", '']
        for r in doc['results']:
            text.extend([f"## {r['id']}: {'PASS' if r['pass'] else 'FAIL'}",
                         f"Question: {r['question']}",f"Reason: {r['reason']}",
                         f"Action: `{r.get('action','—')}`",
                         f"Validation: `{r.get('validation','—')}`; dry-run: `{r.get('dry_run','—')}`",
                         f"Quality review: `{r.get('quality_review','—')}`",
                         f"Result normalization: `{r.get('result_normalization','—')}`",
                         f"Semantic warnings: {r.get('semantic_warnings',[])}",
                         f"Review evidence: {r.get('review_evidence',[])}",'',
                         '```sql',r.get('sql') or '-- no SQL','```',''])
        payload='\n'.join(text)
    else:
        payload=json.dumps(doc,ensure_ascii=False,indent=2)+'\n'
    part.write_text(payload,encoding='utf8')
    os.replace(part,path)


def main():
    parser=argparse.ArgumentParser(description='Evaluate the actual HTTP pipeline, never using gold SQL in model prompts')
    parser.add_argument('url',help='Public HTTPS URL, or localhost for diagnostics')
    parser.add_argument('--only',help='Comma-separated case IDs for targeted diagnostics, e.g. q05,q09,q10')
    parser.add_argument('--from-case',dest='from_case',help='Run from this case onward, e.g. q13')
    parser.add_argument('--timeout',type=int,default=45,help='HTTP per-question timeout in seconds (default 45)')
    parser.add_argument('--transient-retries',type=int,default=1,choices=(0,1,2),help='Retry a model_unavailable response (default 1, max 2)')
    args=parser.parse_args()
    base=args.url.rstrip('/')
    if not base.startswith(('https://','http://localhost:','http://127.0.0.1:')):
        parser.error('Use the public HTTPS URL (or localhost for local diagnostics)')
    if args.only and args.from_case:
        parser.error('Use either --only or --from-case, not both')
    if not 3 <= args.timeout <= 180:
        parser.error('--timeout must be between 3 and 180 seconds')
    cases=CASES
    if args.only:
        wanted={c.strip() for c in args.only.split(',') if c.strip()}
        unknown=wanted-{case['id'] for case in CASES}
        if unknown: parser.error('Unknown case IDs: '+', '.join(sorted(unknown)))
        cases=[case for case in CASES if case['id'] in wanted]
    elif args.from_case:
        ids=[case['id'] for case in CASES]
        if args.from_case not in ids: parser.error('Unknown starting case')
        cases=CASES[ids.index(args.from_case):]
    full_run=len(cases)==len(CASES)
    with urlopen(base+'/health',timeout=12) as resp:
        if resp.status!=200:raise SystemExit('Site is not healthy')
    with urlopen(base+'/api/meta',timeout=12) as resp:
        meta=json.load(resp)
    fingerprint=meta.get('pipeline_sha256')
    if not isinstance(fingerprint,str) or len(fingerprint)!=64:
        raise SystemExit('Deployment has no source fingerprint: deploy the audited code before evaluation.')
    runtime_config=meta.get('runtime_config_sha256')
    if not isinstance(runtime_config,str) or len(runtime_config)!=64:
        raise SystemExit('Missing public runtime-config digest; deploy the new version before evaluating.')
    reports=[]
    out=ROOT/'reports'
    stamp=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())
    def document(status):
        return {'url':base,'generated_at':stamp,'status':status,'pipeline_sha256':fingerprint,
                'runtime_config_sha256':runtime_config,
                'provider_model':meta.get('provider_model'),
                'full_run':full_run,'completed':len(reports),
                'passed':sum(x['pass'] for x in reports),'total':len(cases),
                'results':reports}
    # Progress file is diagnostic only. Incomplete or subset results must NOT
    # overwrite the full 17-question report used by submission packaging.
    _write_report(out/'eval_progress.json',document('in_progress'))
    for case in cases:
        request=Request(base+'/api/ask',method='POST',headers={'Content-Type':'application/json'},
                        data=json.dumps({'question':case['question_en']},ensure_ascii=False).encode('utf8'))
        began=time.monotonic()
        disconnected=False
        attempts=0
        try:
            while True:
                attempts+=1
                with urlopen(request,timeout=args.timeout) as response:
                    obj=json.loads(response.read())
                # Only an explicit transient provider failure is retried: no SQL
                # has executed and the production pipeline failed closed.
                # Each retry is a fresh model call, never a cached reference SQL.
                temporary=(obj.get('validation')=='model_unavailable' and
                           'unavailable or timed out' in str(obj.get('answer','')).lower())
                if not temporary or attempts>args.transient_retries:
                    break
                time.sleep(min(3.0,1.5*attempts))
            ok,reason=score(case,obj)
            report={'id':case['id'],'question':case['question_en'],'pass':ok,
                    'reason':reason,'action':obj.get('action'), 'sql':obj.get('sql'),
                    'validation':obj.get('validation'), 'dry_run':obj.get('dry_run'),
                    'row_count':obj.get('row_count'),'columns':obj.get('columns'),'rows':obj.get('rows'),
                    'result_normalization':obj.get('result_normalization'),
                    'semantic_warnings':obj.get('semantic_warnings'),
                    'quality_review':obj.get('quality_review'),
                    'review_evidence':obj.get('review_evidence',[]),
                    'model_status':(obj.get('model_diagnostics') or {}).get('status'),
                    'attempts':attempts, 'seconds':round(time.monotonic()-began,2)}
        except (HTTPError,URLError,TimeoutError,OSError,http.client.HTTPException,ValueError) as ex:
            disconnected=isinstance(ex,(URLError,TimeoutError,ConnectionError,http.client.RemoteDisconnected))
            report={'id':case['id'],'question':case['question_en'],'pass':False,
                    'reason':'HTTP/runtime error: '+str(ex),'seconds':round(time.monotonic()-began,2)}
        print(('PASS' if report['pass'] else 'FAIL'),case['id'],report['reason'][:115],flush=True)
        reports.append(report)
        _write_report(out/'eval_progress.json',document('in_progress'))
        if disconnected:
            _write_report(out/'eval_partial.json',document('server_disconnected'))
            print('Server connection lost. Partial results saved to reports/eval_partial.json.',file=sys.stderr)
            return 2
    doc=document('complete' if full_run else 'subset_complete')
    suffix='eval_report' if full_run else 'eval_subset_report'
    _write_report(out/(suffix+'.json'),doc)
    _write_report(out/(suffix+'.md'),doc,markdown=True)
    print(f"Results: {doc['passed']}/{doc['total']} ({doc['status']}); saved under {out}")
    return 1 if doc['passed']<len(cases) else 0

if __name__=='__main__':sys.exit(main())
