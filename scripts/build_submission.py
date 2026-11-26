"""Package genuine live evaluation + 3 public traces into a submission ZIP.

Never fabricates test results and never calls the model. Run evaluate_live.py and
capture_traces.py against your PUBLIC Hamravesh URL first.
"""
from __future__ import annotations
import argparse
import json
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import urlparse
from zipfile import ZipFile,ZIP_DEFLATED

ROOT=Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0,str(ROOT))
from app.source_fingerprint import pipeline_sha256


def main():
    p=argparse.ArgumentParser()
    p.add_argument('public_url',help='https://<your app>.darkube.ir')
    p.add_argument('--repo',default='',help='Optional source repository URL')
    p.add_argument('--allow-failures',action='store_true',help='Produce an INCOMPLETE diagnostics package even if eval failed')
    opt=p.parse_args()
    url=opt.public_url.rstrip('/')
    parsed=urlparse(url)
    if parsed.scheme!='https' or not parsed.hostname or parsed.hostname in ('localhost','127.0.0.1'):
        p.error('Provide the public HTTPS deployment URL, not localhost')
    paths=[ROOT/'reports'/name for name in ('eval_report.json','eval_report.md','traces.json','traces.md')]
    for path in paths:
        if not path.exists():p.error(f'Missing {path.name}. Run live evaluation and trace capture first.')
    evaluation=json.loads(paths[0].read_text(encoding='utf8'))
    traces=json.loads(paths[2].read_text(encoding='utf8'))
    if evaluation.get('url','').rstrip('/')!=url or traces.get('public_url','').rstrip('/')!=url:
        p.error('Live report URLs differ from requested public URL: rerun both scripts for this same deployment')
    local_fingerprint=pipeline_sha256()
    for label,record in (('evaluation',evaluation),('trace',traces)):
        fingerprint=record.get('pipeline_sha256')
        if fingerprint!=local_fingerprint:
            p.error(f'{label} was not generated from this audited code version. Redeploy and rerun public evaluation AND traces. Expected pipeline_sha256={local_fingerprint}; observed={fingerprint}')
    if evaluation.get('total')!=17 or len(evaluation.get('results',[]))!=17:
        p.error('Expected evaluation for ALL 17 questions')
    expected={'good_join','refusal','clarification'}
    observed={i.get('case') for i in traces.get('traces',[])}
    if observed!=expected or len(traces['traces'])!=3:
        p.error('Expected the three required traces')
    problems=[]
    for t in traces['traces']:
        case,r=t['case'],t['response']
        if case=='good_join' and (r.get('action')!='answer_from_query' or len(r.get('tables',[]))<2 or r.get('validation')!='passed' or r.get('dry_run')!='ok'):
            problems.append('good_answer trace needs a validated join')
        if case in ('refusal','clarification') and (r.get('sql') is not None or r.get('database_executed') is not False):
            problems.append(case+' trace unexpectedly executed SQL')
        if case=='refusal' and r.get('action') not in ('refuse_write','refuse_out_of_scope'):problems.append('refusal trace is not a refusal')
        if case=='clarification' and r.get('action')!='ask_clarifying_question':problems.append('clarification trace did not ask a question')
    passed=evaluation.get('passed',0)
    if passed<17:problems.append(f'live model evaluation only passed {passed}/17')
    if problems and not opt.allow_failures:p.error('Not ready for final submission: '+'; '.join(problems))
    status='INCOMPLETE — REVIEW REQUIRED' if problems else 'READY — 17/17 eval and 3 valid live traces'
    readme=f'''# Football Text-to-SQL — Assignment 2 submission

Status: **{status}**

- Audited pipeline fingerprint: `{local_fingerprint}`
- Public Hamravesh URL: {url}
- GitHub source: {opt.repo or '(add your repository link before submission)'}
- Evaluation results: **{passed}/17**, generated from live HTTP responses; see `eval_report.json`.
- Required traces: 3, generated from the public service; see `traces.md`.
- No SQL answer is hard-coded from the evaluation set. The live system calls GapGPT with `semantic_model.md` and `schema.sql`, validates and dry-runs the resulting SQL, then reads `football.db` through a read-only SQLite connection.
- Model-generated SQL cannot write, attach external databases, or access arbitrary files. Query results and evidence are shown with every answer.
- Scope: Iran Persian Gulf Pro League, supplied 2026–27 snapshot only.
- Created: {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}

## Running the deployed system
Open the public URL, ask a football question in Persian or English, and inspect the SQL plus Trace. Refusal and clarification actions must not run SQL.

## Bundle
`eval_report.json` / `eval_report.md`: full 17-case live evaluation, including per-case failures.
`traces.json` / `traces.md`: good join, refusal, clarification from public HTTP.
`schema.sql` / `semantic_model.md`: independent schema and domain mapping.
`ARCHITECTURE.md` / `DEPLOYMENT.md`: design and deployment instructions.

## Caveats
''' + ('- '+ '\n- '.join(problems)+'\n' if problems else '- No known eval or trace failures in the attached run; availability beyond the test period is not guaranteed.\n')
    outfile=ROOT/'Football_Text2SQL_Submission.zip'
    mapping=[('README.md',readme.encode('utf8'))]
    mapping += [(name,(ROOT/'reports'/name).read_bytes()) for name in ('eval_report.json','eval_report.md','traces.json','traces.md')]
    mapping += [(name,(ROOT/'data'/name).read_bytes()) for name in ('schema.sql','semantic_model.md')]
    mapping += [(name,(ROOT/'docs'/name).read_bytes()) for name in ('ARCHITECTURE.md','DEPLOYMENT.md','CONTAMINATION_AUDIT.md')]
    # Reviewer can inspect the complete production inference path. No code is hidden.
    mapping += [(path.relative_to(ROOT).as_posix(),path.read_bytes())
                for folder in ('app','scripts','tests')
                for path in sorted((ROOT/folder).glob('*.py'))]
    # Preserve the old benchmark-shaped regression checks as explicitly archived evidence.
    archived=ROOT/'docs'/'legacy_tests'
    if archived.is_dir():
        mapping += [(p.relative_to(ROOT).as_posix(),p.read_bytes()) for p in sorted(archived.iterdir()) if p.is_file()]
    if (ROOT/'Dockerfile').exists():mapping.append(('Dockerfile',(ROOT/'Dockerfile').read_bytes()))
    screenshot_dir=ROOT/'reports'/'screenshots'
    if screenshot_dir.is_dir():
        mapping += [('screenshots/'+p.name,p.read_bytes()) for p in sorted(screenshot_dir.iterdir())
                    if p.is_file() and p.suffix.lower() in ('.png','.jpg','.jpeg','.webp')] 
    with ZipFile(outfile,'w',ZIP_DEFLATED) as z:
        for name,data in mapping:z.writestr(name,data)
    print('Wrote',outfile,'status:',status)

if __name__=='__main__':main()
