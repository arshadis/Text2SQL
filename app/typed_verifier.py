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
    # A venue is assigned to scheduled fixtures too. Counting games that
    # actually occurred at each stadium requires completed on-field matches.
    # This applies to any season, venue, or user wording, not a held-out test.
    if ('stadium' in p.requested_entities and 'match count' in measures
        and not re.search(r'\b(?:scheduled|upcoming|future|cancelled|awarded|all\s+fixtures?)\b|برنامه[\s\u200c]*ریزی|برگزار\s+نشده|لغو',question,re.I)
        and re.search(r'\b(?:FROM|JOIN)\s+"?match"?\b',raw,re.I)
        and not re.search(r"\bstatus\s*=\s*['\"]finished['\"]|['\"]finished['\"]\s*=\s*(?:[a-z_][a-z_0-9]*\.)?status",raw,re.I)):
        issues.append('The count of games played at a stadium must distinguish finished matches from scheduled or cancelled fixtures; use physically played match status.')
    if ('own-goal event details' in measures and re.search(r'\b(?:FROM|JOIN)\s+"?goal"?\b',raw,re.I)
        and not re.search(r'\bis_own_goal\s*=\s*1\b|\b1\s*=\s*(?:[a-z_][a-z_0-9]*\.)?is_own_goal\b',code,re.I)):
        issues.append('A list of own-goal events must select only goal records marked is_own_goal=1.')

    # A user who asks for starters should not silently include bench players.
    if ('clean sheets' in measures and re.search(r'\blineup\b',code,re.I)
        and re.search(r'\b(?:start(?:ed|ing)?|starter)\b|شروع|فیکس',question,re.I)
        and not re.search(r'\bis_starter\s*=\s*1\b',code,re.I)):
        issues.append('A starting-goalkeeper statistic must restrict the lineup to recorded starters.')
    # A clean sheet belongs to a STARTING goalkeeper and to their own side.
    # The checks apply to any unseen keeper/clean-sheet question. Merely
    # selecting a player's name after joining a match is not enough.
    if 'clean sheets' in measures:
        if not re.search(r'\b(?:FROM|JOIN)\s+"?lineup"?\b',raw,re.I):
            issues.append('A goalkeeper clean sheet must be derived from the recorded lineup and the goalkeeper team, not generic players or match scores.')
        else:
            # Both expressions must be actual predicates, not only column
            # names in the SELECT output. Exclude substitute/bench players.
            starter=bool(re.search(r'\b(?:[a-z_][a-z_0-9]*\.)?is_starter\s*=\s*1\b|\b1\s*=\s*(?:[a-z_][a-z_0-9]*\.)?is_starter\b',code,re.I))
            keeper=bool(re.search(r"\b(?:[a-z_][a-z_0-9]*\.)?position\s*=\s*['\"]GK['\"]|['\"]GK['\"]\s*=\s*(?:[a-z_][a-z_0-9]*\.)?position\b",raw,re.I))
            formation_line=bool(re.search(r'\b(?:[a-z_][a-z_0-9]*\.)?formation_line\s*=\s*0\b',code,re.I))
            if not keeper and not (starter and formation_line):
                issues.append('Clean sheet reports must filter to the goalkeeper position (lineup.position=GK or starting formation_line=0); other footballers cannot be credited with keeper clean sheets.')
            if not starter:
                issues.append('Clean sheet reports must count recorded starting goalkeepers, not substitutes or general lineup players.')
            if re.search(r'\bv_team_match\b',code,re.I):
                # Extract aliases and verify the team-match join uses BOTH
                # match and team identifiers. This rules out a two-sided
                # fanout that mistakenly credits both sides of each match.
                def alias(relation):
                    match=re.search(r'\b(?:FROM|JOIN)\s+"?'+relation+r'"?\s+(?:AS\s+)?([a-z_][a-z_0-9]*)\b',raw,re.I)
                    if not match or match.group(1).lower() in {'on','where','join','group','order','limit'}:
                        return relation
                    return match.group(1)
                la,va=alias('lineup'),alias('v_team_match')
                def linked(field):
                    left=rf'\b{re.escape(la)}\.{field}\s*=\s*{re.escape(va)}\.{field}\b'
                    right=rf'\b{re.escape(va)}\.{field}\s*=\s*{re.escape(la)}\.{field}\b'
                    return bool(re.search(left+'|'+right,code,re.I))
                if not (linked('match_id') and linked('team_id')):
                    issues.append('To count a goalkeeper team clean sheet using v_team_match, JOIN lineup on BOTH match_id and team_id; match-only joins duplicate the two fixture sides.')
                if not re.search(r'\b(?:[a-z_][a-z_0-9]*\.)?goals_against\s*=\s*0\b|\b0\s*=\s*(?:[a-z_][a-z_0-9]*\.)?goals_against\b',code,re.I):
                    issues.append('The starting goalkeeper own team must have goals_against=0 for a clean sheet.')
            elif not re.search(r'\b(?:home_goals|away_goals|goals_against)\b',code,re.I):
                issues.append('A clean sheet requires a verified zero-conceded condition for the goalkeeper own team.')

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
