"""Question -> semantic planner -> strict validation -> dry-run -> RO rows -> evidence."""
from __future__ import annotations
import os
import re
import time
from .db import RejectedSQL, execute_readonly
from .llm import ModelError, plan
from .quality import reconsider_refusal, review_feedback, semantic_signal
from .contract import diagnostics, infer_contract
from .normalizer import normalize

WRITE_CUES = re.compile(r'\b(?:delete|drop|truncate|update|insert|alter|create|remove\s+from|wipe|erase)\b|(?:حذف\s*کن|پاک\s*کن|پاک\s*کردن|ویرایش\s*کن|اضافه\s*کن|تغییر\s*بده|بازی\s*ها\s*را\s*پاک)',re.I)


def answer(question: str, *, planner=plan, runner=execute_readonly, previous_question=None,
           try_repair=True, reviewer=None) -> dict:
    start=time.monotonic()
    question=(question or '').strip()
    base={'intent':'unknown','action':'refuse_out_of_scope','sql':None,
          'validation':'not_run','dry_run':'not_run','row_count':0,'rows':[],'columns':[],
          'tables':[],'fields':[],'execution_ms':0,'model_diagnostics':None,
          'answer':'','next_state':None,'database_executed':False,
          'quality_review':'not_run','semantic_warnings':[], 'result_normalization':'not_run'}
    def result(**values):
        out={**base,**values};out['total_latency_ms']=round((time.monotonic()-start)*1000);return out
    if not question or len(question)>700:
        return result(action='ask_clarifying_question',answer='لطفاً یک سؤال مشخص و کوتاه درباره داده‌های فوتبال وارد کنید.')
    # Hard write policy is checked BEFORE transmitting question to model or preparing SQL.
    if WRITE_CUES.search(question):
        return result(intent='write_request',action='refuse_write',validation='blocked_by_policy',
                      answer='این سیستم فقط خواندنی است و نمی‌تواند داده‌های مسابقات را تغییر دهد.')
    if infer_contract(question).grain=='not recorded by the database':
        return result(intent='unsupported_metric',action='refuse_out_of_scope',validation='blocked_by_policy',
                      answer='این معیار در دیتابیس تمرین ثبت نشده و نمی‌توان آن را از داده‌های دیگر حدس زد.')
    if previous_question and (not isinstance(previous_question,str) or len(previous_question)>350):
        previous_question=None
    try:
        route,diag=planner(question,previous_question=previous_question)
    except ModelError as e:
        return result(action='refuse_out_of_scope',validation='model_unavailable',
                      answer='مدل تولید SQL در دسترس نیست؛ هیچ کوئری اجرا نشده است. '+str(e))
    action=route['action'];intent=str(route.get('intent') or 'unknown')[:100]
    if action=='ask_clarifying_question':
        followup=str(route.get('clarification') or 'لطفاً معیار مدنظرتان را دقیق‌تر مشخص کنید.')[:300]
        return result(intent=intent,action=action,model_diagnostics=diag,
                      answer=followup,next_state={'pending_question':question})
    review_enabled=(reviewer is not None or (planner is plan and
                    os.getenv('GAPGPT_REVIEW_ENABLED','1').strip().lower() not in ('0','false','no')))
    review_planner=reviewer if reviewer is not None else planner
    if action=='refuse_out_of_scope' and review_enabled and reconsider_refusal(question):
        # Verify that a derivable database question was not mistaken for outside scope.
        # No answer is forced: the second call may also refuse or ask for clarification.
        try:
            second,second_diag=review_planner(question,previous_question=previous_question,feedback={
                'mode':'reconsider_out_of_scope',
                'instruction':'Recheck whether a join or aggregation over the documented schema can answer the question. If so, propose read-only SQL; otherwise keep refusal.',
                'original_reason':str(route.get('reason') or '')[:240],
            })
            if second['action']=='answer_from_query':
                route=second;action=second['action'];intent=str(second.get('intent') or intent)[:100]
                diag={**second_diag,'latency_ms':diag.get('latency_ms',0)+second_diag.get('latency_ms',0),
                      'quality_review':'refusal_reconsidered'}
        except ModelError:
            pass
    if action in ('refuse_write','refuse_out_of_scope'):
        return result(intent=intent,action=action,model_diagnostics=diag,
                      answer=str(route.get('reason') or 'این درخواست با اطلاعات موجود قابل پاسخ نیست.')[:300])
    sql=route['sql']
    data=None
    last_rejection=None
    # Bounded read-only repair. Failed candidates are rejected in the sandbox;
    # a second retry is allowed for the real provider, not for mock unit tests.
    retries=2 if (try_repair and planner is plan) else 1 if try_repair else 0
    cumulative_repair_latency=0
    first_diag=diag
    for attempt in range(retries+1):
        try:
            data=runner(sql)
            break
        except RejectedSQL as error:
            last_rejection=error
            if attempt>=retries:
                break
            try:
                previous_sql=sql
                repaired,new_diag=planner(question,previous_question=previous_question,
                    error=('This SQL candidate FAILED independent validation/dry-run and was NOT executed. '
                           'Diagnose the failing table/column alias and correct it. '
                           'Use only the documented SQLite schema. Failure: '+str(error)[:320]+
                           '\nFailed SQL candidate:\n'+previous_sql[:7000]))
                cumulative_repair_latency+=new_diag.get('latency_ms',0)
                if repaired['action']!='answer_from_query' or repaired['sql']==previous_sql:
                    break
                sql=repaired['sql']
                diag={**new_diag,'latency_ms':first_diag.get('latency_ms',0)+cumulative_repair_latency}
            except ModelError:
                break
    if data is None:
        return result(intent=intent,action='refuse_out_of_scope',sql=None,
                      validation='rejected',model_diagnostics=diag,
                      answer='SQL پیشنهادی تأیید نشد و اجرا نشد: '+str(last_rejection)[:180])
    review_status='disabled' if not review_enabled else 'not_run'
    if review_enabled:
        # ALL candidates, including a second or third model answer, are executed only
        # after the same independent read-only SQL sandbox validation. Ranking and
        # result-shape checks use question text and REAL observed rows, never gold SQL.
        initial_issues=diagnostics(question,sql,data)
        revisions=2 if (reviewer is None and planner is plan and
                        os.getenv('GAPGPT_STRICT_REVIEW','1').lower() not in ('0','false','no')) else 1
        total_review_latency=0
        last_review_http=None
        for attempt in range(revisions):
            try:
                feedback=review_feedback(question,sql,data)
                if attempt:
                    feedback['mode']='strict_result_contract_repair'
                    feedback['instruction']=(
                        'The first review did not eliminate the observable problems. '
                        'Write a NEW read-only SELECT that resolves ALL of the result-contract '
                        'violations below; carefully check schema table aliases, GROUP BY grain, '
                        'tiebreaker ORDER BY, projection, LIMIT, and join cardinality. '
                        'Do not invent values; all rows must come from the database.')
                revised,review_diag=review_planner(question,previous_question=previous_question,
                                                   feedback=feedback)
                total_review_latency+=review_diag.get('latency_ms',0)
                last_review_http=review_diag.get('http_status')
                if revised['action']=='answer_from_query' and revised['sql'].strip()!=sql.strip():
                    try:
                        alternative=runner(revised['sql'])
                        before_issues=diagnostics(question,sql,data)
                        after_issues=diagnostics(question,revised['sql'],alternative)
                        before_signal=semantic_signal(question,sql,data)
                        after_signal=semantic_signal(question,revised['sql'],alternative)
                        # First optimize independently inferred output violations;
                        # do not let a plausible LLM revision regress the real rows.
                        improves=(len(after_issues)<len(before_issues) or
                                  (len(after_issues)==len(before_issues) and
                                   after_signal > before_signal + 0.1))
                        if improves:
                            sql=revised['sql'];data=alternative
                            review_status='adopted'
                        else:
                            review_status='rejected_regression'
                    except RejectedSQL:
                        review_status='rejected_revision'
                else:
                    review_status='kept_original' if review_status=='not_run' else review_status
                # A compliant result does not need additional model calls. A fallback
                # retry occurs only for real live provider and unresolved issues.
                if not diagnostics(question,sql,data):
                    break
            except ModelError:
                review_status='review_unavailable'
                break
        diag={**diag,
              'latency_ms':diag.get('latency_ms',0)+total_review_latency,
              'review_http_status':last_review_http,
              'quality_review':review_status}
    # Optional deterministic schema-aware shaping after the LLM review.
    # Besides projection/ranking/limit, an unambiguous two-sided join can be
    # keyed by credited team, or a missing own-goal club label FK can be added.
    # The candidate passes the SAME read-only sandbox. No evaluation reference
    # SQL or expected rows are used in response construction.
    normalization='disabled'
    if planner is plan and os.getenv('RESULT_NORMALIZATION_ENABLED','1').lower() not in ('0','false','no'):
        try:
            candidate=normalize(question,sql,data)
            if candidate:
                revised_data=runner(candidate)  # validate, dry-run, read-only execute
                previous_issues=diagnostics(question,sql,data)
                next_issues=diagnostics(question,candidate,revised_data)
                if len(next_issues)<len(previous_issues):
                    sql,data=candidate,revised_data
                    normalization='applied'
                else:
                    normalization='not_better'
            else:
                normalization='not_applicable'
        except RejectedSQL:
            normalization='rejected_by_sandbox'
    count=data['row_count']
    # The presentation never invents factual data; the table of rows is the answer.
    summary=('این پرسش در دیتابیس نتیجه‌ای نداشت؛ اطلاعاتی حدس زده نشد.' if not count else
             f'نتیجه بر اساس {count} ردیف بازگشتی از دیتابیس نمایش داده شده است.' +
             (' (خروجی به سقف ۱۰۰ ردیف محدود شده است.)' if data['truncated'] else ''))
    return result(intent=intent,action='answer_from_query',sql=sql,
                  model_diagnostics=diag,quality_review=review_status,
                  semantic_warnings=diagnostics(question,sql,data),
                  result_normalization=normalization,answer=summary,
                  database_executed=True,**data)
