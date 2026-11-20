"""Capture the three required traces directly from public HTTP responses."""
import json,sys,time
from pathlib import Path
from urllib.request import Request,urlopen
ROOT=Path(__file__).resolve().parents[1]
CASES=[('good_join','۵ گلزن برتر لیگ چه کسانی هستند؟'),
       ('refusal','بازی‌های لغو شده را پاک کن'),
       ('clarification','بهترین بازیکن کیست؟')]
def main():
    if len(sys.argv)<2:raise SystemExit('Usage: python scripts/capture_traces.py https://PUBLIC_URL')
    base=sys.argv[1].rstrip('/')
    result=[]
    for name,question in CASES:
        req=Request(base+'/api/ask',method='POST',headers={'Content-Type':'application/json'},
                    data=json.dumps({'question':question},ensure_ascii=False).encode())
        with urlopen(req,timeout=45) as r: data=json.load(r)
        if name=='good_join' and (data['action']!='answer_from_query' or len(data.get('tables',[]))<2):
            raise SystemExit('Good-answer trace did not demonstrate a successful join. Fix before submission.')
        if name=='refusal' and (data['action'] not in ('refuse_write','refuse_out_of_scope') or data['sql'] is not None):
            raise SystemExit('Refusal trace did not refuse.')
        if name=='clarification' and (data['action']!='ask_clarifying_question' or data['sql'] is not None):
            raise SystemExit('Clarification trace did not ask a question.')
        result.append({'case':name,'question':question,'response':data})
    output=ROOT/'reports';output.mkdir(exist_ok=True)
    payload={'public_url':base,'generated_at':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'traces':result}
    (output/'traces.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf8')
    lines=[f'# Three real traces from {base}','']
    for item in result:
        r=item['response']
        lines += [f"## {item['case']}",f"Question: {item['question']}",f"Intent: {r['intent']}",
                  f"Action: {r['action']}",f"Validation: {r['validation']}",f"Dry-run: {r['dry_run']}",
                  f"Tables: {', '.join(r['tables']) or '—'}",f"Columns: {', '.join(r['fields']) or '—'}",
                  f"Row count: {r['row_count']}",f"Answer: {r['answer']}",'','```sql',r['sql'] or '-- No SQL was run','```','']
    (output/'traces.md').write_text('\n'.join(lines),encoding='utf8')
    print('Saved 3 HTTP traces to reports/traces.json and reports/traces.md')
if __name__=='__main__':main()
