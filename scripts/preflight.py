"""Local release preflight: source presence, DB integrity, security tests and optional GapGPT call."""
from __future__ import annotations
import os
import subprocess
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def run(args):
    print('> '+' '.join(args),flush=True)
    subprocess.run(args,cwd=ROOT,check=True)


def main():
    required=['Dockerfile','data/football.db','data/schema.sql','data/semantic_model.md',
              'data/eval_questions.json','app/db.py','app/llm.py','app/pipeline.py',
              'scripts/evaluate_live.py','scripts/capture_traces.py']
    missing=[p for p in required if not (ROOT/p).is_file()]
    if missing:raise SystemExit('Missing project files: '+', '.join(missing))
    run([sys.executable,'-m','unittest','discover','-s','tests','-v'])
    run([sys.executable,'scripts/verify_dataset.py'])
    print('PASS: local structure, security, HTTP, and dataset baselines')
    if '--live' in sys.argv:
        if not os.getenv('GAPGPT_API_KEY'):raise SystemExit('GapGPT key missing in this shell. Set it as an environment variable first.')
        sys.path.insert(0,str(ROOT))
        from app.pipeline import answer
        r=answer('How many matches have finished?')
        print('GapGPT live smoke:',{k:r.get(k) for k in ('action','intent','validation','dry_run','row_count','model_diagnostics')})
        if r['action']!='answer_from_query' or r['validation']!='passed':
            raise SystemExit('Live smoke failed: diagnose before deployment')
    else:
        print('GapGPT not contacted. Use --live after configuring API secret to test it.')

if __name__=='__main__':main()
