"""Independent catalog and tie-preservation tests, never using eval gold rows."""
import json
import os
from unittest.mock import patch
import unittest
from pathlib import Path
from app.schema_graph import focused_relations
from app.db import execute_readonly
from app.normalizer import expand_verified_ties


class CatalogGraphTests(unittest.TestCase):
    def test_staff_temporal_relationship_is_discoverable(self):
        graph=focused_relations('Compare how often registered head coaches change across a season')
        names={r['relation'] for r in graph['relations']}
        self.assertTrue({'coach','match_coach','match','team'} <= names)
        edges={(e['from'],e['to']) for e in graph['foreign_keys']}
        self.assertIn(('match_coach.match_id','match.match_id'),edges)
        self.assertIn(('match_coach.coach_id','coach.coach_id'),edges)

    def test_formation_and_coach_observations_can_be_joined(self):
        graph=focused_relations('Count distinct starting formations per coach across recorded games')
        names={r['relation'] for r in graph['relations']}
        self.assertTrue({'coach','match_coach','match'} <= names)
        match=next(r for r in graph['relations'] if r['relation']=='match')
        self.assertIn('home_formation',match['columns'])
        self.assertIn('away_formation',match['columns'])

    def test_home_points_use_standings_and_venue_views(self):
        graph=focused_relations('Compare points won in home games versus away games')
        names={r['relation'] for r in graph['relations']}
        self.assertIn('v_team_match',names)
        self.assertIn('v_standings',names)

    def test_graph_excludes_actual_personal_record_values(self):
        graph=focused_relations('List the managers in the database')
        payload=json.dumps(graph,ensure_ascii=False)
        self.assertNotIn('سهراب بختیاری زاده',payload)
        self.assertNotIn('محمد ربیعی',payload)
        self.assertEqual(graph['source'],'sqlite_catalog')

    def test_unrecorded_concept_has_no_matching_relations(self):
        graph=focused_relations('How much was the ticket sales revenue?')
        self.assertEqual(graph['relations'],[])


class PlannerPayloadTests(unittest.TestCase):
    def test_planner_receives_only_catalog_evidence_not_reference_sql(self):
        from app.llm import plan
        received=[]
        def transport(request):
            doc=json.loads(request.data)
            received.append(doc)
            return ({'choices':[{'message':{'content':json.dumps({
                'action':'ask_clarifying_question','intent':'unknown',
                'sql':None,'clarification':'Which statistic?','reason':'not supplied'
            })}}]},200)
        with patch.dict(os.environ, {'GAPGPT_API_KEY':'unit-test-secret'}, clear=False):
            result,_=plan('Show the managers of registered clubs',transport=transport)
        self.assertEqual(result['action'],'ask_clarifying_question')
        payload=json.loads(received[0]['messages'][2]['content'])
        graph=payload['focused_schema_graph']
        self.assertIn('match_coach',{r['relation'] for r in graph['relations']})
        self.assertTrue(graph['foreign_keys'])
        self.assertNotIn('eval_questions.json',received[0]['messages'][2]['content'])
        self.assertNotIn('expected_rows',received[0]['messages'][2]['content'])


class VerifiedTieTests(unittest.TestCase):
    def test_preserves_all_observed_tied_entities(self):
        sql=('SELECT t.name AS team, '
             '(SELECT COUNT(*) FROM "match" m WHERE m.home_team_id=t.team_id '
             'OR m.away_team_id=t.team_id) AS fixtures '
             'FROM team t ORDER BY fixtures DESC, team ASC LIMIT 1')
        original=execute_readonly(sql)
        self.assertEqual(original['row_count'],1)
        found=expand_verified_ties('Which clubs have the most scheduled fixtures?',sql,original,execute_readonly)
        self.assertIsNotNone(found)
        revised,rows=found
        self.assertGreater(rows['row_count'],1)
        self.assertEqual({r[1] for r in rows['rows']},{34})
        self.assertRegex(revised,r'LIMIT 18$')

    def test_explicit_one_does_not_expand(self):
        sql=('SELECT t.name AS team, '
             '(SELECT COUNT(*) FROM "match" m WHERE m.home_team_id=t.team_id '
             'OR m.away_team_id=t.team_id) AS fixtures '
             'FROM team t ORDER BY fixtures DESC, team ASC LIMIT 1')
        original=execute_readonly(sql)
        self.assertIsNone(expand_verified_ties('Top 1 club by fixtures',sql,original,execute_readonly))

    def test_unrelated_sort_metric_not_expanded(self):
        sql='SELECT name AS team, team_id AS identity FROM team ORDER BY team ASC LIMIT 1'
        original=execute_readonly(sql)
        self.assertIsNone(expand_verified_ties('Which team has most matches?',sql,original,execute_readonly))


if __name__=='__main__':unittest.main()
