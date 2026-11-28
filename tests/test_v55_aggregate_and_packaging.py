import unittest
from app.aggregate_repair import conditional_count_candidate
from app.db import execute_readonly
from app.pipeline import answer
from app.semantic_checks import inspect

class AggregateTests(unittest.TestCase):
    def test_generic_boolean_count_counts_only_true(self):
        q='How many wins and draws did each club record away from home?'
        bad="SELECT team_id, COUNT(outcome = 'W'), COUNT(outcome = 'D') FROM v_team_match WHERE venue='away' GROUP BY team_id"
        fixed=conditional_count_candidate(q,bad)
        self.assertIsNotNone(fixed)
        reference="SELECT team_id, SUM(CASE WHEN outcome='W' THEN 1 ELSE 0 END), SUM(CASE WHEN outcome='D' THEN 1 ELSE 0 END) FROM v_team_match WHERE venue='away' GROUP BY team_id"
        self.assertEqual(execute_readonly(fixed)['rows'],execute_readonly(reference)['rows'])
        self.assertNotEqual(execute_readonly(bad)['rows'],execute_readonly(reference)['rows'])
        self.assertTrue(any('Conditional COUNT' in x for x in inspect(q,bad,execute_readonly(bad))))
    def test_no_rewrite_comments_or_unrelated_requests(self):
        self.assertIsNone(conditional_count_candidate('How many goals?',"SELECT COUNT(*) FROM goal -- COUNT(is_own_goal = 1)"))
        self.assertIsNone(conditional_count_candidate('List team names',"SELECT COUNT(outcome = 'W') FROM v_team_match"))
    def test_pipeline_reruns_validated_correction(self):
        sql="SELECT COUNT(is_own_goal = 1) AS total FROM goal"
        def planner(*args,**kwargs):
            return {'action':'answer_from_query','intent':'count events','sql':sql}, {'latency_ms':0}
        r=answer('How many own goals are recorded?',planner=planner)
        self.assertEqual(r['rows'],execute_readonly('SELECT COUNT(*) FROM goal WHERE is_own_goal=1')['rows'])
        self.assertIn('CASE WHEN',r['sql'])
        self.assertEqual(r['validation'],'passed')
        self.assertEqual(r['review_evidence'][0]['stage'],'conditional_count_repair')

class RankingTests(unittest.TestCase):
    def test_explicit_rank_tie_is_stable_without_changing_metrics(self):
        from app.normalizer import stabilize_explicit_ranking
        sql='SELECT team, played FROM v_standings ORDER BY played DESC LIMIT 4'
        q='Show top 4 clubs by games played in the league table'
        original=execute_readonly(sql)
        revised,actual=stabilize_explicit_ranking(q,sql,original,execute_readonly)
        self.assertIn(', 1 ASC',revised)
        self.assertEqual(actual['rows'],execute_readonly('SELECT team, played FROM v_standings ORDER BY played DESC, team ASC LIMIT 4')['rows'])
        self.assertEqual([x[1] for x in original['rows']],[x[1] for x in actual['rows']])
    def test_no_invented_limit_or_unspecified_ranking(self):
        from app.normalizer import stabilize_explicit_ranking
        sql='SELECT team, played FROM v_standings ORDER BY played DESC LIMIT 4'
        self.assertIsNone(stabilize_explicit_ranking('Which team played the most games?',sql,execute_readonly(sql),execute_readonly))
