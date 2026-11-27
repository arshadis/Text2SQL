"""Schema-derived relation map for question-conditioned planning.

This is generated from SQLite's own catalog, *not* reference evaluation SQL,
question templates, golden rows, or prewritten query recipes. The output is
bounded metadata (fields, foreign keys, views). No database records are sent.
"""
from __future__ import annotations

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


def focused_relations(question: str, *, primary: int = 4, limit: int = 7) -> dict:
    """Return a compact subgraph selected using the user's own domain words.

    Foreign keys are from PRAGMA foreign_key_list, and related relations are
    added because they join to a selected table. This recovers useful routes
    such as coach -> match_coach -> match without assuming an answer SQL.
    """
    concepts={c for c in _concepts(question) if len(c)>=3 and c not in _STOP}
    # Vocabulary expands a user term to a field concept; it does not determine
    # an aggregation, status filter, projection, or expected result length.
    if 'table' in concepts or 'standings' in concepts:
        concepts.add('standings')
    if 'home' in concepts or 'away' in concepts:
        concepts.add('venue')
    if 'point' in concepts or 'points' in concepts:
        concepts.update(('points','standings'))
    if 'goalkeeper' in concepts or 'keeper' in concepts:
        concepts.add('lineup')
    if not concepts:
        return {'source':'sqlite_catalog', 'relations':[], 'foreign_keys':[]}
    con=ro_connection()
    try:
        raw=[]
        for name,kind in con.execute("SELECT name,type FROM sqlite_master WHERE type IN ('table','view') AND name NOT LIKE 'sqlite_%'"):
            if not re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]*',name):continue
            cols=[x[1] for x in con.execute(f'PRAGMA table_info({_ident(name)})')]
            matching=[c for c in cols if any(t in c.casefold().split('_') or t in c.casefold() for t in concepts)]
            name_words=set(name.casefold().split('_'))
            exact_field_terms={t for t in concepts if any(t in c.casefold().split('_') for c in cols)}
            name_terms={t for t in concepts if t in name_words}
            score=12*len(name_terms)+5*len(exact_field_terms)
            if kind=='view':
                score=max(0,score-2)
                # A recorded venue role is unusually informative for home/away
                # questions. This is a catalog field match, not a query plan.
                if 'venue' in exact_field_terms:score+=8
            if score >= (6 if kind=='view' else 5):
                raw.append((score,name,kind,cols,matching))
        raw.sort(key=lambda x:(-x[0],x[1]))
        seeds=[x[1] for x in raw[:max(1,primary)]]
        # Always include direct foreign-key neighbors when there's room;
        # this is essential for cross-table historical facts, but never
        # dictates how any returned query must be written.
        fk_all=[]
        for name,kind in con.execute("SELECT name,type FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"):
            if not re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]*',name):continue
            for row in con.execute(f'PRAGMA foreign_key_list({_ident(name)})'):
                to,source,target=row[2],row[3],row[4]
                fk_all.append((name,source,to,target))
        chosen=set(seeds)
        candidates=[]
        for a,af,b,bf in fk_all:
            if a in chosen and b not in chosen:candidates.append((a,b))
            if b in chosen and a not in chosen:candidates.append((b,a))
        # A bridge table may connect two selected entities, even if its own
        # name does not share the exact text of the question.
        scores={name:score for score,name,*_ in raw}
        candidates.sort(key=lambda x:(-scores.get(x[1],0),x[1]))
        for _,name in candidates:
            if len(chosen)>=limit:break
            chosen.add(name)
        # Add high relevance views if they were not covered by the FK graph.
        for _,name,kind,*_ in raw:
            if len(chosen)>=limit:break
            if name not in chosen:chosen.add(name)
        focus=[]
        for name in sorted(chosen, key=lambda x:(-scores.get(x,0),x)):
            kind=next((x[2] for x in raw if x[1]==name),None)
            if kind is None:
                kind=con.execute('SELECT type FROM sqlite_master WHERE name=?',(name,)).fetchone()[0]
            columns=[x[1] for x in con.execute(f'PRAGMA table_info({_ident(name)})')]
            focus.append({'relation':name,'kind':kind,'columns':columns[:26]})
        edges=[{'from':a+'.'+af,'to':b+'.'+bf} for a,af,b,bf in fk_all
               if a in chosen and b in chosen]
        return {'source':'sqlite_catalog','relations':focus,'foreign_keys':edges[:32],
                'note':'Catalog facts only. Foreign-key edges describe relationships, not answer SQL.'}
    finally:
        con.close()
