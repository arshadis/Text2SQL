"""Schema-driven join/cardinality tests; no evaluation gold or question->SQL table."""
import inspect
import unittest
from unittest.mock import patch
from app import contract, normalizer
from app.db import execute_readonly, RejectedSQL
from app.pipeline import answer

OWN_EVENTS = 'List all own goals: match, scorer, and which team benefited.'
TEAM_RANK = 'Which team scores most often after the 75th minute?'
# Deliberately imperfect model SQL, not reference or gold SQL.
MISSING_SCORER_CLUB = '''SELECT g.match_id, p.name_fa AS scorer_name,
    t.name AS benefited_team, g.minute, g.added_time
    FROM goal g JOIN player p ON p.player_id=g.player_id
    JOIN team t ON t.team_id=g.team_id
    WHERE g.is_own_goal=1 ORDER BY g.match_id'''
FANOUT = '''SELECT t.name AS team, COUNT(g.goal_id) AS late_goals
    FROM goal g JOIN v_team_match tm ON g.match_id=tm.match_id
    JOIN team t ON t.team_id=tm.team_id
    WHERE g.minute>75 GROUP BY tm.team_id
    ORDER BY late_goals DESC,t.name ASC LIMIT 3'''

class CrossTeamSemantics(unittest.TestCase):
    def test_own_goal_requires_both_distinct_club_roles(self):
        observations=execute_readonly(MISSING_SCORER_CLUB)
        self.assertTrue(any('Missing readable scorer club' in x for x in contract.diagnostics(OWN_EVENTS,MISSING_SCORER_CLUB,observations)))

    def test_missing_scorer_club_can_be_derived_from_existing_event_query(self):
        original=execute_readonly(MISSING_SCORER_CLUB)
        corrected=normalizer.normalize(OWN_EVENTS,MISSING_SCORER_CLUB,original)
        self.assertIsNotNone(corrected)
        result=execute_readonly(corrected)
        self.assertEqual(result['row_count'],original['row_count'])
        self.assertEqual(result['columns'],['match_id','scorer_name','scorer_team','benefited_team','minute','added_time'])
        self.assertFalse(contract.diagnostics(OWN_EVENTS,corrected,result))
        self.assertTrue(any(row[2]!=row[3] for row in result['rows']))
        # Verify both role labels independently via existing declared FK relations.
        with_connection=execute_readonly('''SELECT g.match_id, ts.name, tb.name
          FROM goal g JOIN team ts ON ts.team_id=g.scorer_team_id
          JOIN team tb ON tb.team_id=g.team_id WHERE g.is_own_goal=1 ORDER BY g.match_id''')
        self.assertEqual([[x[0],x[2],x[3]] for x in result['rows']],with_connection['rows'])

    def test_own_goal_already_correct_is_not_rewritten(self):
        completed=normalizer.normalize(OWN_EVENTS,MISSING_SCORER_CLUB,execute_readonly(MISSING_SCORER_CLUB))
        self.assertEqual(normalizer.normalize(OWN_EVENTS,completed,execute_readonly(completed)),None)

    def test_own_goal_compensation_does_not_handle_destructive_sql(self):
        changed=normalizer.normalize(OWN_EVENTS,MISSING_SCORER_CLUB,execute_readonly(MISSING_SCORER_CLUB))
        with self.assertRaises(RejectedSQL):
            execute_readonly(changed+'; DELETE FROM goal')

    def test_cardinality_error_detected_even_with_valid_sql_and_three_rows(self):
        result=execute_readonly(FANOUT)
        self.assertEqual(result['validation'],'passed')
        self.assertEqual(result['row_count'],3)
        self.assertTrue(any('fanout' in x.lower() for x in contract.diagnostics(TEAM_RANK,FANOUT,result)))

    def test_readonly_join_fix_yields_independently_counted_credited_goals(self):
        result=execute_readonly(FANOUT)
        edited=normalizer.normalize(TEAM_RANK,FANOUT,result)
        self.assertIn('g.team_id = tm.team_id',edited)
        corrected=execute_readonly(edited)
        self.assertFalse(contract.diagnostics(TEAM_RANK,edited,corrected))
        independent=execute_readonly('''SELECT t.name AS club, COUNT(*) AS metric
         FROM goal g JOIN team t ON t.team_id=g.team_id
         WHERE g.minute>75 GROUP BY g.team_id ORDER BY metric DESC, club ASC LIMIT 3''')
        self.assertEqual(corrected['rows'],independent['rows'])
        self.assertNotEqual(result['rows'],independent['rows'])

    def test_safe_two_key_join_is_accepted_without_changes(self):
        prepared=normalizer.normalize(TEAM_RANK,FANOUT,execute_readonly(FANOUT))
        self.assertEqual(normalizer.normalize(TEAM_RANK,prepared,execute_readonly(prepared)),None)

    def test_credited_goals_must_not_be_assigned_to_scorers_team(self):
        sql='''SELECT t.name AS team, COUNT(*) AS metric
           FROM goal g JOIN team t ON t.team_id=g.scorer_team_id
           GROUP BY g.scorer_team_id ORDER BY metric DESC, team ASC LIMIT 3'''
        self.assertTrue(any('credited club' in x for x in contract.diagnostics(TEAM_RANK,sql,execute_readonly(sql))))

    def test_do_not_rewrite_opposition_semantics_as_credited_goals(self):
        q='Which team conceded the most goals?'
        sql=FANOUT
        self.assertIsNone(normalizer._align_goal_view_team_join(q,sql,contract.diagnostics(q,sql,execute_readonly(sql))))

    def test_pipeline_normalizes_canonical_errors_and_keeps_ro_validation(self):
        import app.pipeline as pipeline
        def planner(sql):
            def fake(*args,**kwargs):
                return ({'action':'answer_from_query','intent':'test','sql':sql}, {'status':'ok','latency_ms':0})
            return fake
        for question,sql in ((TEAM_RANK,FANOUT),(OWN_EVENTS,MISSING_SCORER_CLUB)):
            fake=planner(sql)
            with self.subTest(question=question):
                with patch.object(pipeline,'plan',fake), patch.dict('os.environ',{'GAPGPT_REVIEW_ENABLED':'0','RESULT_NORMALIZATION_ENABLED':'1'}):
                    result=answer(question,planner=fake)
                self.assertEqual(result['validation'],'passed')
                self.assertEqual(result['dry_run'],'ok')
                self.assertEqual(result['result_normalization'],'applied')
                self.assertEqual(result['semantic_warnings'],[])
                self.assertTrue(result['database_executed'])

    def test_no_eval_rows_in_production_contract_or_normalizer(self):
        s=inspect.getsource(contract)+inspect.getsource(normalizer)
        for banned in ('eval_questions.json','gold_sql','expected_rows'):
            self.assertNotIn(banned,s)

if __name__=='__main__': unittest.main()
