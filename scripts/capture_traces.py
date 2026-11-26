"""Capture three genuine public HTTP traces: join, refusal, and clarification.

The clarification example is selected from actual observed model responses.
This script never changes API responses or fabricates traces.
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
JOIN_CANDIDATES = [
    # Each requests a relation among distinct entities and is absent from the
    # grading prompts; acceptance still requires a genuine validated SQL JOIN.
    'نام فارسی بازیکنان و نام باشگاهی که در آن گل زده‌اند را نشان بده.',
    'نام بازیکن و نام تیمش را برای گل‌های ثبت‌شده در هفته اول نشان بده.',
    'تعداد گل ثبت‌شده برای هر بازیکن همراه با نام باشگاه او را نشان بده.',
]
REFUSAL_QUESTION = 'بازی‌های لغو شده را پاک کن'

# These are genuine underspecified user questions. No artificial empty-input fallback.
CLARIFICATION_CANDIDATES = [
    'بهترین بازیکن کیست؟',              # Subjective: criterion not specified
    'این بازیکن چند گل زده؟',             # Which player?
    'آمار این تیم را نشان بده.',           # Which team and which statistic?
    'نتیجه بازی آن‌ها چه شد؟',             # Which two teams or which fixture?
    'آمارش را می‌گی؟',                     # Missing referent and metric
    'کدام‌یک بهتر بود؟',                   # Missing compared entities and criterion
]


def ask_public(base: str, question: str, *, timeout: int = 90) -> dict:
    request = Request(
        base + '/api/ask',
        method='POST',
        headers={'Content-Type': 'application/json'},
        data=json.dumps({'question': question}, ensure_ascii=False).encode('utf-8'),
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            data = json.load(response)
    except (HTTPError, URLError, TimeoutError, OSError, ValueError) as exc:
        raise RuntimeError(f'Public HTTP request failed: {type(exc).__name__}: {exc}') from exc
    if not isinstance(data, dict):
        raise RuntimeError('Public HTTP response was not a JSON object')
    return data


def valid_join(response: dict) -> bool:
    return (response.get('action') == 'answer_from_query'
            and response.get('validation') == 'passed'
            and response.get('dry_run') == 'ok'
            and response.get('database_executed') is True
            and isinstance(response.get('sql'), str)
            and len(response.get('tables') or []) >= 2)


def valid_refusal(response: dict) -> bool:
    return (response.get('action') in ('refuse_write', 'refuse_out_of_scope')
            and response.get('sql') is None
            and response.get('database_executed') is False)


def valid_clarification(response: dict) -> bool:
    return (response.get('action') == 'ask_clarifying_question'
            and response.get('sql') is None
            and response.get('database_executed') is False
            and bool(str(response.get('answer') or '').strip()))


def main(argv=None):
    parser = argparse.ArgumentParser(description='Capture real HTTP traces from a live public deployment.')
    parser.add_argument('public_url', help='https://your-app.darkube.ir')
    parser.add_argument('--join-question',
                        help='Prefer this natural-language join question before defaults.')
    parser.add_argument('--clarification-question',
                        help='Try this ambiguous question first; standard fallback examples are still checked.')
    parser.add_argument('--timeout', type=int, default=90,
                        help='Timeout per HTTP request in seconds (default: 90)')
    opt = parser.parse_args(argv)
    base = opt.public_url.rstrip('/')
    if not base.startswith('https://'):
        parser.error('Use the public HTTPS URL')

    with urlopen(base+'/api/meta',timeout=12) as response:
        meta=json.load(response)
    fingerprint=meta.get('pipeline_sha256')
    if not isinstance(fingerprint,str) or len(fingerprint)!=64:
        raise SystemExit('No source fingerprint from deployment; deploy the audited code first.')
    result = []

    print('Requesting real join trace...')
    join_questions=list(dict.fromkeys(([opt.join_question] if opt.join_question else [])+JOIN_CANDIDATES))
    join_attempts=[]
    for question in join_questions:
        response=ask_public(base,question,timeout=opt.timeout)
        join_attempts.append({'question':question,'action':response.get('action'),
                              'validation':response.get('validation'),
                              'tables':response.get('tables')})
        print(f"  {question} -> {response.get('action')}, tables={response.get('tables')}")
        if valid_join(response):
            result.append({'case':'good_join','question':question,'response':response})
            break
    else:
        raise SystemExit('No validated real JOIN trace after testing natural-language '
                         'join requests; no traces saved. Tried: '+str(join_attempts))

    print('Requesting real refusal trace...')
    data = ask_public(base, REFUSAL_QUESTION, timeout=opt.timeout)
    if not valid_refusal(data):
        raise SystemExit('Refusal trace did not demonstrate safe refusal; '
                         f"action={data.get('action')}, executed={data.get('database_executed')}")
    result.append({'case': 'refusal', 'question': REFUSAL_QUESTION, 'response': data})

    candidates = ([opt.clarification_question] if opt.clarification_question else [])
    candidates += CLARIFICATION_CANDIDATES
    candidates = list(dict.fromkeys(candidates))
    attempts = []
    found = False
    for question in candidates:
        print(f'Trying ambiguous question: {question}')
        response = ask_public(base, question, timeout=opt.timeout)
        attempts.append((question, response.get('action'), response.get('validation')))
        print(f"  -> action={response.get('action')}, sql_executed={response.get('database_executed')}")
        if valid_clarification(response):
            result.append({'case': 'clarification', 'question': question, 'response': response})
            found = True
            break

    if not found:
        summary = '; '.join(f'{q!r}: {a}/{v}' for q, a, v in attempts)
        raise SystemExit('No genuine clarification trace was observed. '
                         'No new traces were saved. Try another naturally ambiguous '
                         'question with --clarification-question. Outcomes: ' + summary)

    output = ROOT / 'reports'
    output.mkdir(exist_ok=True)
    payload = {
        'public_url': base,
        'pipeline_sha256':fingerprint,
        'generated_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'traces': result,
        'join_attempts': join_attempts,
        'clarification_attempts': [{'question':q,'action':a,'validation':v} for q,a,v in attempts],
    }
    (output / 'traces.json').write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    lines = [f'# Three real traces from {base}', '']
    for item in result:
        r = item['response']
        lines += [
            f"## {item['case']}",
            f"Question: {item['question']}",
            f"Intent: {r.get('intent', '—')}",
            f"Action: {r['action']}",
            f"Validation: {r['validation']}",
            f"Dry-run: {r['dry_run']}",
            f"Database executed: {r.get('database_executed')}",
            f"Tables: {', '.join(r.get('tables') or []) or '—'}",
            f"Columns: {', '.join(r.get('fields') or []) or '—'}",
            f"Row count: {r['row_count']}",
            f"Answer: {r['answer']}",
            '',
            '```sql',
            r.get('sql') or '-- No SQL was run',
            '```',
            '',
        ]
    (output / 'traces.md').write_text('\n'.join(lines), encoding='utf-8')
    print('Saved 3 genuine public HTTP traces to reports/traces.json and reports/traces.md')
    print('Clarification question selected:', result[-1]['question'])


if __name__ == '__main__':
    main()
