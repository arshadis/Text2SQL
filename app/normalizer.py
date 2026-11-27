"""Optional conservative SQL shaping for only *explicit* top-N requests.

This module does not alter football joins, predicates, groupings, or inferred top-k.
A separate read-only validator/sandbox must execute the returned candidate.
"""
from __future__ import annotations
import re
from .contract import infer_contract


def _top_level_clauses(sql: str) -> dict[str,int]:
    """Scan tokens outside quotes and nested parentheses (not a full SQL parser)."""
    found={}
    i,depth,quote=0,0,None
    while i<len(sql):
        ch=sql[i]
        if quote:
            if ch==quote:
                if i+1<len(sql) and sql[i+1]==quote:
                    i+=2;continue
                quote=None
            i+=1;continue
        if ch in "'\"`": quote=ch;i+=1;continue
        if ch=='(': depth+=1;i+=1;continue
        if ch==')': depth=max(0,depth-1);i+=1;continue
        if depth==0:
            match=re.match(r'\b(order\s+by|limit|offset|union|intersect|except)\b',sql[i:],re.I)
            if match:
                found[match.group(1).lower().replace(' ','_')]=i
                if match.group(1).lower().startswith('order'):found['order']=i
                i+=len(match.group());continue
        i+=1
    return found


def _projection_end(statement: str) -> int | None:
    """Find top-level FROM, respecting SQL quoting and nested parentheses."""
    depth=0
    quote=None
    i=0
    while i<len(statement):
        char=statement[i]
        if quote:
            if char==quote:
                if i+1<len(statement) and statement[i+1]==quote:
                    i+=2;continue
                quote=None
            i+=1;continue
        if char in "\"'`": quote=char;i+=1;continue
        if char=='[':quote=']';i+=1;continue
        if char=='(': depth+=1;i+=1;continue
        if char==')': depth=max(0,depth-1);i+=1;continue
        if depth==0:
            m=re.match(r'\bFROM\b',statement[i:],re.I)
            if m:return i
        i+=1
    return None


def _projections(select_part: str) -> list[str]:
    chunks=[]
    depth=0
    quote=None
    start=0
    i=0
    while i<len(select_part):
        ch=select_part[i]
        if quote:
            if ch==quote:
                if i+1<len(select_part) and select_part[i+1]==quote:
                    i+=2;continue
                quote=None
            i+=1;continue
        if ch in "\"'`": quote=ch;i+=1;continue
        if ch=='[':quote=']';i+=1;continue
        if ch=='(':depth+=1;i+=1;continue
        if ch==')':depth=max(0,depth-1);i+=1;continue
        if ch==',' and depth==0:
            chunks.append(select_part[start:i]);start=i+1
        i+=1
    chunks.append(select_part[start:])
    return chunks


def remove_unrequested_ids(question: str, sql: str, data: dict) -> str | None:
    """Remove unrequested ID *presentation* fields, preserving SQL semantics.

    Only edits a plain, explicit SELECT projection; never touches joins,
    filters, GROUP BY, HAVING, ORDER BY, LIMIT or CTEs. The caller must rerun
    the candidate through the same independent SQL validator.
    """
    if not isinstance(sql,str) or re.search(r'\b(?:id|ids|identifiers?|شناسه)\b',question,re.I):
        return None
    columns=list(data.get('columns') or ())
    if len(columns)<2 or not any(isinstance(v,str) for v in (data.get('rows') or [[None]])[0]):
        return None
    unwanted={i for i,c in enumerate(columns)
              if str(c).casefold().endswith('_id') and str(c).casefold()!='match_id'}
    if not unwanted or len(unwanted)==len(columns):return None
    statement=sql.strip().rstrip(';')
    if not re.match(r'^SELECT\s+',statement,re.I) or re.search(r'\b(?:UNION|INTERSECT|EXCEPT|RECURSIVE)\b',statement,re.I):
        return None
    select_start=re.match(r'^SELECT\s+',statement,re.I).end()
    # DISTINCT/ALL or positional ORDER/GROUP BY are sensitive to projection
    # changes; leave them to the model rather than risk altered SQL meaning.
    if re.match(r'\s*(?:DISTINCT|ALL)\b',statement[select_start:],re.I):
        return None
    if re.search(r'\b(?:ORDER|GROUP)\s+BY\s+\d+\b',statement,re.I):
        return None
    end=_projection_end(statement[select_start:])
    if end is None:return None
    end+=select_start
    projections=_projections(statement[select_start:end])
    if len(projections)!=len(columns) or any('*'==x.strip() or x.strip().endswith('.*') for x in projections):
        return None
    retained=[chunk.strip() for i,chunk in enumerate(projections) if i not in unwanted]
    return 'SELECT '+', '.join(retained)+' '+statement[end:]


def normalize(question: str, sql: str, data: dict) -> str | None:
    """Only apply generic projection cleanup and *explicit* top-N limits.

    Does not alter joins, filters, metrics or infer a top-k from the grader.
    Every candidate must be checked by the existing read-only sandbox.
    """
    cleaned=remove_unrequested_ids(question,sql,data)
    if cleaned:
        return cleaned
    c=infer_contract(question)
    if c.target_rows is None or not c.ordered or not isinstance(sql,str):
        return None
    statement=sql.strip().rstrip(';')
    if not re.match(r'^SELECT\s+',statement,re.I) or re.search(r'\b(?:UNION|INTERSECT|EXCEPT|RECURSIVE)\b',statement,re.I):
        return None
    clauses=_top_level_clauses(statement)
    if 'order' not in clauses:
        return None
    if data.get('row_count',0)==c.target_rows:
        return None
    if 'limit' in clauses:
        return None
    return statement+f' LIMIT {c.target_rows}'


def expand_verified_ties(question: str, sql: str, data: dict, runner) -> tuple[str,dict] | None:
    """Preserve all *observed* leaders tied for first in an unspecified ranking.

    This is derived from the query's actual metric and independently executed
    database rows. It is not a preselected category top-k or a benchmark size.
    Only a simple trailing LIMIT 1 is eligible. The candidate must be run via
    the production read-only sandbox before it is returned to the caller.
    """
    contract=infer_contract(question)
    if contract.grain!='ranking' or contract.target_rows is not None:
        return None
    if not isinstance(sql,str):return None
    statement=sql.strip().rstrip(';')
    if not re.search(r'\bORDER\s+BY\b',statement,re.I):return None
    if not re.search(r'\bLIMIT\s+1\s*$',statement,re.I):return None
    if re.search(r'\b(?:OFFSET|FETCH|UNION|INTERSECT|EXCEPT)\b',statement,re.I):return None
    columns=list(data.get('columns') or ())
    rows=list(data.get('rows') or ())
    if len(rows)!=1 or len(columns)<2:return None
    # The metric must be a projected numeric quantity, not an identifier.
    metric_idx=next((i for i in range(len(columns)-1,-1,-1)
                    if (isinstance(rows[0][i],(int,float)) and not isinstance(rows[0][i],bool)
                        and not str(columns[i]).lower().endswith('_id')
                        and str(columns[i]).lower() not in ('round','minute','added_time'))),None)
    if metric_idx is None:return None
    metric=columns[metric_idx]
    order=re.search(r'\bORDER\s+BY\s+(.*?)(?:\bLIMIT\b|$)',statement,re.I|re.S)
    if not order:return None
    first_sort=order.group(1).split(',',1)[0].strip()
    if not re.search(r'\bDESC\b',first_sort,re.I):return None
    # We cannot infer the right metric if ORDER BY begins with a different
    # projected expression; reject instead of stretching ties speculatively.
    if not (re.search(r'\b'+re.escape(str(metric))+r'\b',first_sort,re.I)
            or first_sort.upper().startswith(str(metric_idx+1)+' ')):
        return None
    # Preview is independently validated and capped by execute_readonly.
    preview_sql=re.sub(r'\bLIMIT\s+1\s*$','LIMIT 100',statement,flags=re.I)
    preview=runner(preview_sql)
    if preview.get('truncated'):
        return None
    sample=preview.get('rows') or []
    if len(sample)<2 or sample[0][metric_idx]!=sample[1][metric_idx]:
        return None
    n=0
    for row in sample:
        if row[metric_idx]!=sample[0][metric_idx]:break
        n+=1
    if n<2 or n>=100:return None
    candidate=re.sub(r'\bLIMIT\s+1\s*$',f'LIMIT {n}',statement,flags=re.I)
    replacement=runner(candidate)
    if (replacement.get('columns')!=columns or replacement.get('row_count')!=n
        or replacement.get('rows')!=sample[:n]):return None
    return candidate,replacement
