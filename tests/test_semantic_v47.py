"""Independent paraphrase tests: no evaluator prompts, gold SQL or result arrays."""
from __future__ import annotations
import unittest
from app.semantic_checks import inspect
from app.contract import diagnostics
from app.normalizer import remove_unrequested_ids, normalize
from app.db import execute_readonly
from app.pipeline import answer

class QuestionGroundedConsistency(unittest.TestCase):
    @staticmethod
    def data(columns,rows):
        return {'columns':columns,'rows':rows,'row_count':len(rows),'truncated':False}

    def test_past_score_cannot_include_fixtures_without_results(self):
        d=self.data(['home_team','away_team','home_goals','away_goals'],[['Alfa','Beta',1,2],['Beta','Alfa',None,None]])
        text='How did the score of the match between Alfa and Beta end?'
        bad="SELECT home_team, away_team, home_goals, away_goals FROM v_match"
        problems=inspect(text,bad,d)
        self.assertTrue(any('NULL final scores' in x for x in problems))
        self.assertFalse(any('NULL final scores' in x for x in inspect(text,bad,self.data(d['columns'],d['rows'][:1]))))

    def test_home_scope_not_equivalent_to_overall_standings(self):
        d=self.data(['team','points'],[['Alfa',20]])
        bad="SELECT team, points FROM v_standings WHERE team_id IN (SELECT team_id FROM v_team_match WHERE venue='home')"
        problems=inspect('Compare points earned in home fixtures by clubs',bad,d)
        self.assertTrue(any('home/away-only' in x for x in problems))
        valid="SELECT t.name AS team, SUM(CASE tm.outcome WHEN 'W' THEN 3 WHEN 'D' THEN 1 ELSE 0 END) AS points FROM v_team_match tm JOIN team t ON t.team_id=tm.team_id WHERE tm.venue='home' GROUP BY tm.team_id"
        self.assertFalse(any('home/away-only' in x for x in inspect('Compare points earned in home fixtures by clubs',valid,d)))

    def test_goalkeeper_zero_conceded_is_team_specific(self):
        d=self.data(['name','n'],[['Alfa keeper',7]])
        bad="SELECT p.name_fa AS name, COUNT(*) AS n FROM lineup l JOIN match m ON l.match_id=m.match_id JOIN player p ON l.player_id=p.player_id WHERE l.position='GK' AND l.is_starter=1 AND (m.home_goals=0 OR m.away_goals=0) GROUP BY l.player_id"
        problems=inspect('Which keepers recorded shutouts (clean sheets) for their own clubs?',bad,d)
        self.assertTrue(any('own team' in x for x in problems))

    def test_credited_and_scoring_teams_are_distinct_roles(self):
        d=self.data(['home_team','away_team','scorer'],[['Alfa','Beta','P']])
        bad='SELECT home_team,away_team,scorer FROM goal g JOIN v_match vm ON g.match_id=vm.match_id'
        self.assertTrue(any('credited team' in x for x in inspect('Show all own goals and the club that benefited',bad,d)))
        good='SELECT credited.name AS beneficiary, scoring.name AS original_club FROM goal g JOIN team credited ON credited.team_id=g.team_id JOIN team scoring ON scoring.team_id=g.scorer_team_id WHERE g.is_own_goal=1'
        self.assertFalse(any('credited team' in x for x in inspect('Show all own goals and the club that benefited',good,d)))

    def test_registered_entities_with_zero_events_need_left_join(self):
        d=self.data(['name','n'],[['Alfa',3]])
        text='Show every registered venue, including counts of recorded fixtures'
        bad="SELECT s.name_fa AS name, COUNT(m.match_id) AS n FROM stadium s LEFT JOIN match m ON s.stadium_id=m.stadium_id WHERE m.status='finished' GROUP BY s.stadium_id"
        issues=inspect(text,bad,d)
        self.assertTrue(any('LEFT JOIN' in x for x in issues))

    def test_internal_id_cleanup_preserves_query_semantics(self):
        question='Show four clubs with points and their readable club labels'
        sql='SELECT team_id, team, points FROM v_standings ORDER BY points DESC, team ASC LIMIT 4'
        before=execute_readonly(sql)
        cleaned=remove_unrequested_ids(question,sql,before)
        self.assertIsNotNone(cleaned)
        self.assertNotIn('team_id, team',cleaned)
        after=execute_readonly(cleaned)
        self.assertEqual(after['columns'],['team','points'])
        self.assertEqual(after['rows'],[[r[1],r[2]] for r in before['rows']])

    def test_explicit_id_request_never_removed(self):
        sql='SELECT team_id, name FROM team LIMIT 2'
        d=execute_readonly(sql)
        self.assertIsNone(remove_unrequested_ids('Show team IDs and club names',sql,d))

    def test_distinct_projection_not_modified(self):
        sql='SELECT DISTINCT team_id, name FROM team'
        d=execute_readonly(sql)
        self.assertIsNone(remove_unrequested_ids('Show all club names',sql,d))

    def test_positional_order_not_modified(self):
        sql='SELECT team_id, name FROM team ORDER BY 1 LIMIT 3'
        d=execute_readonly(sql)
        self.assertIsNone(remove_unrequested_ids('Show club names',sql,d))

    def test_cte_not_altered_by_projection_cleanup(self):
        sql='WITH c AS (SELECT team_id, name FROM team) SELECT team_id, name FROM c LIMIT 2'
        d=execute_readonly(sql)
        self.assertIsNone(remove_unrequested_ids('Show team names',sql,d))

    def test_still_no_implicit_rank_count(self):
        self.assertIsNone(normalize('Show clubs sorted by points',
            'SELECT team, points FROM v_standings ORDER BY points DESC',
            execute_readonly('SELECT team, points FROM v_standings ORDER BY points DESC')))

    def test_scalar_count_does_not_require_person_name(self):
        data=execute_readonly('SELECT COUNT(*) AS total FROM referee')
        issues=diagnostics('How many referees were recorded?', 'SELECT COUNT(*) AS total FROM referee',data)
        self.assertFalse(any('No readable entity label' in x for x in issues))

    def test_review_records_original_and_candidate_sql(self):
        original='SELECT team, points FROM v_standings LIMIT 2'
        revised='SELECT team, points FROM v_standings ORDER BY points DESC, team ASC LIMIT 2'
        def plan(*a,**kw):
            return {'action':'answer_from_query','intent':'table','sql':original}, {'status':'ok','latency_ms':1}
        def review(*a,**kw):
            return {'action':'answer_from_query','intent':'table','sql':revised}, {'status':'ok','latency_ms':1}
        res=answer('Show clubs ranked by points',planner=plan,reviewer=review)
        ev=res['review_evidence'][0]
        self.assertEqual(ev['original_sql'],original)
        self.assertEqual(ev['candidate_sql'],revised)
        self.assertIn('reason',ev)

if __name__=='__main__': unittest.main()
