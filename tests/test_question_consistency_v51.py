"""Independent consistency tests; no evaluator question text or reference SQL."""
from __future__ import annotations

import unittest
from app.db import execute_readonly
from app.pipeline import answer, _same_facts_after_projection
from app.semantic_checks import inspect


class QuestionConsistencyTests(unittest.TestCase):
    @staticmethod
    def _plan(sql):
        def plan(*_,**kw):
            return ({'action':'answer_from_query','intent':'public stats','sql':sql},
                    {'status':'ok','latency_ms':1})
        return plan

    def test_bad_ranking_rewrite_cannot_win_with_a_tiebreaker(self):
        original='SELECT team, points FROM v_standings ORDER BY points DESC LIMIT 2'
        changed='SELECT team, points FROM v_standings ORDER BY points ASC, team ASC LIMIT 2'
        def reviewer(*a,**kw):
            return ({'action':'answer_from_query','intent':'better style','sql':changed},
                    {'status':'ok','latency_ms':1})
        actual=answer('Show clubs ranked by points', planner=self._plan(original), reviewer=reviewer)
        self.assertEqual(actual['sql'], original)
        self.assertEqual(actual['quality_review'], 'rejected_regression')
        self.assertFalse(actual['review_evidence'][0]['decision']=='accepted')
        self.assertFalse(_same_facts_after_projection(execute_readonly(original), execute_readonly(changed)))

    def test_projection_only_cleanup_can_be_accepted(self):
        original='SELECT team_id, team, points FROM v_standings ORDER BY points DESC, team ASC LIMIT 4'
        revised='SELECT team, points FROM v_standings ORDER BY points DESC, team ASC LIMIT 4'
        def reviewer(*a,**kw):
            return ({'action':'answer_from_query','intent':'readable output','sql':revised},
                    {'status':'ok','latency_ms':1})
        actual=answer('Show clubs ranked by points', planner=self._plan(original),reviewer=reviewer)
        self.assertEqual(actual['sql'], revised)
        self.assertEqual(actual['quality_review'], 'adopted')
        self.assertTrue(_same_facts_after_projection(execute_readonly(original),execute_readonly(revised)))

    def test_team_only_output_is_not_individual_scorers(self):
        sql=('SELECT t.name AS team_name, COUNT(g.goal_id) AS goals '
             'FROM goal g JOIN team t ON g.scorer_team_id=t.team_id '
             'WHERE g.is_own_goal=0 GROUP BY t.team_id ORDER BY goals DESC')
        r=execute_readonly(sql)
        self.assertTrue(any('individual goal scorers' in x for x in inspect(
            'Show leading scorers and their teams',sql,r)))
        good=('SELECT p.name_fa AS player_name, t.name AS team_name, '
              'COUNT(*) AS goals FROM goal g JOIN player p ON p.player_id=g.player_id '
              'JOIN team t ON g.scorer_team_id=t.team_id WHERE g.is_own_goal=0 '
              'GROUP BY p.player_id, t.team_id ORDER BY goals DESC')
        self.assertFalse(any('individual goal scorers' in x for x in inspect(
            'Show leading scorers and their teams',good,execute_readonly(good))))

    def test_own_goal_beneficiary_must_link_credited_role(self):
        wrong=('SELECT g.team_id AS credited_team_id, p.name_fa AS scorer, t.name AS beneficiary '
               'FROM goal g JOIN "match" m ON m.match_id=g.match_id '
               'JOIN player p ON p.player_id=g.player_id '
               'JOIN team t ON t.team_id=m.home_team_id '
               'WHERE g.is_own_goal=1')
        correct=('SELECT p.name_fa AS scorer, t.name AS beneficiary FROM goal g '
                 'JOIN player p ON p.player_id=g.player_id '
                 'JOIN team t ON t.team_id=g.team_id WHERE g.is_own_goal=1')
        question='List own goals and which team benefited from each goal'
        self.assertTrue(any('explicit join' in x for x in inspect(question,wrong,execute_readonly(wrong))))
        self.assertFalse(any('explicit join' in x for x in inspect(question,correct,execute_readonly(correct))))

    def test_persistent_semantic_contradiction_gets_bounded_repair(self):
        invalid=('SELECT team, points FROM v_standings '
                 'WHERE team_id IN (SELECT team_id FROM v_team_match WHERE venue=\'home\') '
                 'ORDER BY points DESC LIMIT 1')
        corrected=("SELECT t.name AS team, SUM(CASE tm.outcome WHEN 'W' THEN 3 "
                   "WHEN 'D' THEN 1 ELSE 0 END) AS points "
                   'FROM v_team_match tm JOIN team t ON t.team_id=tm.team_id '
                   "WHERE tm.venue='home' GROUP BY tm.team_id ORDER BY points DESC")
        stages=[]
        def reviewer(*a,**kw):
            mode=kw['feedback']['mode']
            stages.append(mode)
            if mode=='bounded_question_consistency_repair':
                sql=corrected
            else:
                sql=invalid
            return ({'action':'answer_from_query','intent':'home points','sql':sql},
                    {'status':'ok','latency_ms':1})
        r=answer('Show points earned at home by each club',
                 planner=self._plan(invalid),reviewer=reviewer)
        self.assertEqual(r['sql'],corrected)
        self.assertIn('bounded_question_consistency_repair',stages)
        self.assertEqual(r['quality_review'],'semantic_repair_adopted')
        self.assertEqual(r['review_evidence'][-1]['decision'],'accepted')

    def test_review_candidate_cannot_write(self):
        bad='SELECT t.name AS team_name, COUNT(*) AS goals FROM goal g JOIN team t ON t.team_id=g.team_id GROUP BY t.team_id'
        def reviewer(*a,**kw):
            return ({'action':'answer_from_query','intent':'unsafe','sql':'DROP TABLE goal'},
                    {'status':'ok','latency_ms':1})
        r=answer('Show top goal scorers by player',planner=self._plan(bad),reviewer=reviewer)
        self.assertEqual(r['sql'],bad)
        self.assertTrue(r['database_executed'])
        self.assertEqual(r['validation'],'passed')
        self.assertIn(r['quality_review'],['semantic_repair_unavailable','rejected_revision'])


if __name__=='__main__': unittest.main()
