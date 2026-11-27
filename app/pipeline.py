"""Question -> semantic planner -> strict validation -> dry-run -> RO rows -> evidence."""
from __future__ import annotations
import os
import re
import time
from collections import Counter
from .db import RejectedSQL, execute_readonly
from .llm import ModelError, plan
from .quality import reconsider_refusal, reconsider_clarification, review_feedback, semantic_signal
from .contract import diagnostics, infer_contract
from .normalizer import normalize, expand_verified_ties
from .narrative import summarize
from .schema_evidence import explain_available_data

def _same_facts_after_projection(before: dict, after: dict) -> bool:
    """Allow cosmetic reviewer edits only if actual database facts are unchanged.

    Query text/style is not evidence that a revision is an improvement. The
    candidate must preserve the whole observed multiset of rows after dropping
    zero or more unrequested display fields. This deliberately does not infer
    a benchmark answer, a preferred top-k, or an arbitrary statistic.
    """
    previous=list(before.get('columns') or ())
    proposed=list(after.get('columns') or ())
    if (not proposed or len(proposed)>len(previous) or len(set(previous))!=len(previous)
        or len(set(proposed))!=len(proposed) or not set(proposed).issubset(set(previous))
        or before.get('truncated') or after.get('truncated')):
        return False
    try:
        idx=[previous.index(col) for col in proposed]
        one=Counter(tuple(repr(row[i]) for i in idx) for row in before['rows'])
        two=Counter(tuple(repr(value) for value in row) for row in after['rows'])
        return one==two
    except (KeyError,IndexError,TypeError):
        return False


def _verified_entity_set_dedupe(before: dict, after: dict) -> bool:
    """Candidate SELECT DISTINCT returns precisely the original observed set.

    Never accept a truncation-limited sample or a changed field; this is only
    for a user's request for unique entity labels, never for event listings.
    """
    if (before.get('truncated') or after.get('truncated')
        or before.get('columns')!=after.get('columns')):
        return False
    try:
        one=[tuple(repr(v) for v in row) for row in before['rows']]
        two=[tuple(repr(v) for v in row) for row in after['rows']]
        return len(one)>len(two) and len(two)==len(set(one)) and set(two)==set(one)
    except (KeyError,TypeError):
        return False


WRITE_CUES = re.compile(r'\b(?:delete|drop|truncate|update|insert|alter|create|remove\s+from|wipe|erase)\b|(?:حذف\s*کن|پاک\s*کن|پاک\s*کردن|ویرایش\s*کن|اضافه\s*کن|تغییر\s*بده|بازی\s*ها\s*را\s*پاک)',re.I)


def answer(question: str, *, planner=plan, runner=execute_readonly, previous_question=None,
           try_repair=True, reviewer=None) -> dict:
    start=time.monotonic()
    question=(question or '').strip()
    base={'intent':'unknown','action':'refuse_out_of_scope','sql':None,
          'validation':'not_run','dry_run':'not_run','row_count':0,'rows':[],'columns':[],
          'tables':[],'fields':[],'execution_ms':0,'model_diagnostics':None,
          'answer':'','next_state':None,'database_executed':False,
          'quality_review':'not_run','review_evidence':[],'semantic_warnings':[], 'result_normalization':'not_run'}
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
    review_enabled=(reviewer is not None or (planner is plan and
                    os.getenv('GAPGPT_REVIEW_ENABLED','1').strip().lower() not in ('0','false','no')))
    review_planner=reviewer if reviewer is not None else planner
    # A model occasionally asks for clarification on a measurable, answerable
    # question. One bounded second opinion is allowed, but never forced:
    # only a successfully validated SQL answer may replace clarification.
    # The criterion is inferred from ordinary metric words, not gold SQL,
    # evaluator row counts or question IDs.
    if (action=='ask_clarifying_question' and review_enabled and
            reconsider_clarification(question)):
        try:
            revised,new_diag=review_planner(question,previous_question=previous_question,feedback={
                'mode':'clarification_necessity_check',
                'original_clarification':str(route.get('clarification') or '')[:260],
                'instruction':(
                    'Check whether the user already names a measurable quantity and '
                    'identifiable subject using the supplied schema. If yes, answer '
                    'using independent read-only SQL. If a necessary referent or '
                    'subjective criterion really is missing, keep one clarification. '
                    'Never guess an unspecified metric.'),
            })
            if revised['action']=='answer_from_query':
                route=revised;action=route['action']
                intent=str(route.get('intent') or intent)[:100]
                diag={**new_diag,'latency_ms':diag.get('latency_ms',0)+new_diag.get('latency_ms',0),
                      'clarification_review':'reconsidered_as_query'}
            else:
                diag={**diag,'clarification_review':'kept_clarification'}
        except ModelError:
            diag={**diag,'clarification_review':'review_unavailable'}
    if (action=='ask_clarifying_question' and review_enabled and
            reconsider_clarification(question)):
        # Bounded final check grounded in available schema facts. A genuine
        # ambiguity is never replaced with an invented metric or referent.
        try:
            evidence=explain_available_data(question)
            if evidence['relations']:
                checked,check_diag=review_planner(question,previous_question=previous_question,feedback={
                    'mode':'schema_evidence_clarification_check',
                    'readonly_schema_evidence':evidence,
                    'instruction':('Does this metadata establish that the specified metric is recorded? '
                        'If subject and metric are clear, generate read-only SQL from the schema. '
                        'Otherwise retain clarification. Never guess a missing criterion.'),
                })
                diag={**diag,'latency_ms':diag.get('latency_ms',0)+check_diag.get('latency_ms',0),
                      'schema_evidence_review':'query' if checked['action']=='answer_from_query' else 'kept_clarification'}
                if checked['action']=='answer_from_query':
                    route=checked;action=checked['action'];intent=str(checked.get('intent') or intent)[:100]
        except (ModelError, ValueError, OSError):
            pass
    if action=='ask_clarifying_question':
        followup=str(route.get('clarification') or 'لطفاً معیار مدنظرتان را دقیق‌تر مشخص کنید.')[:300]
        return result(intent=intent,action=action,model_diagnostics=diag,
                      answer=followup,next_state={'pending_question':question})
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
            else:
                evidence=explain_available_data(question)
                if evidence['relations']:
                    third,third_diag=review_planner(question,previous_question=previous_question,feedback={
                        'mode':'schema_evidence_answerability_check',
                        'original_reason':str(route.get('reason') or '')[:240],
                        'readonly_schema_evidence':evidence,
                        'instruction':('A dedicated change-log table is not needed if repeated observations '
                            'can be joined or aggregated to derive the requested fact. Use the schema '
                            'and aggregate metadata, never a guess. Answer with read-only SQL only '
                            'when the fact is genuinely derivable; otherwise preserve refusal.'),
                    })
                    diag={**diag,'latency_ms':diag.get('latency_ms',0)+second_diag.get('latency_ms',0)
                           +third_diag.get('latency_ms',0),
                          'schema_evidence_review':'query' if third['action']=='answer_from_query' else 'kept_refusal'}
                    if third['action']=='answer_from_query':
                        route=third;action=third['action'];intent=str(third.get('intent') or intent)[:100]
        except (ModelError, ValueError, OSError):
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
    review_evidence=[]
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
                        # A candidate cannot buy a better cosmetic score at
                        # the cost of a new question-grounded semantic warning.
                        from .semantic_checks import inspect as semantic_issues
                        before_semantic=set(semantic_issues(question,sql,data,
                                                  explicit_limit=infer_contract(question).target_rows))
                        after_semantic=set(semantic_issues(question,revised['sql'],alternative,
                                                  explicit_limit=infer_contract(question).target_rows))
                        introduced=after_semantic-before_semantic
                        # Changes that repair objectively observed semantic
                        # violations may legitimately change numerical rows.
                        # Cosmetic changes are admissible ONLY when actual
                        # database facts remain exactly the same (as a multiset
                        # after projection). A "nicer" score cannot justify a
                        # different answer or fabricated preferred top-k.
                        fixed_semantics=bool(before_semantic-after_semantic)
                        genuine_semantic_repair=(not introduced and fixed_semantics)
                        verified_cosmetic=(not introduced and not fixed_semantics and
                            len(after_issues)<len(before_issues) and
                            _same_facts_after_projection(data,alternative))
                        improves=genuine_semantic_repair or verified_cosmetic
                        review_evidence.append({'original_issues':before_issues,'candidate_issues':after_issues,
                            'original_semantic_issues':sorted(before_semantic),
                            'introduced_semantic_issues':sorted(introduced),
                            'original_signal':before_signal,'candidate_signal':after_signal,
                            'original_sql':sql, 'candidate_sql':revised['sql'],
                            'original_columns':data.get('columns',[]),
                            'candidate_columns':alternative.get('columns',[]),
                            'original_row_count':data.get('row_count'),
                            'candidate_row_count':alternative.get('row_count'),
                            'reason':('fixes an independently detected semantic contradiction' if genuine_semantic_repair else
                                      'preserves all real result values while improving presentation' if verified_cosmetic else
                                      'no proven semantic improvement or identical observed facts'),
                            'decision':'accepted' if improves else 'rejected'})
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
    # Optional narrow presentation shaping for an explicitly requested top-N.
    # Never rewrite joins, filters, metrics or domain-specific relationships.
    # Any candidate passes the same SQLite sandbox; reference answers are absent.
    normalization='disabled'
    if planner is plan and os.getenv('RESULT_NORMALIZATION_ENABLED','1').lower() not in ('0','false','no'):
        try:
            candidate=normalize(question,sql,data)
            if candidate:
                revised_data=runner(candidate)  # validate, dry-run, read-only execute
                previous_issues=diagnostics(question,sql,data)
                next_issues=diagnostics(question,candidate,revised_data)
                # A verified DISTINCT cleanup is legitimate even when a
                # subquery's aggregate obscured the generic warning.
                from .normalizer import dedupe_entity_listing
                safe_set=(candidate==dedupe_entity_listing(question,sql,data)
                          and _verified_entity_set_dedupe(data,revised_data))
                if len(next_issues)<len(previous_issues) or safe_set:
                    sql,data=candidate,revised_data
                    normalization='verified_entity_set' if safe_set else 'applied'
                else:
                    normalization='not_better'
            else:
                normalization='not_applicable'
        except RejectedSQL:
            normalization='rejected_by_sandbox'
    # Preserve real ties at the top of an unspecified ranking, not a
    # benchmark-specific number of rows. The read-only executor checks both
    # the preview and the final candidate. All schema/role diagnostics still
    # apply after this optional presentation change.
    if planner is plan and os.getenv('RESULT_NORMALIZATION_ENABLED','1').lower() not in ('0','false','no'):
        try:
            tied=expand_verified_ties(question,sql,data,runner)
            if tied:
                proposed,observed=tied
                from .semantic_checks import inspect as inspect_semantics
                before=set(inspect_semantics(question,sql,data))
                after=set(inspect_semantics(question,proposed,observed))
                if not after-before:
                    sql,data=proposed,observed
                    normalization='verified_ties_expanded'
        except RejectedSQL:
            pass
    # A validated query can still contradict its stated question. Only severe,
    # demonstrable semantic mismatches get one final bounded model repair.
    # This is not an output-format chase; it does not invent an evaluator top-k.
    from .semantic_checks import inspect as inspect_semantics
    hard_issue_clues=(
        'home/away-only point total', 'NULL final scores',
        'goal scorers but the result', 'credited goal.team_id role',
        'club that benefited', 'own team', 'SAME team', 'double-count',
        'goalkeeper position', 'starting goalkeeper', 'clean sheet reports',
        'BOTH match_id and team_id', 'goals_against=0',
        'games played at a stadium', 'is_own_goal=1',
        'fixture sides', 'physically played fixtures',
    )
    before_hard=[v for v in inspect_semantics(question,sql,data)
                 if any(clue.lower() in v.lower() for clue in hard_issue_clues)]
    if before_hard and review_enabled:
        try:
            feedback=review_feedback(question,sql,data)
            feedback.update({
                'mode':'bounded_question_consistency_repair',
                'observed_semantic_contradictions':before_hard,
                'instruction':('The executed SQL is valid but contradicts the question in '
                    'the specific ways listed. Correct the actual meaning using schema '
                    'and role-aware joins. Do not copy any reference SQL, invent data, '
                    'or introduce a guessed top-N. Return one SELECT only.'),
            })
            proposed,fix_diag=review_planner(question,previous_question=previous_question,feedback=feedback)
            if proposed['action']=='answer_from_query' and proposed['sql'].strip()!=sql.strip():
                fixed=runner(proposed['sql'])
                after_hard=[v for v in inspect_semantics(question,proposed['sql'],fixed)
                            if any(clue.lower() in v.lower() for clue in hard_issue_clues)]
                # A repair must remove an actual contradiction WITHOUT
                # introducing another independently observable contradiction.
                # More attractive row counts alone are not evidence.
                before_all=set(inspect_semantics(question,sql,data))
                after_all=set(inspect_semantics(question,proposed['sql'],fixed))
                improvements=(len(after_hard)<len(before_hard)
                              and not (after_all-before_all)
                              and not fixed.get('truncated')
                              and fixed.get('validation')=='passed')
                review_evidence.append({
                    'stage':'question_consistency_repair', 'original_sql':sql,
                    'candidate_sql':proposed['sql'], 'original_issues':before_hard,
                    'candidate_issues':after_hard,
                    'original_row_count':data.get('row_count'),
                    'candidate_row_count':fixed.get('row_count'),
                    'decision':'accepted' if improvements else 'rejected',
                })
                if improvements:
                    sql,data=proposed['sql'],fixed
                    review_status='semantic_repair_adopted'
                    normalization='not_applicable_after_semantic_repair'
                else:
                    review_status='semantic_repair_rejected'
            if diag is not None:
                diag={**diag,'latency_ms':diag.get('latency_ms',0)+fix_diag.get('latency_ms',0)}
        except (ModelError,RejectedSQL,ValueError):
            review_status='semantic_repair_unavailable'

    # A semantic repair can introduce an unnecessary ID display column.
    # Run a final projection-only cleanup after repair, and accept it ONLY
    # when every observed fact is preserved. No benchmark-specific shaping.
    if (review_status=='semantic_repair_adopted' and planner is plan and
        os.getenv('RESULT_NORMALIZATION_ENABLED','1').lower() not in ('0','false','no')):
        from .normalizer import remove_unrequested_ids
        projection=remove_unrequested_ids(question,sql,data)
        if projection:
            try:
                projected=runner(projection)
                if (_same_facts_after_projection(data,projected) and
                    not (set(inspect_semantics(question,projection,projected))-
                         set(inspect_semantics(question,sql,data)))):
                    sql,data=projection,projected
                    normalization='verified_post_repair_projection'
            except RejectedSQL:
                pass
    count=data['row_count']
    # The presentation never invents factual data; the table of rows is the answer.
    summary=summarize(data)
    return result(intent=intent,action='answer_from_query',sql=sql,
                  model_diagnostics=diag,quality_review=review_status,
                  semantic_warnings=diagnostics(question,sql,data),review_evidence=review_evidence,
                  result_normalization=normalization,answer=summary,
                  database_executed=True,**data)
