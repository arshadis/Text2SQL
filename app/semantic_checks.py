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
_ALL = re.compile(r'\b(?:all|every|each|complete|entire)\b|(?:همه|تمام|کامل)', re.I)
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
    return list(dict.fromkeys(issues))
