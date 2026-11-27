"""Question-focused SQL catalog context, compiled from the actual SQLite DB.

No gold SQL, benchmark questions, or previously recorded answers are consulted.
The full semantic dictionary is still available in fallback mode for debugging.
"""
from __future__ import annotations

from .db import ro_connection
from .schema_graph import focused_relations
from .query_plan import derive_query_plan


def select_relevant_relations(question: str, *, max_relations: int = 9) -> list[str]:
    """Union semantic-dictionary vocabulary with FK-graph hits.

    A relation is included for its domain meaning, never because a benchmark
    expects a specific SQL clause or row count. The caller still verifies it
    exists in the actual catalog.
    """
    import re
    plan=derive_query_plan(question)
    q=question.casefold()
    selected=set(r["relation"] for r in focused_relations(question, limit=max_relations)["relations"])
    entities=set(plan.requested_entities); measures=set(plan.requested_measures)
    if "team" in entities: selected.add("team")
    if "player" in entities: selected.add("player")
    if "match" in entities: selected.add("match")
    if "coach" in entities: selected.update(("coach","match_coach","match","team"))
    if "referee" in entities: selected.update(("referee","match"))
    if "stadium" in entities: selected.update(("stadium","match"))
    if "points" in measures: selected.update(("v_standings", "team"))
    if "home side only; do not substitute overall-league totals" in plan.filters or "away side only; do not substitute overall-league totals" in plan.filters:
        selected.update(("v_team_match","match","team"))
    if "match result" in measures: selected.update(("match","v_match","team"))
    if "match count" in measures: selected.add("match")
    if "goal count" in measures or "own-goal event details" in measures: selected.add("goal")
    if "goal count" in measures and "player" in entities:
        selected.update(("goal","player","team"))
    if "goal count" in measures and "team" in entities:
        selected.update(("goal","team"))
    if "clean sheets" in measures: selected.update(("lineup","player","team","v_team_match","match"))
    if "playing minutes" in measures: selected.update(("v_player_minutes","player","team"))
    if "distinct formations" in measures or "formation detail" in measures: selected.update(("match","match_coach","coach","team"))
    if "yellow cards" in measures or "red cards" in measures: selected.add("card")
    if "recorded penalties" in measures: selected.add("penalty")
    if "VAR decisions" in measures: selected.add("var_decision")
    if "recorded substitutions" in measures: selected.add("substitution")
    if re.search(r"\b(?:standings|league\s+table|table\s+leader)\b|جدول\s+لیگ|صدر\s+جدول",q):
        selected.update(("v_standings","team"))
    if re.search(r"\b(?:scoring|scored|scores|scorers?|goals?)\b|گلزن|گل\s+زد",q):
        selected.add("goal")
    if re.search(r"\b(?:fixtures?|games?|derby|scores?)\b|بازی|دیدار|دربی|نتیجه",q):
        selected.add("match")
    if re.search(r"\b(?:minutes\s+played|playing\s+time)\b|دقایق\s+بازی",q):
        selected.update(("v_player_minutes","player","team"))
    if re.search(r"\b(?:goalkeepers?|keepers?|clean\s+sheets?)\b|کلین|دروازه",q):
        selected.update(("lineup","player","team","v_team_match"))
    if re.search(r"\b(?:own[ -]?goals?)\b|گل[\s\u200c]*به[\s\u200c]*خودی",q):
        selected.update(("goal","player","team","match"))
    # Rankings often need one additional lookup for readable labels.
    priority=("match_coach","coach","goal","lineup","v_player_minutes", "v_team_match",
              "v_standings","match","v_match","player","team","referee", "card",
              "penalty","var_decision","substitution","stadium")
    ordered=[name for name in priority if name in selected]
    return ordered[:max_relations]
from .llm_context_basics import BASICS


def compiled_context(question: str, *, max_relations: int = 9) -> str:
    graph=focused_relations(question, limit=max_relations)
    names=select_relevant_relations(question, max_relations=max_relations)
    if not names:
        # A question can refer to an unrecognized concept. The model still
        # needs enough catalog facts to determine availability, without guessing.
        names=['team','player','"match"','v_standings','v_team_match']
    con=ro_connection()
    try:
        parts=[BASICS,'Selected SQLite relation definitions (authoritative database schema):']
        for name in names:
            clean=name.strip('"')
            record=con.execute('SELECT sql FROM sqlite_master WHERE name=? AND type IN ("table","view")',(clean,)).fetchone()
            if record and record[0]: parts.append(record[0].strip()+';')
        parts.append('Declared and inferred links (only metadata, not generated query):')
        selected=set(n.strip('"') for n in names)
        for name in sorted(selected):
            record=con.execute('SELECT type FROM sqlite_master WHERE name=?',(name,)).fetchone()
            if record and record[0]=='table':
                for fk in con.execute(f'PRAGMA foreign_key_list("{name}")'):
                    if fk[2] in selected:
                        parts.append(f'- {name}.{fk[3]} → {fk[2]}.{fk[4]} [declared FK]')
        for name in sorted(selected):
            record=con.execute('SELECT type FROM sqlite_master WHERE name=?',(name,)).fetchone()
            if not record or record[0]!='view':continue
            vcols={r[1] for r in con.execute(f'PRAGMA table_info("{name}")')}
            for table in sorted(selected-{name}):
                t=con.execute('SELECT type FROM sqlite_master WHERE name=?',(table,)).fetchone()
                if not t or t[0]!='table':continue
                for pk in con.execute(f'PRAGMA table_info("{table}")'):
                    if pk[5]>0 and pk[1].endswith('_id') and pk[1] in vcols:
                        parts.append(f'- {name}.{pk[1]} ↔ {table}.{pk[1]} [inferred, verify semantics]')
        parts.append('Typed user-question constraints (the raw question remains authoritative):')
        parts.append(str(derive_query_plan(question).as_prompt()))
        return '\n'.join(parts)
    finally:
        con.close()
