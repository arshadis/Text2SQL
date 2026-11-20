"""General presentation and review stability; no evaluator records or reference SQL."""
import unittest
from app.pipeline import answer
from app.quality import semantic_signal, review_feedback
from app.llm import SYSTEM, SEMANTIC


class IndependentReasoningTests(unittest.TestCase):
    def _planner(self, sql):
        def mock(*args, **kwargs):
            return ({'action': 'answer_from_query', 'intent': 'compare', 'sql': sql},
                    {'status': 'ok', 'latency_ms': 1})
        return mock

    def test_review_rejects_single_row_degraded_leaderboard(self):
        original = 'SELECT team, points FROM v_standings ORDER BY points DESC LIMIT 3'
        worse = 'SELECT team, points FROM v_standings ORDER BY points DESC LIMIT 1'
        result = answer('Which team has the most points?', planner=self._planner(original),
                        reviewer=self._planner(worse))
        self.assertEqual(result['quality_review'], 'rejected_regression')
        self.assertEqual(result['sql'], original)
        self.assertEqual(result['row_count'], 3)

    def test_review_adopts_better_ranked_leaderboard(self):
        original = 'SELECT team, points FROM v_standings ORDER BY points DESC LIMIT 1'
        improved = 'SELECT team, points FROM v_standings ORDER BY points DESC LIMIT 3'
        result = answer('Which team has the most points?', planner=self._planner(original),
                        reviewer=self._planner(improved))
        self.assertEqual(result['quality_review'], 'adopted')
        self.assertEqual(result['sql'], improved)
        self.assertEqual(result['row_count'], 3)

    def test_internal_ids_unwanted_when_readable_names_exist(self):
        poor = {'columns':['team_id','points'], 'rows':[[1,22]], 'row_count':1}
        good = {'columns':['team','points'], 'rows':[['Foo',22]], 'row_count':1}
        q='Which club has the most points?'
        self.assertGreater(semantic_signal(q,'SELECT team,points FROM v_standings',good),
                           semantic_signal(q,'SELECT team_id,points FROM v_standings',poor))

    def test_explicit_top_n_is_preferred(self):
        r3 = {'columns':['team','points'], 'rows':[['A',1],['B',1],['C',1]], 'row_count':3}
        r5 = {'columns':['team','points'], 'rows':[['A',1]]*5, 'row_count':5}
        q='Top 5 teams by points'
        self.assertGreater(semantic_signal(q,'SELECT team,points FROM v_standings',r5),
                           semantic_signal(q,'SELECT team,points FROM v_standings',r3))

    def test_formation_and_coach_derive_from_schema_not_gold(self):
        self.assertIn('match_coach',SEMANTIC)
        self.assertIn('home_formation',SEMANTIC)
        self.assertIn('coaches and formations',SYSTEM.lower())
        feedback = review_feedback('How many formations have coaches used?',
                                   'SELECT team FROM v_standings LIMIT 1',
                                   {'columns':['team'],'rows':[['X']],'row_count':1})
        self.assertTrue(any('match_coach' in h for h in feedback['review_hints']))
        self.assertNotIn('expected_rows',repr(feedback))

if __name__ == '__main__':
    unittest.main()
