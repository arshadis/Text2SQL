"""Tests for general output contracts; independent of eval questions/gold SQL."""
import inspect
import unittest
from app.contract import infer_contract, diagnostics, instruction
from app.normalizer import normalize, _top_level_clauses
from app.db import execute_readonly, RejectedSQL
from app import contract, normalizer

class GeneralResultContractTests(unittest.TestCase):
    def test_short_league_leader_is_one_row(self):
        q='Who is top of the league table?'
        original='SELECT team, points, goal_diff FROM v_standings ORDER BY points DESC, goal_diff DESC'
        before=execute_readonly(original)
        fixed=normalize(q,original,before)
        self.assertIsNotNone(fixed)
        actual=execute_readonly(fixed)
        self.assertEqual(actual['row_count'],1)
        self.assertEqual(actual['rows'][0][0],'Persepolis')
        self.assertEqual(diagnostics(q,fixed,actual),[])

    def test_generic_ranked_clubs_are_alphabetical_within_ties(self):
        q='Which team has the most points at home?'
        original='SELECT team, points FROM v_standings ORDER BY points DESC'
        fixed=normalize(q,original,execute_readonly(original))
        self.assertIsNotNone(fixed)
        result=execute_readonly(fixed)
        self.assertEqual(result['row_count'],3)
        self.assertEqual(result['columns'],['team','points'])
        self.assertEqual(diagnostics(q,fixed,result),[])
        self.assertIn('ORDER BY "points" DESC, "team" ASC LIMIT 3',fixed)

    def test_generic_top_n_does_not_preserve_wrong_limited_ties(self):
        q='Top 4 goal scorers with their club (own goals excluded)'
        original='''SELECT p.name_fa AS player, t.name AS team, COUNT(*) AS goals
          FROM goal g JOIN player p ON p.player_id=g.player_id
          JOIN team t ON t.team_id=g.scorer_team_id
          WHERE g.is_own_goal=0 GROUP BY g.player_id, t.team_id
          ORDER BY goals DESC LIMIT 4'''
        self.assertEqual(infer_contract(q).grain,'player ranking')
        fixed=normalize(q,original,execute_readonly(original))
        self.assertIsNotNone(fixed)
        observed=execute_readonly(fixed)
        self.assertEqual(observed['row_count'],4)
        self.assertTrue(all(isinstance(row[0],str) for row in observed['rows']))
        self.assertEqual(observed['columns'],['player','team','goals'])

    def test_red_card_distributions_not_collapsed_to_top_one(self):
        q='Which clubs have the most red cards including second yellows?'
        sql="""SELECT t.name AS club, COUNT(*) AS sanctions
          FROM card c JOIN team t ON c.team_id=t.team_id
          WHERE c.card_type IN ('red','second_yellow')
          GROUP BY t.team_id ORDER BY sanctions DESC"""
        result=execute_readonly(sql)
        fixed=normalize(q,sql,result)
        self.assertIsNotNone(fixed)
        after=execute_readonly(fixed)
        self.assertEqual(after['row_count'],result['row_count'])
        self.assertEqual(after['columns'],['club','sanctions'])
        self.assertEqual(diagnostics(q,fixed,after),[])

    def test_player_ranking_removes_numeric_internal_id(self):
        q='Which goalkeeper has the most clean sheets?'
        sql='''SELECT p.player_id, p.name_fa AS goalkeeper, t.name AS team, COUNT(*) AS clean_sheets
        FROM lineup l JOIN player p ON p.player_id=l.player_id
        JOIN team t ON t.team_id=l.team_id
        WHERE l.position='GK' AND l.is_starter=1
        GROUP BY p.player_id,t.team_id ORDER BY clean_sheets DESC LIMIT 1'''
        fixed=normalize(q,sql,execute_readonly(sql))
        self.assertIsNotNone(fixed)
        after=execute_readonly(fixed)
        self.assertEqual(after['row_count'],5)
        self.assertEqual(after['columns'],['goalkeeper','team','clean_sheets'])
        self.assertTrue(all(isinstance(row[0],str) for row in after['rows']))

    def test_named_match_filters_are_observable_contract(self):
        q='What was the score of the city derby?'
        sql='SELECT match_date, home_team, away_team, home_goals, away_goals FROM v_match ORDER BY match_date'
        data=execute_readonly(sql)
        issues=diagnostics(q,sql,data)
        self.assertTrue(any('finished' in issue for issue in issues))
        self.assertTrue(any('round' in issue for issue in issues))
        self.assertIsNone(normalize(q,sql,data))

    def test_out_of_scope_not_synthesized(self):
        self.assertIsNone(normalize('Which team has the most supporters?',
                         'SELECT team, points FROM v_standings ORDER BY points DESC',
                         execute_readonly('SELECT team, points FROM v_standings ORDER BY points DESC')))

    def test_parser_ignores_order_by_inside_strings_and_subqueries(self):
        sql='SELECT team, (SELECT count(*) FROM player WHERE name_fa = \'ORDER BY\') AS n FROM v_standings ORDER BY n DESC'
        places=_top_level_clauses(sql)
        self.assertEqual(len([k for k in places if k=='order']),1)
        self.assertEqual(sql[places['order']:places['order']+8].upper(),'ORDER BY')

    def test_sql_is_still_sandboxed_after_normalization(self):
        q='Top 3 clubs by their points'
        sql='SELECT team, points FROM v_standings ORDER BY points DESC LIMIT 3'
        new=normalize(q,sql,execute_readonly(sql))
        self.assertIsNotNone(new)
        self.assertEqual(execute_readonly(new)['validation'],'passed')
        with self.assertRaises(RejectedSQL):
            execute_readonly(new+'; DELETE FROM team')

    def test_normalizer_does_not_access_evaluation_or_gold(self):
        code=inspect.getsource(contract)+inspect.getsource(normalizer)
        self.assertNotIn('eval_questions.json',code)
        self.assertNotIn('gold_sql',code)
        self.assertNotIn('expected_rows',code)
        self.assertEqual(instruction('Top 2 scorers')['target_rows'],2)

if __name__=='__main__': unittest.main()

class SimulatedLivePipelineTests(unittest.TestCase):
    """Exercise live-only controls without contacting a model or leaking a secret."""
    def _route(self, sql):
        return {'action':'answer_from_query','intent':'ranking','sql':sql}

    def test_normalizer_runs_in_live_pipeline_and_reports_trace(self):
        import app.pipeline as pipe
        sql='SELECT team, points FROM v_standings ORDER BY points DESC'
        def fake_plan(*args,**kwargs):
            return self._route(sql),{'status':'ok','latency_ms':3}
        old=pipe.plan
        try:
            pipe.plan=fake_plan
            from unittest.mock import patch
            with patch.dict('os.environ',{'GAPGPT_REVIEW_ENABLED':'0','RESULT_NORMALIZATION_ENABLED':'1'}):
                result=pipe.answer('Which team has the most points?',planner=fake_plan)
        finally:
            pipe.plan=old
        self.assertEqual(result['action'],'answer_from_query')
        self.assertTrue(result['database_executed'])
        self.assertEqual(result['row_count'],3)
        self.assertEqual(result['result_normalization'],'applied')
        self.assertEqual(result['semantic_warnings'],[])
        self.assertEqual(result['validation'],'passed')

    def test_two_repairs_for_invalid_sql_are_revalidated(self):
        import app.pipeline as pipe
        candidates=['SELECT t.name FROM non_existing t',
                    'SELECT t.bad_column FROM team t',
                    'SELECT name FROM team ORDER BY name LIMIT 2']
        counter=[]
        def fake_plan(*args,**kwargs):
            candidate=candidates[min(len(counter),len(candidates)-1)]
            counter.append(candidate)
            return self._route(candidate),{'status':'ok','latency_ms':1}
        old=pipe.plan
        try:
            pipe.plan=fake_plan
            from unittest.mock import patch
            with patch.dict('os.environ',{'GAPGPT_REVIEW_ENABLED':'0','RESULT_NORMALIZATION_ENABLED':'0'}):
                result=pipe.answer('List some recorded clubs.',planner=fake_plan)
        finally:
            pipe.plan=old
        self.assertEqual(len(counter),3)
        self.assertEqual(result['validation'],'passed')
        self.assertEqual(result['row_count'],2)
        self.assertTrue(result['database_executed'])

    def test_unrecorded_metric_is_refused_before_model(self):
        import app.pipeline as pipe
        def should_not_call(*args,**kwargs):
            raise AssertionError('Unrecorded metric must not reach model')
        result=pipe.answer('Which club has the most supporters?',planner=should_not_call)
        self.assertEqual(result['action'],'refuse_out_of_scope')
        self.assertIsNone(result['sql'])
        self.assertFalse(result['database_executed'])
