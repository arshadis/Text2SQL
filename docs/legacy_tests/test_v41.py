"""General outcome-shaping and resilient diagnostic-evaluator tests.

No reference answers or gold SQL in the user-facing planner.
"""
import io
import json
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch
from pathlib import Path
from tempfile import TemporaryDirectory
from app.contract import diagnostics
from app.normalizer import normalize
from app.db import execute_readonly
from scripts import evaluate_live

class BetterContracts(unittest.TestCase):
    def test_red_cards_report_club_and_single_metric_without_translation(self):
        question='Which team has received the most red cards (including second yellows)?'
        candidate="""SELECT t.name AS team, t.name_fa AS team_fa, COUNT(*) AS red_cards
        FROM card c JOIN team t ON c.team_id=t.team_id
        WHERE c.card_type IN ('red','second_yellow')
        GROUP BY t.team_id ORDER BY red_cards DESC, t.name ASC"""
        rows=execute_readonly(candidate)
        self.assertTrue(diagnostics(question,candidate,rows))
        transformed=normalize(question,candidate,rows)
        self.assertIsNotNone(transformed)
        actual=execute_readonly(transformed)
        self.assertEqual(actual['row_count'],rows['row_count'])
        self.assertEqual(actual['columns'],['team','red_cards'])
        self.assertEqual(diagnostics(question,transformed,actual),[])

    def test_own_goals_remove_only_unrequested_date_and_preserve_events(self):
        question='List all own goals: match, scorer, and which team benefited.'
        candidate='''SELECT g.match_id, m.match_date, p.name_fa AS scorer,
          ts.name AS scorer_team, tb.name AS benefited_team,
          g.minute, g.added_time FROM goal g
          JOIN "match" m ON m.match_id=g.match_id
          JOIN player p ON p.player_id=g.player_id
          JOIN team ts ON ts.team_id=g.scorer_team_id
          JOIN team tb ON tb.team_id=g.team_id
          WHERE g.is_own_goal=1'''
        data=execute_readonly(candidate)
        self.assertEqual(data['row_count'],8)
        self.assertTrue(diagnostics(question,candidate,data))
        transformed=normalize(question,candidate,data)
        self.assertIsNotNone(transformed)
        after=execute_readonly(transformed)
        self.assertEqual(after['row_count'],8)
        self.assertEqual(after['columns'],['match_id','scorer','scorer_team','benefited_team','minute','added_time'])
        self.assertEqual(diagnostics(question,transformed,after),[])
        self.assertEqual(after['rows'][0][0],486079)
        self.assertEqual(after['rows'][0][1],'علیرضا آرتا')

    def test_coach_changes_detect_incomplete_one_coach_per_team(self):
        q='Which teams changed head coach during the season, and who were the coaches?'
        data={'columns':['team','coach_name','first_round','last_round','games'],
              'rows':[['Example Club','Coach 1',1,5,5],['Another Club','Coach 3',1,4,4]],
              'row_count':2}
        issues=diagnostics(q,'SELECT 1 FROM match_coach',data)
        self.assertTrue(any('EVERY distinct' in x for x in issues))
        completed={'columns':data['columns'],
            'rows':[['Example Club','Coach 1',1,5,5],['Example Club','Coach 2',6,9,4]],
            'row_count':2}
        self.assertFalse(any('EVERY distinct' in x for x in diagnostics(q,'SELECT 1 FROM match_coach',completed)))

    def test_own_goals_dont_remove_date_explicitly_requested(self):
        q='List all own goals with match date, scorer, and which team benefited.'
        sample={'columns':['match_id','match_date','scorer','benefited_team','minute','added_time'],
                'rows':[[1,'2026-09-02','A','B',90,1]],'row_count':1}
        sql='SELECT match_id, match_date, scorer, benefited_team, minute, added_time FROM example ORDER BY match_id'
        self.assertFalse(any('unrequested' in x for x in diagnostics(q,sql,sample)))

    def test_coach_contract_expects_stints_not_pairs(self):
        q='Which teams changed head coach during the season, and who were the coaches?'
        bad={'columns':['team','previous_coach','current_coach','coaches'],
             'rows':[['A','B','C',2]],'row_count':1}
        errs=diagnostics(q,'SELECT name FROM team',bad)
        self.assertTrue(any('PER (team, coach)' in err for err in errs))
        self.assertTrue(any('first and last' in err for err in errs))

class EvaluatorResilience(unittest.TestCase):
    def test_subset_results_do_not_overwrite_full_submission_report(self):
        with TemporaryDirectory() as td:
            root=Path(td)
            existing=root/'eval_report.json'
            existing.write_text('{"old":"keep"}',encoding='utf8')
            d={'url':'http://localhost:3000','generated_at':'test','passed':1,
               'total':1,'status':'subset_complete','results':[]}
            evaluate_live._write_report(root/'eval_subset_report.json',d)
            self.assertEqual(existing.read_text(encoding='utf8'),'{"old":"keep"}')
            self.assertEqual(json.loads((root/'eval_subset_report.json').read_text())['status'],'subset_complete')

if __name__=='__main__':unittest.main()
