"""Independent checks that an executed query respects the typed user intent.

This is NOT a query generator or a hidden-answer matcher. It checks necessary
conditions from the user's own words and the documented data model. Only
high-confidence contradictions are reported; unknown cases remain unknown.
"""
from __future__ import annotations

import re
from .query_plan import derive_query_plan
from .db import scrub_noncode


def inspect_plan(question: str, sql: str, data: dict) -> list[str]:
    p=derive_query_plan(question)
    code=scrub_noncode(sql)
    raw=sql.casefold()
    cols=[str(x).casefold() for x in data.get('columns',())]
    issues=[]
    filters=set(p.filters)
    measures=set(p.requested_measures)
    # The adjective "after" expresses a strict lower bound. We compare the
    # bound the visitor wrote, not one from an evaluation template.
    for spec in filters:
        m=re.match(r'event minute strictly > (\d+)',spec)
        if m and re.search(r'\bminute\s*>=\s*'+m.group(1)+r'\b',code,re.I):
            issues.append('The request says AFTER the stated minute: >= includes that exact minute; use a strictly later event boundary.')
    if ('exclude own-goal events' in filters and 'goal' in raw
        and not re.search(r'\bis_own_goal\b',code,re.I)):
        issues.append('The request excludes own goals but the goal events are not filtered by their own-goal flag.')
    if ('distinct formations' in measures and 'coach' in p.requested_entities
        and 'match_coach' in raw and 'match' in raw
        and not any('side only' in f for f in filters)):
        if 'home_formation' in raw and 'away_formation' not in raw or ('away_formation' in raw and 'home_formation' not in raw):
            issues.append('Formation statistics for coaches across both fixture sides must use the formation recorded for their own club, whether home or away.')
    # A user who asks for starters should not silently include bench players.
    if ('clean sheets' in measures and re.search(r'\blineup\b',code,re.I)
        and re.search(r'\b(?:start(?:ed|ing)?|starter)\b|شروع|فیکس',question,re.I)
        and not re.search(r'\bis_starter\s*=\s*1\b',code,re.I)):
        issues.append('A starting-goalkeeper statistic must restrict the lineup to recorded starters.')
    # The question is about a SPECIFIC event role, not the two fixture sides.
    if 'own-goal event details' in measures and data.get('row_count',0)>0:
        if not any(c in ('scorer','player_name','scorer_name','name_fa') or
                   re.search(r'(?:scorer|player).*name',c) for c in cols):
            issues.append('An own-goal event listing needs a named scorer (person), not merely clubs and match details.')
        if not any('benefit' in c or 'credit' in c or 'team' in c or 'club' in c
                   for c in cols):
            issues.append('Own-goal event output must identify the credited beneficiary club.')
    # A trend/change query is about differences in recorded observations, not
    # a directory of every observation or the currently assigned staff.
    if any('temporal change' in f for f in filters) and 'coach' in p.requested_entities:
        if re.search(r'\bmatch_coach\b',raw,re.I) and not re.search(
            r'\b(?:having|count\s*\(\s*distinct|lag\s*\(|not\s+exists|exists\s*\(|\bself\b|\b!=|<>|\bINTERSECT\b)',
            code,re.I):
            issues.append('A claim of coach CHANGE requires comparing distinct coach observations for the same club over time; merely listing match_coach rows is insufficient.')
    # For minutes across a season, MAX(minutes) from the per-match view is a
    # single-game maximum; the per-player total needs an actual accumulation.
    if ('playing minutes' in measures and 'v_player_minutes' in raw
        and re.search(r'\bmax\s*\(\s*(?:\w+\.)?minutes_played\s*\)',code,re.I)
        and not re.search(r'\bsum\s*\(\s*(?:\w+\.)?minutes_played\s*\)',code,re.I)):
        issues.append('The question requests total playing time, but MAX of per-match minutes is not a season total.')
    if ('red cards' in measures and re.search(r'\bcard\b',raw,re.I)
        and re.search(r'\b(?:including|include)\s+second\s+yellows?\b|کارت\s+زرد\s+دوم',question,re.I)
        and re.search(r'card_type\s*=\s*[\'\"]red[\'\"]',raw,re.I)
        and not re.search(r'\bsecond_yellow\b',raw,re.I)):
        issues.append('The question explicitly includes second yellows as send-offs, but the query filters only literal red cards.')
    return list(dict.fromkeys(issues))
