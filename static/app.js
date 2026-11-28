'use strict';
const $ = id => document.getElementById(id);
const form=$('ask'), question=$('question'), send=$('send');
let state=null;
const display=(id,value)=>{$(id).textContent= value===null||value===undefined||value===''?'—':String(value)};
const entities = v => Array.isArray(v)?v.join(', ')||'—':'—';
function setQuestion(q, resetState=true) {question.value=q;if(resetState)state=null;display('counter',`${question.value.length} / 700`);question.focus();}
document.querySelectorAll('[data-q]').forEach(button=>button.addEventListener('click',()=>setQuestion(button.dataset.q)));
question.addEventListener('input',()=>display('counter',`${question.value.length} / 700`));
$('reset').addEventListener('click',()=>{state=null;question.value='';question.focus();$('result').hidden=true;display('counter','0 / 700');});
$('copy-sql').addEventListener('click',async()=>{const sql=$('sql').textContent;if(!sql||sql==='—')return;try{await navigator.clipboard.writeText(sql);$('copy-sql').textContent='کپی شد';setTimeout(()=>$('copy-sql').textContent='کپی SQL',1400);}catch{}});
fetch('/api/meta').then(r=>r.ok?r.json():null).then(d=>{if(d){display('teams',d.teams);display('players',d.players);display('matches',d.matches);}}).catch(()=>{});
form.addEventListener('submit',async e=>{
  e.preventDefault();if(!question.value.trim())return;
  send.disabled=true;send.textContent='در حال تحلیل…';
  $('result').hidden=false; $('table-wrap').hidden=true; $('followup').hidden=true;
  for(const id of ['action-badge','intent','action','validation','dryrun','tables','fields','rowcount','execution','model','review','review-basis','total','sql','validation-badge','semantic-warnings'])display(id,'—');
  display('answer','در حال تولید و اعتبارسنجی SQL…');
  try {
    const response=await fetch('/api/ask',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({question:question.value,state}),signal:AbortSignal.timeout(180000)});
    const data=await response.json();if(!response.ok)throw Error(data.error||`HTTP ${response.status}`);
    state=data.next_state||null;
    display('answer',data.answer);
    display('action-badge',data.action);
    display('intent',data.intent);display('action',data.action);
    display('validation',data.validation);display('dryrun',data.dry_run);
    display('tables',entities(data.tables));display('fields',entities(data.fields));
    display('rowcount',data.row_count);display('execution',`${data.execution_ms??0} ms`);
    const m=data.model_diagnostics;
    display('model',m?`${m.status} · ${m.latency_ms} ms · HTTP ${m.http_status}`:'not called');
    display('review',data.quality_review||'not_run');
    display('semantic-warnings',entities(data.semantic_warnings));
    const evidence=Array.isArray(data.review_evidence)?data.review_evidence:[];
    display('review-basis',evidence.length?evidence.map(ev=>`${ev.decision}: issues ${ev.original_issues?.length??0}→${ev.candidate_issues?.length??0}, signal ${ev.original_signal??'—'}→${ev.candidate_signal??'—'}`).join(' | '):'—');
    display('total',`${data.total_latency_ms} ms`);display('sql',data.sql||'—');
    display('validation-badge',data.validation==='passed'?'✓ validated':data.validation);
    $('followup').hidden=!state;
    const head=$('rows').querySelector('thead'), body=$('rows').querySelector('tbody');
    head.replaceChildren();body.replaceChildren();
    if(data.columns?.length){const tr=document.createElement('tr');
      data.columns.forEach(c=>{const th=document.createElement('th');th.textContent=c;tr.appendChild(th);});head.appendChild(tr);
      for(const row of data.rows||[]){const tr=document.createElement('tr');for(const cell of row){const td=document.createElement('td');td.textContent=cell===null?'NULL':String(cell);tr.appendChild(td);}body.appendChild(tr);}
      display('row-counter',`${data.row_count} ردیف${data.truncated?' · محدودشده':''}`);$('table-wrap').hidden=false;}
    $('result').scrollIntoView({behavior:'smooth',block:'start'});
  }catch(err){display('answer',err.name==='TimeoutError'?'زمان انتظار مرورگر تمام شد؛ اتصال سرور را بررسی کن.':'خطا در ارتباط: '+err.message);}
  finally{send.disabled=false;send.innerHTML='تحلیل سؤال <span aria-hidden="true">↗</span>';}
});
