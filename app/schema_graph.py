"""Bounded, minimal schema graph selected from actual SQLite catalog metadata.

The graph is a lookup aid for open-ended SQL planning, NOT an answer template.
A shortest FK route can connect two relevant entities, but unrelated event
neighbors are not copied merely because they touch a selected relation.
"""
from __future__ import annotations

from collections import deque
import re

from .db import ro_connection
from .schema_evidence import _concepts, _ident

_STOP = frozenset('''which what whose where when who whom how much many show list all each every
are was were did does do have has had the a an for from into in of on at to by as is
and with during across most best top highest lowest more fewer compare count number
between recorded register registered season current ever same different change changed
over report team teams player players club clubs games match matches fixture fixtures
at their whose this that
'''.split())


def _shortest_path(first: str, second: str, adjacent: dict[str, set[str]], depth: int=3) -> list[str]:
    if first==second:return [first]
    frontier=deque([[first]])
    visited={first}
    while frontier:
        path=frontier.popleft()
        if len(path)>depth:continue
        for next_name in sorted(adjacent.get(path[-1],())):
            if next_name==second:return path+[second]
            if next_name not in visited:
                frontier.append(path+[next_name]);visited.add(next_name)
    return []


def focused_relations(question: str, *, primary: int=4, limit: int=7) -> dict:
    """Prioritize matching relations and the *shortest paths between them*.

    No row values, reference questions, prebuilt SQL or expected result sizes.
    Views have no declared FKs; familiar *_id fields in views are provided as
    columns, while explicit edges come only from the SQLite foreign key list.
    """
    concepts={c for c in _concepts(question) if len(c)>=3 and c not in _STOP}
    q=question.casefold()
    if 'home' in concepts or 'away' in concepts or 'خانگی' in q or 'میزبان' in q:
        concepts.add('venue')
    if 'point' in concepts or 'points' in concepts or 'امتیاز' in q:
        concepts.update(('points','standings'))
    if 'goalkeeper' in concepts or 'keeper' in concepts or 'دروازه' in q:
        concepts.add('lineup')
    if not concepts:
        return {'source':'sqlite_catalog','relations':[],'foreign_keys':[]}
    con=ro_connection()
    try:
        catalog={}
        for name,kind in con.execute("SELECT name,type FROM sqlite_master WHERE type IN ('table','view') AND name NOT LIKE 'sqlite_%'"):
            if not re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]*',name):continue
            cols=[x[1] for x in con.execute(f'PRAGMA table_info({_ident(name)})')]
            catalog[name]=(kind,cols)
        scored=[]
        for name,(kind,cols) in catalog.items():
            name_words=set(name.casefold().split('_'))
            cols_words=[set(c.casefold().split('_')) for c in cols]
            exact_field_terms={t for t in concepts if any(t in parts for parts in cols_words)}
            name_terms=concepts & name_words
            score=12*len(name_terms)+5*len(exact_field_terms)
            if kind=='view':
                score=max(0,score-2)
                if 'venue' in exact_field_terms: score+=8
            # A formation belongs to a match *side*; formation_line on a
            # lineup is a position, not the team tactical formation string.
            if 'formation' in concepts and any(c.endswith('_formation') for c in cols):
                score+=8
            if score:
                scored.append((score,name))
        scored.sort(key=lambda t:(-t[0],t[1]))
        peak=scored[0][0] if scored else 0
        seeds=[name for score,name in scored if score>=max(6,peak*.38)][:max(1,primary)]
        edges=[]
        adjacent={n:set() for n in catalog}
        for name,(kind,_) in catalog.items():
            if kind!='table':continue
            for row in con.execute(f'PRAGMA foreign_key_list({_ident(name)})'):
                to,source,target=row[2],row[3],row[4]
                if to not in catalog:continue
                edges.append((name,source,to,target))
                adjacent[name].add(to);adjacent[to].add(name)

        chosen=set(seeds)
        # Bridge relevant entities by their shortest declared FK routes.
        for i,a in enumerate(seeds):
            for b in seeds[i+1:]:
                path=_shortest_path(a,b,adjacent)
                if path and len(chosen | set(path))<=limit:
                    chosen.update(path)

        # Entity labels must be reachable; include a lookup table explicitly
        # mentioned by the visitor if it has a PK link to a selected table.
        requested={
            'player':r'\b(?:players?|goalkeepers?|keepers?)\b|بازیکن|گلزن|دروازه[\s\u200c]*بان',
            'team':r'\b(?:teams?|clubs?)\b|تیم|باشگاه',
            'coach':r'\b(?:coaches?|managers?|head[ -]?coaches?)\b|مربی|سرمربی',
            'referee':r'\breferees?\b|داور',
            'stadium':r'\bstadiums?\b|ورزشگاه',
            'match':r'\b(?:matches?|fixtures?|games?)\b|مسابقه|مسابقات|بازی',
        }
        for lookup,pattern in requested.items():
            if (lookup in catalog and lookup not in chosen and len(chosen)<limit
                and re.search(pattern,q,re.I)
                and (any(lookup in adjacent.get(node,()) for node in chosen)
                     or any(lookup+'_id' in catalog[n][1] for n in chosen))):
                chosen.add(lookup)

        # A query about changes over time needs the observation's time/key.
        # ``match_coach`` is just one possible time-varying relation.
        if (re.search(r'\b(?:chang(?:e|ed|es|ing)|histor(?:y|ical)|different\s+coaches?)\b|تغییر|عوض',q,re.I)
            and 'match_coach' in chosen):
            # Include all the direct references of a repeated observation:
            # whose observation, on which occasion, and who/what was linked.
            for relation in sorted(adjacent.get('match_coach',())):
                if len(chosen)>=limit:break
                chosen.add(relation)

        # A goalkeeper's clean-sheet metric requires the conceded-score side;
        # include the relevant schema view rather than only unrelated event tables.
        if (('clean sheet' in q or 'clean sheets' in q or 'کلین' in q)
            and 'lineup' in chosen):
            # Clean sheets are per goalkeeper AND team, tied to the team's
            # goals conceded in its match; role tables are needed even if
            # a user does not spell out the words "team" or "player".
            for relation in ('player','team','v_team_match'):
                if relation in catalog and len(chosen)<limit:
                    chosen.add(relation)

        # Do not expand each seed's entire neighborhood: that previously
        # injected unrelated goals/cards/etc into coach and stadium questions.
        scores=dict((name,score) for score,name in scored)
        focus=[]
        for name in sorted(chosen,key=lambda n:(-scores.get(n,0),n))[:limit]:
            kind,columns=catalog[name]
            focus.append({'relation':name,'kind':kind,'columns':columns[:26]})
        names={r['relation'] for r in focus}
        joins=[{'from':a+'.'+af,'to':b+'.'+bf} for a,af,b,bf in edges
               if a in names and b in names]
        # Views cannot declare foreign keys in SQLite. Their joinable ID columns
        # can still be connected to an existing *declared primary key* when
        # the column names exactly match. Label these as inferred, not FKs.
        suggested=[]
        for view in sorted(names):
            if catalog[view][0]!='view':continue
            for table in sorted(names):
                if catalog[table][0]!='table':continue
                pk_cols=[r[1] for r in con.execute(f'PRAGMA table_info({_ident(table)})')
                         if r[5]>0]
                for key in pk_cols:
                    if (key.endswith('_id') and key in catalog[view][1] and
                        (key!='match_id' or table=='match')):
                        suggested.append({'from':view+'.'+key,'to':table+'.'+key,
                                          'confidence':'same_name_to_declared_primary_key'})
        return {'source':'sqlite_catalog','relations':focus,'foreign_keys':joins[:32],
                'inferred_view_links':suggested[:12],
                'note':'Declared FKs and same-name view-to-PK hints are catalog facts, not answer SQL.'}
    finally:
        con.close()
