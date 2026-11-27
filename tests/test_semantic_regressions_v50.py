"""Independent semantic invariants unrelated to the 17-question grader."""
from __future__ import annotations

from collections import Counter
import json
import sqlite3
import unittest
from app.db import execute_readonly
from app.schema_graph import focused_relations
from app.schema_evidence import explain_available_data
from app.normalizer import normalize, dedupe_entity_listing, preserve_left_join_zero_counts
from app.contract import diagnostics


class FocusedSchemaTests(unittest.TestCase):
    def test_staff_change_has_temporal_fk_path(self):
        graph=focused_relations('Compare how often registered head coaches change across a season')
        nodes={r['relation'] for r in graph['relations']}
        self.assertTrue({'coach','team','match_coach','match'} <= nodes)
        self.assertNotIn('goal',nodes)
        self.assertNotIn('card',nodes)

    def test_tactics_graph_has_formation_fields_not_event_fanout(self):
        graph=focused_relations('Which manager used the most different starting formations?')
        nodes={r['relation'] for r in graph['relations']}
        self.assertTrue({'coach','match_coach','match'} <= nodes)
        self.assertFalse({'goal','card','penalty'} & nodes)
        match=next(r for r in graph['relations'] if r['relation']=='match')
        self.assertIn('home_formation',match['columns'])
        self.assertIn('away_formation',match['columns'])

    def test_stadium_question_does_not_drag_in_cards_goals(self):
        graph=focused_relations('نام ورزشگاه‌های ثبت‌شده و تعداد بازی‌ها در هر ورزشگاه را بده.')
        self.assertEqual({'stadium','match'}, {r['relation'] for r in graph['relations']})

    def test_minutes_view_link_to_player_pk_is_explicitly_inferred(self):
        graph=focused_relations('Which player has played the most minutes?')
        self.assertIn({'from':'v_player_minutes.player_id','to':'player.player_id',
                       'confidence':'same_name_to_declared_primary_key'},
                      graph['inferred_view_links'])
        self.assertFalse(any(x.get('from','').startswith('v_player_minutes') for x in graph['foreign_keys']))

    def test_keeper_graph_contains_all_needed_relations(self):
        graph=focused_relations('Which goalkeepers have the most clean sheets?')
        self.assertTrue({'lineup','player','team','v_team_match'} <= {r['relation'] for r in graph['relations']})

    def test_referee_cards_bounded_join_path(self):
        graph=focused_relations('Which referee has shown most yellow cards?')
        self.assertEqual({'card','match','referee'}, {r['relation'] for r in graph['relations']})

    def test_aggregate_relation_proves_multiple_observed_staff(self):
        evidence=explain_available_data('Which teams changed head coach during the season?')
        assoc=next(r for r in evidence['relations'] if r['relation']=='match_coach')
        mult=[x for x in assoc['observed_relationship_cardinality']
              if x['group_field']=='team_id' and x['observed_field']=='coach_id']
        self.assertTrue(mult)
        self.assertGreater(mult[0]['groups_with_multiple_values'],0)
        # Only metadata/statistics; never ship the private record rows or gold SQL.
        text=json.dumps(evidence,ensure_ascii=False)
        self.assertNotIn('SELECT DISTINCT c.name_fa',text)
        self.assertNotIn('expected_rows',text)


class QueryGrainTests(unittest.TestCase):
    SQL=('SELECT c.name_fa AS coach_name, t.name_fa AS team_name '
         'FROM match_coach mc '
         'JOIN coach c ON c.coach_id=mc.coach_id '
         'JOIN team t ON t.team_id=mc.team_id LIMIT 100')
    QUESTION='چه مربی‌هایی در مسابقات ثبت شده‌اند و نام تیمشان چیست؟'

    def test_repeated_label_pairs_are_a_real_grain_mismatch(self):
        observed=execute_readonly(self.SQL)
        self.assertEqual(observed['row_count'],100)
        self.assertTrue(any('identical label rows repeat' in x for x in diagnostics(
            self.QUESTION,self.SQL,observed)))
        candidate=normalize(self.QUESTION,self.SQL,observed)
        self.assertIn('SELECT DISTINCT',candidate)
        result=execute_readonly(candidate)
        # Value-level proof obtained directly from the production DB, without
        # copying an evaluator expected result into either module.
        independent=execute_readonly(
            'SELECT DISTINCT c.name_fa, t.name_fa FROM match_coach mc '
            'JOIN coach c ON c.coach_id=mc.coach_id '
            'JOIN team t ON t.team_id=mc.team_id')
        self.assertEqual(Counter(map(tuple,result['rows'])),Counter(map(tuple,independent['rows'])))
        self.assertFalse(result['truncated'])
        self.assertEqual(diagnostics(self.QUESTION,candidate,result),[])

    def test_per_match_reporting_must_preserve_multiplicity(self):
        observed=execute_readonly(self.SQL)
        self.assertIsNone(dedupe_entity_listing(
            'برای هر مسابقه نام مربی و تیمش را بگو.',self.SQL,observed))

    def test_event_id_projection_not_deduplicated(self):
        sql=('SELECT mc.match_id, c.name_fa AS coach_name, t.name_fa AS team_name '
             'FROM match_coach mc JOIN coach c ON c.coach_id=mc.coach_id '
             'JOIN team t ON t.team_id=mc.team_id LIMIT 100')
        observed=execute_readonly(sql)
        self.assertIsNone(dedupe_entity_listing(self.QUESTION,sql,observed))

    def test_aggregate_sql_is_not_distinct_rewritten(self):
        sql='SELECT t.name AS team_name, COUNT(*) AS games FROM match_coach mc JOIN team t ON t.team_id=mc.team_id GROUP BY t.team_id'
        self.assertIsNone(dedupe_entity_listing(self.QUESTION,sql,execute_readonly(sql)))


class NullableJoinTests(unittest.TestCase):
    QUESTION='نام همه ورزشگاه‌های ثبت‌شده و تعداد بازی‌ها در هر ورزشگاه را بده.'
    SQL=('SELECT s.name_fa AS stadium_name, COUNT(m.match_id) AS match_count '
         'FROM stadium s LEFT JOIN "match" m ON s.stadium_id=m.stadium_id '
         "WHERE m.status = 'finished' GROUP BY s.stadium_id")

    def test_move_nullable_filter_and_validate(self):
        original=execute_readonly(self.SQL)
        self.assertTrue(any('WHERE predicate' in x for x in diagnostics(self.QUESTION,self.SQL,original)))
        candidate=normalize(self.QUESTION,self.SQL,original)
        self.assertIn(') AND m.status',candidate)
        self.assertNotIn(' WHERE m.status',candidate)
        observed=execute_readonly(candidate)
        self.assertEqual(diagnostics(self.QUESTION,candidate,observed),[])

    def test_zero_event_stadium_is_preserved_in_a_synthetic_database(self):
        db=sqlite3.connect(':memory:')
        db.executescript('''CREATE TABLE stadium(stadium_id INTEGER PRIMARY KEY,name_fa TEXT);
            CREATE TABLE "match"(match_id INTEGER PRIMARY KEY,stadium_id INTEGER,status TEXT);
            INSERT INTO stadium VALUES (1,'A'),(2,'B');
            INSERT INTO "match" VALUES (1,1,'finished');''')
        before=[*db.execute(self.SQL)]
        candidate=preserve_left_join_zero_counts(self.QUESTION,self.SQL,{'columns':[],'rows':[]})
        after=[*db.execute(candidate)]
        self.assertEqual(before,[('A',1)])
        self.assertEqual(after,[('A',1),('B',0)])
        db.close()

    def test_does_not_rewrite_nonall_or_count_star(self):
        observed=execute_readonly(self.SQL)
        self.assertIsNone(preserve_left_join_zero_counts('Stadiums with finished matches',self.SQL,observed))
        self.assertIsNone(preserve_left_join_zero_counts(
            self.QUESTION,self.SQL.replace('COUNT(m.match_id)','COUNT(*)'),observed))

    def test_does_not_rewrite_multifilter(self):
        observed=execute_readonly(self.SQL)
        self.assertIsNone(preserve_left_join_zero_counts(
            self.QUESTION,self.SQL.replace("m.status = 'finished'", "m.status = 'finished' AND s.name_fa IS NOT NULL"),observed))


if __name__=='__main__':unittest.main()
