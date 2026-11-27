"""Bounded schema metadata for a second opinion on premature refusals.

No benchmark questions, expected rows or reference SQL are consulted. This
module only reveals table/column metadata and aggregate counts from the
immutable read-only football database.
"""
from __future__ import annotations
import re
from .db import ro_connection

VOCABULARY = {
    'مربی': ('coach',), 'سرمربی': ('coach',),
    'آرایش': ('formation',), 'سیستم بازی': ('formation',),
    'دروازه بان': ('lineup',), 'دروازه‌بان': ('lineup',),
    'کلین شیت': ('lineup',), 'گل': ('goal',),
    'داور': ('referee',), 'کارت': ('card',), 'پنالتی': ('penalty',),
    'ورزشگاه': ('stadium',), 'تعویض': ('substitution',),
    'بازیکن': ('player',), 'بازی': ('match',), 'مسابقه': ('match',),
    'جدول': ('standing',), 'امتیاز': ('point',),
}


def _concepts(question: str) -> set[str]:
    q = question.casefold()
    tokens = {x for x in re.findall(r'[a-z][a-z_]+', q) if len(x) >= 4}
    def singular(t):
        if t.endswith(('ches','shes')): return t[:-2]
        if t.endswith('ies'): return t[:-3] + 'y'
        return t[:-1] if t.endswith('s') else t
    bases = {singular(t) for t in tokens}
    english_aliases = {'manager': 'coach', 'managing': 'coach',
        'headcoach': 'coach', 'tactic': 'formation', 'lineup': 'formation',
        'keeper': 'lineup', 'shutout': 'lineup', 'booking': 'card'}
    bases.update(english_aliases[t] for t in list(bases) if t in english_aliases)
    for phrase, aliases in VOCABULARY.items():
        if phrase in q:
            bases.update(aliases)
    # Ignore broad match/team terms when a more discriminating metric exists.
    broad = {'team','match','game','player','season','time','league','club',
             'which','many','most','different','change','changed','over'}
    if bases - broad:
        bases -= {'team','match','game','player','season','time','league','club'}
    return bases


def _ident(name: str) -> str:
    if not re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]*', name):
        raise ValueError('Unsafe schema identifier')
    return '"' + name + '"'


def explain_available_data(question: str, *, max_relations: int = 4) -> dict:
    concepts = _concepts(question)
    if not concepts:
        return {'source': 'readonly_schema', 'relations': []}
    con = ro_connection()
    try:
        candidates=[]
        for (name,) in con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"):
            try:
                table=_ident(name)
            except ValueError:
                continue
            columns=[r[1] for r in con.execute(f'PRAGMA table_info({table})')]
            matching=[col for col in columns if any(x in col.casefold() for x in concepts)]
            relevance=sum(8 for x in concepts if x in name.casefold())+len(matching)
            if relevance:
                candidates.append((relevance,name,columns,matching))
        candidates.sort(key=lambda t:(-t[0],t[1]))
        output=[]
        for _, name, columns, matching in candidates[:max(1,min(max_relations,6))]:
            table=_ident(name)
            total=con.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]
            stats=[]
            for col in matching[:4]:
                field=_ident(col)
                n,d=con.execute(f'SELECT COUNT({field}), COUNT(DISTINCT {field}) FROM {table}').fetchone()
                stats.append({'column':col,'non_null':n,'distinct':d})
            output.append({'relation':name,'columns':columns[:24],
                           'observations':total,'field_statistics':stats})
        return {'source':'readonly_schema','relations':output,
                'note':'Counts indicate available data, not a precomputed answer.'}
    finally:
        con.close()
