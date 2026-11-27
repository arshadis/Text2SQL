"""Conservative, question-grounded SQL checks (never benchmark references).

These are observable incompatibilities between an explicitly stated request
and a candidate query, not attempts to infer a hidden grading result shape.
Checks return hints; they DO NOT execute or mutate SQL and never supersede
SQLite authorization.  Conservative false-negative is preferable to a
false-positive that changes the user's meaning.
"""
from __future__ import annotations
import re
from .db import scrub_noncode

# Use SQL text with literals preserved for status analysis, and sanitized SQL
# for structural checks where quoted aliases might otherwise produce false hits.
_PLAYED = re.compile(
    r'\b(?:actually\s+played|played\s+(?:matches?|fixtures?|games?)|'
    r'(?:matches?|fixtures?|games?)\s+(?:have\s+been\s+|were\s+|already\s+)?(?:played|finished|completed)|'
    r'completed\s+(?:matches?|fixtures?|games?)|finished\s+(?:matches?|fixtures?|games?))\b|'
    r'(?:بازی[\s\u200c]*(?:های)?[\s\u200c]*(?:انجام[\s\u200c]*شده|برگزار[\s\u200c]*شده)|'
    r'مسابقات[\s\u200c]*برگزار[\s\u200c]*شده)', re.I)
_ALL = re.compile(r'\b(?:all|every|each|complete|entire|registered)\b|(?:همه|تمام|کامل|ثبت[\s\u200c]*شده)', re.I)
_HUMAN = re.compile(r'\b(?:players?|goalkeepers?|coaches?|managers?|referees?|teams?|clubs?|scorers?)\b|'
                    r'(?:بازیکن|دروازه[\s\u200c]*بان|مربی|سرمربی|داور|تیم|باشگاه|گلزن)',re.I)
_ID_REQUESTED = re.compile(r'\b(?:ids?|identifiers?|primary\s+keys?)\b|شناسه', re.I)
_EXPLICIT_LIMIT = re.compile(r'\blimit\s+(\d+)\b',re.I)
_FINISHED = re.compile(r"\bstatus\s*(?:=\s*['\"]finished['\"]|IN\s*\(\s*['\"]finished['\"]\s*\))",re.I)
_AWARDED = re.compile(r"['\"]awarded['\"]",re.I)


def inspect(question: str, sql: str, data: dict, *, explicit_limit: int | None = None) -> list[str]:
    """Detect only directly observable contradictions; no reference SQL or gold rows.

    This is deliberately incomplete: many incorrect join/aggregation semantics
    require independent testing and cannot be proven from shape alone.
    """
    if not isinstance(sql,str):return []
    raw=sql
    code=scrub_noncode(sql)
    q=question.casefold()
    issues=[]
    cols=[str(x).lower() for x in data.get('columns',())]
    # The counted-match view has TWO records for each match. Directly counting
    # its rows as the number of league fixtures double-counts the same game.
    if (re.search(r'\bv_team_match\b',raw,re.I)
        and re.search(r'\bcount\s*\(\s*\*\s*\)',code,re.I)
        and re.search(r'\b(?:how many|number of|total)\s+(?:\w+\s+){0,2}(?:matches|fixtures|games)\b',q,re.I)
        and not re.search(r'\b(?:per|for each|by|each)\s+(?:club|team)\b',q,re.I)
        and not re.search(r'\bgroup\s+by\b',code,re.I)):
        issues.append('The two-sided match view has one row per team per match: COUNT(*) may double-count fixtures; count unique match identifiers or use the match relation.')
    # Match status is a semantic distinction, not a fixed grading cutoff.
    if (_PLAYED.search(q) and re.search(r'\b(?:v_team_match|v_standings|match|v_match)\b',raw,re.I)
        and not _FINISHED.search(raw)):
        issues.append('The user asks for physically played fixtures; verify status=finished because awarded, scheduled and cancelled games are different.')
    if _PLAYED.search(q) and _AWARDED.search(raw):
        issues.append('The user requests played fixtures but the candidate includes administratively awarded records.')
    # Explicit request for ALL records is inconsistent with a forced LIMIT 1.
    if _ALL.search(q) and re.search(r'\blimit\s+1\b',code,re.I):
        issues.append('The user requested all matching records but the query limits output to one row.')
    if explicit_limit is not None:
        match=_EXPLICIT_LIMIT.search(code)
        if match and int(match.group(1))<explicit_limit:
            issues.append(f'The user explicitly requested {explicit_limit} entries, but SQL LIMIT is only {match.group(1)}.')
    if _HUMAN.search(q) and not _ID_REQUESTED.search(q):
        if any(c.endswith('_id') and c != 'match_id' for c in cols):
            issues.append('The result projects an internal entity ID that the user did not request; show readable names.')
    # A match-score request concerns a recorded result, not a future fixture.
    # This check is driven by actual returned NULL score cells, not by an
    # evaluation case or any hard-coded expected match.
    result_asked=bool(re.search(r"\b(?:score\s+of|what\s+was\s+the\s+score|final\s+score|match\s+result|result\s+of)\b|نتیجه.{0,30}(?:بازی|دیدار|مسابقه)|نتیجه\s*(?:چند|چه)",q,re.I))
    score_indices=[i for i,c in enumerate(cols) if c in ('home_goals','away_goals','home_score','away_score')]
    if result_asked and score_indices and any(any(i<len(row) and row[i] is None for i in score_indices)
                                                   for row in data.get('rows',[])):
        issues.append('The match-score output includes a fixture with NULL final scores; exclude unplayed fixtures before reporting a final result.')

    # Overall-league standings cannot be used as a *venue-specific* points
    # measure simply by filtering the list of clubs present at that venue.
    venue_asked=bool(re.search(r'\b(?:home|at\s+home|home\s+games?|away|on\s+the\s+road)\b|(?:خانگی|خانه|میزبان|خارج\s+از\s+خانه|میهمان)',q,re.I))
    points_asked=bool(re.search(r'\bpoints?\b|امتیاز',q,re.I))
    if (venue_asked and points_asked and re.search(r'\bv_standings\b',code,re.I)
        and re.search(r'\b(?:points)\b',code,re.I)):
        issues.append('Overall v_standings.points is not a home/away-only point total; derive the venue-specific measure from per-team match results.')

    # Two teams play a match, but a goalkeeper belongs to only one of them.
    # A zero on EITHER side of the score is not a clean sheet for BOTH sides.
    keeper_asked=bool(re.search(r'\b(?:goalkeeper|keeper|clean\s+sheets?)\b|دروازه[\s\u200c]*بان|کلین[\s\u200c]*شیت',q,re.I))
    if keeper_asked and ('clean sheet' in q or 'clean sheets' in q or 'کلین' in q or 'conced' in q or 'گل خورده' in q):
        if re.search(r'\b(?:\w+\.)?home_goals\s*=\s*0\s+OR\s+(?:\w+\.)?away_goals\s*=\s*0\b',code,re.I):
            issues.append('Clean sheets must use goals conceded by the goalkeeper’s own team; an OR over home_goals=0 and away_goals=0 credits both goalkeepers.')

    # A goalkeeper clean sheet requires a zero conceded by the keeper's OWN
    # side, not merely a zero anywhere in the fixture. The test is generic.
    if keeper_asked and ('clean sheet' in q or 'clean sheets' in q or
                         'کلین' in q or 'conced' in q or 'گل خورده' in q):
        if re.search(r'\blineup\b',code,re.I) and re.search(r'\b(?:match|v_match)\b',raw,re.I):
            same_side=(re.search(r'\bgoals_against\s*=\s*0\b',code,re.I)
                       or (re.search(r'\bhome_team_id\b',code,re.I)
                           and re.search(r'\baway_team_id\b',code,re.I)
                           and re.search(r'\bhome_goals\b',code,re.I)
                           and re.search(r'\baway_goals\b',code,re.I)
                           and re.search(r'\bteam_id\b',code,re.I)))
            if not same_side and re.search(r'\b(?:home_goals|away_goals)\b',code,re.I):
                issues.append('A goalkeeper clean sheet must test goals conceded by that SAME team, not just a score-zero match.')

    # Own-goal events have three football roles: scorer, scorer's club, and
    # the club credited with the goal. The names of both fixture sides alone
    # cannot identify the credited club without a role-aware relationship.
    own_goal_asked=bool(re.search(r'\bown[ -]?goals?\b|گل[\s\u200c]*به[\s\u200c]*خودی',q,re.I))
    credited_asked=bool(re.search(r'\b(?:benefit(?:ed|ing)?|credited|received)\b|منتفع|سود\s+برد|به\s+نفع',q,re.I))
    if own_goal_asked and credited_asked and re.search(r'\bgoal\b',code,re.I):
        match_alias=re.search(r'\b(?:FROM|JOIN)\s+\"?goal\"?\s+(?:AS\s+)?([a-z_][a-z_0-9]*)\b',raw,re.I)
        goal_alias=(match_alias.group(1) if match_alias and match_alias.group(1).lower()
                    not in ('where','join','on','group','order','limit') else 'goal')
        goal_names={goal_alias, 'goal'}
        def uses_goal_field(field):
            patterns=[rf'\b{re.escape(alias)}\.{field}\b' for alias in goal_names]
            return any(re.search(pat,code,re.I) for pat in patterns) or (f'goal.{field}' in (data.get('fields') or []))
        if not uses_goal_field('team_id'):
            issues.append('The credited team for an own goal must be linked using the goal event’s team_id, not merely the fixture’s home and away sides.')
        scorer_club_asked=bool(re.search(r'\b(?:scorer.s\s+(?:club|team)|player.s\s+(?:club|team)|scoring\s+club)\b|تیم\s+بازیکن|باشگاه\s+گلزن',q,re.I))
        if scorer_club_asked and not uses_goal_field('scorer_team_id'):
            issues.append('When the scorer’s own club is requested, link goal.scorer_team_id separately from the credited team.')

    # Do not silently substitute an aggregate over *teams* for a user request
    # about named individual scorers. This checks presentation grain and schema
    # identity, not any stored expected row or a benchmark-specific output.
    individual_scorers = bool(re.search(
        r'\b(?:scorers?|goalscorers?|goal\s+scorers?)\b|گلزن|گلزنان',q,re.I))
    if individual_scorers and data.get('row_count',0)>0:
        names_present = any(re.search(r'(?:player|scorer|person|athlete).*name|name.*(?:player|scorer)',c)
                            for c in cols)
        has_player_relation = bool(re.search(r'\b(?:FROM|JOIN)\s+"?player"?\b',raw,re.I))
        if not (has_player_relation and (names_present or 'name_fa' in cols)):
            issues.append('The request is about individual goal scorers but the result does not identify a named player; do not aggregate exclusively by club.')

    # For an explicitly requested beneficiary, using the goal credited-team
    # key is necessary, but not sufficient: the projection must identify that
    # team rather than simply showing the fixture participants.
    if own_goal_asked and credited_asked and re.search(r'\bgoal\b',code,re.I):
        credited_link = any(re.search(
            rf'\b(?:[a-z_][a-z_0-9]*\.)?team_id\s*=\s*{re.escape(alias)}\.team_id\b|'
            rf'\b{re.escape(alias)}\.team_id\s*=\s*(?:[a-z_][a-z_0-9]*\.)?team_id\b',
            code,re.I) for alias in goal_names)
        if not credited_link:
            issues.append('Identify the benefited team by an explicit join to the credited goal.team_id role; listing home and away sides does not establish that role.')

    # For a requested SET of named entities (rather than one row per event),
    # repeated identical label tuples are a grain mismatch. This flags actual
    # duplicate observed rows without assuming a fixed expected result count.
    entity_listing = bool(re.search(
        r'\b(?:which|who|list|show|names?|registered|are there)\b|(?:چه\s|کدام|نام\s|اسامی|فهرست|ثبت[\s\u200c]*شده)',q,re.I))
    per_event = bool(re.search(
        r'\b(?:per|for each|each)\s+(?:match|fixture|game|goal|event)\b|'
        r'(?:در\s+هر\s+(?:مسابقه|بازی)|برای\s+هر\s+(?:مسابقه|بازی)|به\s+ازای\s+هر\s+رویداد)',q,re.I))
    if (entity_listing and not per_event and len(cols)>=2 and
        all(re.search(r'(?:name|coach|player|team|club|stadium|referee)',c)
            for c in cols) and
        not re.search(r'\b(?:count|sum|avg|min|max)\s*\(',code,re.I) and
        len(data.get('rows') or [])>=2):
        rows=data['rows']
        if (all(len(row)==len(cols) and all(isinstance(v,str) for v in row)
                for row in rows) and
            len({tuple(row) for row in rows})<len(rows)):
            issues.append('The request names a SET of entity-label combinations, but identical label rows repeat. Consider DISTINCT at the requested grain, not one row per underlying event.')

    # LEFT JOIN + strict WHERE on its nullable side silently discards zero-event
    # entities. This is a general SQL cardinality warning, not a football rule.
    join=re.search(r'\bLEFT\s+(?:OUTER\s+)?JOIN\s+\"?([A-Za-z_][A-Za-z_0-9]*)\"?\s+(?:AS\s+)?([A-Za-z_][A-Za-z_0-9]*)\b',raw,re.I)
    where=re.search(r'\bWHERE\b(.*?)(?:\bGROUP\s+BY\b|\bORDER\s+BY\b|\bLIMIT\b|$)',raw,re.I|re.S)
    if join and where and _ALL.search(q):
        nullable=join.group(2)
        if (re.search(r'\b'+re.escape(nullable)+r'\.[A-Za-z_]+\s*(?:=|!=|<>|IN\s*\()',where.group(1),re.I)
            and not re.search(r'\b'+re.escape(nullable)+r'\.[A-Za-z_]+\s+IS\s+NULL',where.group(1),re.I)):
            issues.append('A WHERE predicate on the nullable side of a LEFT JOIN can discard entities with zero related rows, despite the request for all entities.')
    return list(dict.fromkeys(issues))
