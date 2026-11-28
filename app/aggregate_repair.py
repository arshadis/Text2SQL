"""Conservative correction of SQLite COUNT(boolean), never an answer template.

Only simple equality against a literal in a numeric count/points request.
No gold questions, row counts, or SQL are loaded. The caller validates and
executes the replacement through the normal read-only sandbox.
"""
from __future__ import annotations
import re
from .db import scrub_noncode

_METRIC = re.compile(r'\b(?:points?|count|number|how many|total)\b|امتیاز|تعداد|چند', re.I)
_COUNT = re.compile(r"\bCOUNT\s*\(\s*((?:[A-Za-z_]\w*\.)?[A-Za-z_]\w*\s*=\s*(?:'[^']*'|[0-9]+))\s*\)", re.I)


def conditional_count_candidate(question: str, sql: str) -> str | None:
    if not isinstance(sql,str) or not _METRIC.search(question):
        return None
    clean = scrub_noncode(sql)
    edits=[]
    for match in _COUNT.finditer(sql):
        # Do not rewrite examples inside string literals or SQL comments.
        if clean[match.start():match.start()+5].upper() != 'COUNT':
            continue
        edits.append((match.start(),match.end(),f'COUNT(CASE WHEN {match.group(1)} THEN 1 END)'))
    if not edits:
        return None
    for start,end,replacement in reversed(edits):
        sql=sql[:start]+replacement+sql[end:]
    return sql
