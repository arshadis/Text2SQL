"""Independent, general-purpose semantic review hints; no gold/reference answers."""
from __future__ import annotations
import re
from .contract import diagnostics, instruction

# These are schema concepts, not evaluation questions or reference SQL.
SUPPORTED_TERMS = re.compile(
    r'\b(?:coaches?|managers?|formations?|goalkeepers?|goals?|matches?|cards?|referees?|penalt(?:y|ies)|'
    r'standings|minutes|fixtures?|substitutions?|VAR|leagues?|lineups?|teams?|players?)\b|'
    r'(?:مربی|سرمربی|آرایش|ترکیب|دروازه|گل|مسابق|بازی|داور|کارت|پنالتی|'
    r'دقیقه|جدول|تیم|بازیکن|لیگ)',re.I)
UNSUPPORTED_TERMS = re.compile(
    r'\b(?:fans?|supporters?|attendance|ticket|revenue|salary|transfer fee|'
    r'prediction|tomorrow|next year|real.time)\b|'
    r'(?:هوادار|تماشاگر|بلیت|درآمد|حقوق|پیش\s?بینی|فردا)',re.I)


def reconsider_refusal(question: str) -> bool:
    """One model second opinion only when question refers to modeled concepts."""
    return bool(SUPPORTED_TERMS.search(question) and not UNSUPPORTED_TERMS.search(question))


def review_feedback(question: str, sql: str, data: dict) -> dict:
    """Use only observable draft SQL/returned DB rows; never use evaluation gold."""
    hints = [
        'Check correctness of joins, filters, groups, counts, ranking, tie treatment and output shape.',
        'Verify that returned columns are readable and relevant to the question; avoid display IDs in leaderboards.',
        'If a question requests a list, verify that the query returns an appropriate number of items.'
    ]
    q = question.lower()
    if re.search(r'\b(?:played|finished)\b|انجام\s?شده',q,re.I):
        hints.append("For played fixtures: count ONLY status='finished', not awarded or scheduled.")
    if any(str(col).lower().endswith('_id') for col in data.get('columns',())):
        hints.append('At least one output column is an internal ID; ensure the user explicitly needs it.')
    if data.get('row_count',0) == 0:
        hints.append('Zero rows: check joins/filters to avoid a false empty result.')

    if re.search(r'\b(?:most|best|top|highest)\b|بیشترین|بهترین|برتر',q,re.I):
        hints.append('Rank by a real aggregate DESC. Avoid arbitrary one-row LIMIT 1; use the requested N or an informative leaderboard, break ties by readable names.')
    if re.search(r'coach|manager|formation|مربی|آرایش',q,re.I):
        hints.append('Coach history and formations ARE available by joining match_coach, match, coach and team; use home/away-specific formations and match rounds.')
    if re.search(r'own.goals?|گل\s*به\s*خودی',q,re.I):
        hints.append('For own-goal rows, scorer club comes from scorer_team_id, benefited club from goal.team_id; include added_time as well as minute.')
    if re.search(r'own.goals?|گل\s*به\s*خودی',q,re.I):
        hints.append('Return BOTH readable clubs as separate display columns: scorer_team from goal.scorer_team_id, benefited_team from goal.team_id. Listing only benefited_team is incomplete even when all events are found.')
    if re.search(r'\b(?:team|club|teams|clubs)\b|تیم|باشگاه',q,re.I) and re.search(r'goal|scor|گل',q,re.I):
        hints.append('When counting goals credited to each team, goal.team_id is authoritative. NEVER join goal to v_team_match only on match_id: that view has TWO rows per fixture and causes double counting. Join goal.team_id directly to team, or join v_team_match on BOTH match_id and goal.team_id = team-match.team_id.')
    if re.search(r'keeper|clean.sheet|دروازه',q,re.I):
        hints.append('For a goalkeeper clean sheet, use starting GK lineup plus team-scoped match results, never just zero goal events.')
    if re.search(r'referee|yellow.card|داور|کارت\s*زرد',q,re.I):
        hints.append('A booking belongs to a referee through the match: card.match_id -> match.referee_id -> referee. Yellow means card_type=yellow.')
    if re.search(r'played|minutes|دقیقه\s*بازی',q,re.I) and re.search(r'player|بازیکن|minutes',q,re.I):
        hints.append('Sum per player/team over v_player_minutes.minutes_played rather than MAX, and select readable labels.')
    if data.get('truncated'):
        hints.append('Truncated at the safe row limit; can query reduce the result via grouping/limit?')
    problems=diagnostics(question,sql,data)
    return {
        'mode':'review_draft_for_semantic_accuracy',
        'question_derived_result_contract':instruction(question),
        'observed_contract_violations':problems,
        'instruction':'Correct EVERY observed result-contract violation, including row count, relevant display columns, tie sorting and data grain. Preserve database-derived factual accuracy. If no violations and query is accurate, keep it. No reference answers or gold queries are available.',
        'candidate_sql':sql,
        'database_columns':data.get('columns',[])[:20],
        'database_row_count':data.get('row_count'),
        'database_sample_rows':data.get('rows',[])[:4],
        'review_hints':hints,
    }



def semantic_signal(question: str, sql: str, data: dict) -> float:
    """Heuristic quality signal based on user wording + returned rows ONLY.

    Never reads evaluator questions, expected rows or gold queries. It cannot
    certify correctness and is used only to prevent obvious review regressions.
    """
    q = question.lower()
    columns = [str(c).lower() for c in data.get('columns', ())]
    rows = data.get('rows', ())
    n = data.get('row_count', len(rows))
    score = 0.0
    # A display table should not expose internal player/team IDs unless asked.
    if not re.search(r'\b(?:id|identifier|شناسه)\b', q):
        score -= 3 * sum(c.endswith('_id') and c != 'match_id' for c in columns)
    if re.search(r'\b(?:player|scorer|goalkeeper|coach|referee|team|club)\b|بازیکن|گلزن|مربی|داور|تیم',q):
        if rows and any(isinstance(v,str) for v in rows[0]):
            score += 1
    if re.search(r'\b(?:how many|number of|count of)\b|چند(?:تا|\s+تا)?',q):
        if n==1 and 1<=len(columns)<=2: score+=2
    if re.search(r'\b(?:played|finished)\b|انجام\s*شده',q):
        if re.search(r"status\s*=\s*['\"]finished['\"]",sql,re.I): score+=4
        if re.search(r"['\"]awarded['\"]",sql,re.I): score-=5
    # For an *explicit* N, the user decides the number of returned entries.
    m = re.search(r'\btop\s+(\d+)\b|(?:^|\s)([۱-۹0-9]+)\s*\S*برتر',q)
    if m:
        try:
            expected_n=int((m.group(1) or m.group(2)).translate(str.maketrans('۰۱۲۳۴۵۶۷۸۹','0123456789')))
            if expected_n>0: score-=min(5,abs(n-expected_n))
        except ValueError: pass
    else:
        # A qualitative leaderboard should not degrade to one arbitrary row,
        # but a single standings leader is a well-defined exception.
        rank=bool(re.search(r'\b(?:most|best|highest|top)\b|بیشترین|بهترین|برتر',q))
        single_leader=bool(re.search(r'\b(?:top of the league|league leader)\b|صدرنشین|صدر جدول',q))
        if rank and not single_leader:
            if n==1: score-=2
            elif 2<=n<=5: score+=2
            elif n>15: score-=1
    if re.search(r'\b(?:all|every)\b|همه|تمام',q) and n>1:
        score+=2
    if data.get('truncated'): score-=3
    return score
