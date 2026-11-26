"""Generic, user-derived response contracts. No reference-question templates.

Only explicitly requested counts and ordinary linguistic output rules appear here;
no benchmark-specific top-k sizes, event recipes, or metric thresholds.
"""
from __future__ import annotations
import re
from dataclasses import dataclass

@dataclass(frozen=True)
class Contract:
    grain: str
    target_rows: int | None = None
    ordered: bool = False
    show_names: bool = False
    needs_team: bool = False
    match_result: bool = False
    unique_metric: bool = False
    all_events: bool = False
    rule: str = ''

_NUMS = str.maketrans('۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩','01234567890123456789')


def infer_contract(question: str) -> Contract:
    q = question.casefold()
    if re.search(r'\b(?:fans?|supporters?|attendance|spectators?|tickets?|revenue|salar(?:y|ies)|transfer fees?|predictions?)\b|هوادار|تماشاگر|بلیت|درآمد|حقوق\s*بازیکن|پیش\s*بینی', q):
        return Contract('not recorded by the database', rule='The requested metric is not recorded.')
    n = None
    explicit = re.search(r'\b(?:top|first)\s+(\d+)\b|(?:^|\s)([۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩0-9]+)\s*\S*\s*برتر', q)
    if explicit:
        value = (explicit.group(1) or explicit.group(2)).translate(_NUMS)
        n = max(1,min(100,int(value)))
    all_events = bool(re.search(r'\b(?:list all|show all|all|every)\b|همه|تمام',q))
    rank = bool(re.search(r'\b(?:most|highest|top|best|leaders?|leading)\b|بیشترین|بهترین|برترین|صدر',q))
    leader = bool(re.search(r'\b(?:top of the (?:league|table)|league leader|table leader)\b|صدرنشین|صدر جدول',q))
    names = bool(re.search(r'\b(?:player|players|team|teams|clubs?|coaches?|managers?|referees?|scorers?|goalkeepers?)\b|بازیکن|تیم|باشگاه|مربی|سرمربی|داور|گلزن|دروازه\s*بان',q))
    club = bool(re.search(r'\b(?:team|teams|club|clubs|with their team|with their club)\b|تیم|باشگاه',q))
    # A *single* league-table leader is requested explicitly by this phrasing.
    if leader and n is None:
        return Contract('single standings leader',1,True,True,True,rule='Return the single leading league-table entry.')
    if all_events:
        return Contract('complete listing',None,False,names,club,all_events=True,rule='Return all matching records within the database safety limit.')
    if rank or n is not None:
        return Contract('ranking',n,True,names,club,rule='Order by the requested metric; for ties use a stable readable label. Never assume a fixed top-k unless specified.')
    return Contract('answer from recorded data',show_names=names,needs_team=club)


def diagnostics(question: str, sql: str, data: dict) -> list[str]:
    """Check only *observable, generic* issues in a draft SQL and its rows."""
    c = infer_contract(question)
    columns = [str(x).casefold() for x in data.get('columns',())]
    rows = data.get('rows') or []
    row_count = int(data.get('row_count',len(rows)))
    issues = []
    if c.target_rows is not None and row_count>c.target_rows:
        issues.append(f'User explicitly requested at most {c.target_rows} entries; got {row_count}.')
    if c.target_rows is not None and row_count==0 and rows==[]:
        issues.append('The request yielded zero rows. Verify that joins and filters reflect the question.')
    if c.show_names and not re.search(r'\b(?:id|identifier|شناسه)\b',question.casefold()):
        ids=[name for name in columns if name.endswith('_id') and name!='match_id']
        if ids:
            issues.append('Prefer readable entity labels to internal IDs: '+', '.join(ids))
        if rows and not any(isinstance(v,str) for v in rows[0]):
            issues.append('No readable entity label in the output.')
    if c.ordered and row_count>1:
        order=re.search(r'\border\s+by\b(.*?)(?:\blimit\b|\boffset\b|;|$)',sql,re.I|re.S)
        if not order:
            issues.append('Ranking needs deterministic ORDER BY for the requested metric.')
        elif ',' not in order.group(1):
            issues.append('Consider a stable secondary tie-breaker when metrics tie.')
    if data.get('truncated'):
        issues.append('Result exceeded the read-only row cap; narrow the question if appropriate.')
    return issues


def instruction(question: str) -> dict:
    c=infer_contract(question)
    return {'result_grain':c.grain, 'target_rows':c.target_rows,
            'use_human_labels':c.show_names, 'include_club_label':c.needs_team,
            'require_played_match':False, 'sort_ties_deterministically':c.ordered,
            'result_shape_guidance':c.rule}
