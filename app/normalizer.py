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


def normalize(question: str, sql: str, data: dict) -> str | None:
    """Only enforce a number the user *actually stated*; no implicit defaults.

    Semantics of JOIN/WHERE/aggregates are never touched here. We only trim an
    overlong ordered result or append an explicit LIMIT to an already ordered
    candidate. Unparseable SELECTs are left unchanged.
    """
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
    # Do NOT remove a pre-existing restrictive LIMIT and invent more data.
    if 'limit' in clauses:
        return None
    return statement+f' LIMIT {c.target_rows}'
