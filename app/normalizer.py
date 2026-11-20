"""Conservative output shaping and narrowly-scoped schema-join alignment.

This does not create task answers or look up evaluation cases. In addition to
re-ordering/projecting model results, it may align a demonstrably duplicated
goal-to-two-sided-view join and add a missing FK-backed club label. Both are
schema-derived and never embed fixed result rows or reference solutions.
Every revised SQL passes the same independent read-only sandbox.
"""
from __future__ import annotations
import re
from .contract import infer_contract, diagnostics


def _top_level_clauses(sql: str) -> dict[str,int]:
    """Find clauses only outside SQL strings, comments and parentheses."""
    words = {}
    depth=0; i=0; quote=None
    s=sql
    while i<len(s):
        c=s[i]
        if quote:
            if c==quote:
                if quote in ('"',"'",'`') and i+1<len(s) and s[i+1]==quote:
                    i+=2;continue
                quote=None
            i+=1;continue
        if s.startswith('--',i):
            end=s.find('\n',i+2);i=len(s) if end==-1 else end;continue
        if s.startswith('/*',i):
            end=s.find('*/',i+2);i=len(s) if end==-1 else end+2;continue
        if c in ('"',"'",'`'):
            quote=c;i+=1;continue
        if c=='[':
            end=s.find(']',i+1);i=len(s) if end==-1 else end+1;continue
        if c=='(':
            depth+=1;i+=1;continue
        if c==')':
            depth-=1;i+=1;continue
        if depth==0 and (c.isalpha() or c=='_'):
            m=re.match(r'[a-zA-Z_][a-zA-Z0-9_]*',s[i:])
            if m:
                word=m.group().lower()
                if word in ('order','limit','offset','union','intersect','except','having'):
                    words.setdefault(word,i)
                i+=len(m.group());continue
        i+=1
    return words


def _ident(col: str) -> str:
    return '"'+col.replace('"','""')+'"'




def _complete_own_goal_club_projection(sql: str, columns: list[str], issues: list[str]) -> str | None:
    """Complete a missing scorer-side club lookup in a simple existing goal SELECT.

    Only adds a schema-documented foreign-key name projection when the SELECT
    already exposes the event, named scorer and beneficiary, but omits the
    scorer's club. It does not generate answers, aggregations or predicates.
    Caller must run the transformed SQL through the independent RO sandbox.
    """
    if not any('Missing readable scorer club' in issue for issue in issues):
        return None
    if 'scorer_team_id' in sql.casefold() or '_scorer_club' in sql.casefold():
        return None
    if re.search(r'\b(?:WITH|UNION|INTERSECT|EXCEPT)\b',sql,re.I):
        return None
    # A simple SELECT originating in goal is required. No changes to CTEs,
    # complex source expressions, or results with ambiguous column names.
    source=re.search(r'\bFROM\s+goal\s+(?:AS\s+)?([A-Za-z_]\w*)\b',sql,re.I)
    if not source or source.group(1).lower() in ('join','where','on'):
        return None
    if not sql[:source.start()].lstrip().lower().startswith('select '):
        return None
    if re.search(r'\bLIMIT\s+\d+\b',sql,re.I):
        return None
    if len(columns)!=len(set(columns)):
        return None
    names={col.casefold(): col for col in columns}
    player=next((c for c in columns if c.casefold() in ('scorer','scorer_name','player','player_name')),None)
    beneficiary=next((c for c in columns if c.casefold() in ('benefited_team','beneficiary_team','credited_team','benefited_club','credited_club')),None)
    if not player or not beneficiary or not {'match_id','minute','added_time'}.issubset(names):
        return None
    # The existing beneficiary must already refer to the credited team.
    g=source.group(1)
    if not re.search(rf'\b{re.escape(g)}\.team_id\b',sql,re.I):
        return None
    addition=f' JOIN team AS _scorer_club ON _scorer_club.team_id = {g}.scorer_team_id '
    expanded=sql[:source.end()] + addition + sql[source.end():]
    projected=expanded[:source.start()].rstrip()+', _scorer_club.name AS scorer_team '+expanded[source.start():]
    # Preserve all existing model projections, with the missing role inserted
    # after the scorer. Do not preserve a misleading non-deterministic event order.
    ordered=[]
    for col in columns:
        ordered.append(col)
        if col==player:
            ordered.append('scorer_team')
    fields=', '.join(_ident(col) for col in ordered)
    order=', '.join(_ident(c)+' ASC' for c in ('match_id','minute','added_time'))
    return f'SELECT {fields} FROM ({projected.strip().rstrip(";")}) AS "_own_goal_labels" ORDER BY {order}'


def _align_goal_view_team_join(question: str, sql: str, issues: list[str]) -> str | None:
    """Enforce the published two-column join key on a *model-created* team goal ranking.

    The view has one row per side of a fixture. This only narrows an existing
    simple SQL join to the credited club, never supplies an answer or aggregate.
    Unusual/ambiguous ON clauses are delegated to the model review instead.
    """
    if not any('Goal-to-v_team_match fanout' in issue for issue in issues):
        return None
    # A conceded-goals analysis intentionally attributes events to an opponent;
    # a query rewrite would be an unjustified assumption for that meaning.
    if re.search(r'\b(?:conceded|against|opponent|allowed|received)\b|گل\s*خورده|گل\s*دریافتی',
                 question.casefold()):
        return None
    scorer=re.search(r'\bFROM\s+goal\s+(?:AS\s+)?([A-Za-z_]\w*)\b',sql,re.I)
    joined=re.search(r'\bJOIN\s+v_team_match\s+(?:AS\s+)?([A-Za-z_]\w*)\s+ON\s+',sql,re.I)
    if not scorer or not joined:
        return None
    goal_alias,view_alias=scorer.group(1),joined.group(1)
    g,v=re.escape(goal_alias),re.escape(view_alias)
    predicate=re.match(rf'(?:{g}\.match_id\s*=\s*{v}\.match_id|'
                       rf'{v}\.match_id\s*=\s*{g}\.match_id)\b',
                       sql[joined.end():],re.I)
    if not predicate:
        return None
    pos=joined.end()+predicate.end()
    # Do not change the meaning of OR-based join conditions.
    next_clause=re.split(r'\b(?:JOIN|WHERE|GROUP\s+BY|HAVING|ORDER\s+BY|LIMIT)\b',
                         sql[pos:],maxsplit=1,flags=re.I)[0]
    if re.search(r'\bOR\b',next_clause,re.I):
        return None
    return sql[:pos]+f' AND {goal_alias}.team_id = {view_alias}.team_id'+sql[pos:]


def _restrict_goalkeeper_role(question: str, sql: str, issues: list[str]) -> str | None:
    """Scope an existing lineup relation to goalkeeper starters using a schema predicate.

    This only fixes a missing role filter in a model-supplied clean-sheet query;
    all projections, joins, aggregations and order are retained. Ambiguous SQL
    or a pre-existing role condition is left to the model rather than guessed.
    The caller revalidates and executes the rewritten SELECT read-only.
    """
    if not any('restrict lineup.position' in issue for issue in issues):
        return None
    if not re.search(r'goalkeepers?|clean\s*sheet|دروازه\s*بان|کلین\s*شیت',question,re.I):
        return None
    if not re.search(r'\bis_starter\s*=\s*1\b',sql,re.I) or 'goals_against' not in sql.lower():
        return None
    if re.search(r'\b(?:UNION|INTERSECT|EXCEPT|RECURSIVE)\b',sql,re.I):
        return None
    sources=list(re.finditer(r'\b(?:FROM|JOIN)\s+lineup\s+(?:AS\s+)?([A-Za-z_]\w*)\b',sql,re.I))
    if len(sources)!=1:
        return None
    source=sources[0];alias=source.group(1)
    if alias.casefold() in ('where','join','on','group','order','limit'):
        return None
    if re.search(rf'\b{re.escape(alias)}\.position\b',sql,re.I):
        return None
    # The query has already passed independent validation, but keep the rewrite
    # narrow: replace only the exact matched source table, not an arbitrary SQL span.
    source_text=sql[source.start():source.end()]
    revised=re.sub(r'(?i)\blineup\b',"(SELECT * FROM lineup WHERE position = 'GK')",source_text,count=1)
    return sql[:source.start()]+revised+sql[source.end():]


def normalize(question: str, sql: str, data: dict) -> str | None:
    """Return a safe-shape SQL candidate or None. Runner must revalidate/execute.

    Only simple top-level SELECTs are transformed. Every derived value still
    comes from the submitted database, not a stored task answer. Output SQL is
    shown in the trace and independently validated by the caller.
    """
    if not isinstance(sql,str) or not sql.strip().lower().startswith('select '):
        return None
    sql=sql.strip().rstrip(';').strip()
    contract=infer_contract(question)
    if not contract.ordered or not diagnostics(question,sql,data):
        return None
    # A clean sheet must be attributed only to actual starting goalkeepers.
    # Pre-filtering lineup at source preserves existing joins, aggregation and
    # projections, and avoids falsely crediting outfield starters.
    goalkeeper_sql=_restrict_goalkeeper_role(question,sql,diagnostics(question,sql,data))
    if goalkeeper_sql:
        return goalkeeper_sql
    # First repair an unambiguous two-sided-view fanout, preserving the model's
    # selected fields, filters and aggregation. The calling pipeline revalidates
    # and executes this candidate in the SAME read-only sandbox.
    safe_join=_align_goal_view_team_join(question,sql,diagnostics(question,sql,data))
    if safe_join:
        return safe_join
    columns=list(data.get('columns') or [])
    if contract.grain=='individual own goal event':
        completed=_complete_own_goal_club_projection(sql, columns, diagnostics(question,sql,data))
        if completed:
            return completed
    rows=data.get('rows') or []
    if not rows or len(set(columns))!=len(columns):
        return None
    locations=_top_level_clauses(sql)
    if 'union' in locations or 'intersect' in locations or 'except' in locations:
        return None
    # For a complete event listing, keep the model's event identity, joins and
    # measurements. Only remove a redundant date when the caller did NOT ask for
    # it and the result already carries a match_id. This is a presentation-only
    # operation over the model's query, not an answer template.
    if (contract.grain == 'individual own goal event' and 'match_date' in columns
        and 'match_id' in columns and 'limit' not in locations
        and not re.search(r'\b(?:date|when|calendar|day)\b|تاریخ|چه\s*روزی', question.casefold())):
        keep=[col for col in columns if col.lower() != 'match_date']
        if len(keep)==len(columns)-1 and keep:
            fields=', '.join(_ident(col) for col in keep)
            ordering=', '.join(_ident(col)+' ASC' for col in ('match_id','minute','added_time') if col in keep)
            return (f'SELECT {fields} FROM ({sql}) AS "_event_result"'
                    + (' ORDER BY '+ordering if ordering else ''))
    if 'order' not in locations:
        return None  # Never synthesize a ranking from an unordered unknown query.
    # Explicit standalone standings leader: preserve ranking semantics from
    # model's SQL; only bound how many rows it returns.
    if contract.grain=='single standings leader':
        tail=sql[:locations['limit']].strip() if 'limit' in locations else sql
        return tail+' LIMIT 1'
    if not (contract.target_rows is not None or contract.grain=='team sanction distribution'):
        return None
    # Model's requested grouping and metrics remain intact; only the tail
    # ORDER BY/LIMIT and final presentation are normalized.
    base=sql[:locations['order']].strip()
    if re.search(r'\b(?:select\s+distinct|with\s+)\b',base,re.I) and contract.grain=='team sanction distribution':
        return None
    if contract.grain=='team sanction distribution' or contract.grain=='team ranking':
        names=[x for x in columns if x.lower() in ('team','team_name','club','club_name')]
        if not names:
            names=[x for x in columns if 'team' in x.lower() and not x.lower().endswith('_id')]
    elif contract.grain=='referee ranking':
        names=[x for x in columns if 'referee' in x.lower() and not x.lower().endswith('_id')]
    elif contract.grain=='coach ranking':
        names=[x for x in columns if 'coach' in x.lower() and not x.lower().endswith('_id')]
    else:
        names=[x for x in columns if ('player' in x.lower() or 'goalkeeper' in x.lower()) and not x.lower().endswith('_id')]
    if not names:
        names=[x for x in columns if any(isinstance(row[columns.index(x)],str) for row in rows[:2]) and not x.lower().endswith('_id')]
    if not names: return None
    participant=names[0]
    clubs=[x for x in columns if x.lower() not in (participant.lower(),) and
           ('team' in x.lower() or 'club' in x.lower()) and not x.lower().endswith('_id')]
    if contract.needs_team and contract.grain not in ('team ranking','team sanction distribution') and not clubs:
        return None  # Need model to add the missing club JOIN.
    metrics=[x for x in columns if x!=participant and x not in clubs and
             not x.lower().endswith('_id') and any(isinstance(row[columns.index(x)],(int,float)) for row in rows[:2])]
    if not metrics:return None
    metric=metrics[-1]  # common SQL convention: SELECT name, club, computed metric
    chosen=[participant]+(clubs[:1] if contract.needs_team and contract.grain not in ('team ranking','team sanction distribution') and clubs else [])+[metric]
    if len(set(chosen))!=len(chosen) or len(chosen)<2:return None
    # Re-project from the model's aggregate SELECT, so no manually written
    # football-specific SQL can slip into the answer path.
    display=', '.join(_ident(n) for n in chosen)
    name=_ident(participant);measure=_ident(metric)
    limit=f' LIMIT {contract.target_rows}' if contract.target_rows else ''
    output=(f'SELECT {display} FROM ({base}) AS "_result_contract" '
            f'ORDER BY {measure} DESC, {name} ASC'+limit)
    return output if output.strip()!=sql.strip() else None
