"""Schema-invariant goalkeeper tests; no gold SQL/evaluation rows in production."""
import inspect
import unittest
from app.contract import diagnostics
from app.normalizer import normalize
from app.db import execute_readonly, RejectedSQL
from app import contract,normalizer

QUESTION='Which goalkeepers have the most clean sheets (started and team conceded 0)?'
DRAFT="""SELECT p.name_fa AS goalkeeper, t.name AS club, COUNT(*) AS clean_sheets
FROM lineup l JOIN v_team_match tm ON l.match_id=tm.match_id AND l.team_id=tm.team_id
JOIN player p ON l.player_id=p.player_id JOIN team t ON l.team_id=t.team_id
WHERE l.is_starter=1 AND tm.goals_against=0
GROUP BY p.player_id,t.team_id ORDER BY clean_sheets DESC, goalkeeper ASC LIMIT 5"""

class GoalkeeperInvariantTests(unittest.TestCase):
    def test_diagnostics_detects_missing_goalkeeper_role_even_when_rows_look_plausible(self):
        data=execute_readonly(DRAFT)
        self.assertEqual(data['validation'],'passed')
        self.assertTrue(any('restrict lineup.position' in i for i in diagnostics(QUESTION,DRAFT,data)))

    def test_normalizer_filters_lineup_without_rewriting_aggregation_or_joins(self):
        data=execute_readonly(DRAFT)
        sql=normalize(QUESTION,DRAFT,data)
        self.assertIsNotNone(sql)
        self.assertIn("WHERE position = 'GK'",sql)
        self.assertIn('tm.goals_against=0',sql)
        corrected=execute_readonly(sql)
        self.assertEqual(corrected['validation'],'passed')
        self.assertEqual(corrected['row_count'],5)
        self.assertFalse(any('restrict lineup.position' in i for i in diagnostics(QUESTION,sql,corrected)))
        # Independently verify every reported player came from a GK lineup row.
        roles=execute_readonly("SELECT DISTINCT p.name_fa FROM lineup l JOIN player p ON l.player_id=p.player_id WHERE l.position='GK' AND l.is_starter=1")
        keeper_names={r[0] for r in roles['rows']}
        self.assertTrue(all(row[0] in keeper_names for row in corrected['rows']))

    def test_already_correct_query_unchanged(self):
        sql=DRAFT.replace('WHERE l.is_starter=1',"WHERE l.position='GK' AND l.is_starter=1")
        self.assertFalse(any('restrict lineup.position' in i for i in diagnostics(QUESTION,sql,execute_readonly(sql))))
        self.assertIsNone(normalizer._restrict_goalkeeper_role(QUESTION,sql,diagnostics(QUESTION,sql,execute_readonly(sql))))

    def test_non_keeper_question_is_not_changed(self):
        self.assertIsNone(normalizer._restrict_goalkeeper_role('Which starters have most appearances?',DRAFT,["Goalkeeper-only statistics must restrict lineup.position = 'GK'"]))

    def test_role_rewrite_retains_readonly_invariant(self):
        fixed=normalize(QUESTION,DRAFT,execute_readonly(DRAFT))
        with self.assertRaises(RejectedSQL):execute_readonly(fixed+'; DROP TABLE lineup')

    def test_no_reference_answers_in_code(self):
        s=inspect.getsource(contract)+inspect.getsource(normalizer)
        self.assertNotIn('eval_questions.json',s)
        self.assertNotIn('expected_rows',s)
        self.assertNotIn('gold_sql',s)

class LivePipelineRoleTests(unittest.TestCase):
    def test_real_path_repairs_missing_gk_role(self):
        from unittest.mock import patch
        import app.pipeline as pipeline
        def fake(question,**kwargs):
            return ({'action':'answer_from_query','intent':'keeper_stat','sql':DRAFT},
                    {'provider':'mock','model':'none','status':'ok','latency_ms':1})
        with patch.object(pipeline,'plan',fake), patch.dict('os.environ',
             {'GAPGPT_REVIEW_ENABLED':'0','RESULT_NORMALIZATION_ENABLED':'1'}):
            result=pipeline.answer(QUESTION,planner=fake)
        self.assertEqual(result['action'],'answer_from_query')
        self.assertEqual(result['result_normalization'],'applied')
        self.assertIn("WHERE position = 'GK'",result['sql'])
        self.assertEqual(result['validation'],'passed')
        self.assertTrue(result['database_executed'])
        self.assertEqual(result['semantic_warnings'],[])


class EvaluatorTransientTests(unittest.TestCase):
    def test_model_unavailable_retry_records_second_attempt(self):
        from unittest.mock import patch
        from io import BytesIO
        from scripts import evaluate_live
        import sys
        import tempfile
        from pathlib import Path
        import json

        class FakeResponse:
            def __init__(self, data):
                self.data=data
                self.status=200
            def __enter__(self):return self
            def __exit__(self,*a):return None
            def read(self):return json.dumps(self.data).encode()

        values=[{'validation':'model_unavailable','action':'refuse_out_of_scope',
                 'answer':'GapGPT is unavailable or timed out','database_executed':False},
                {'validation':'passed','dry_run':'ok','action':'answer_from_query',
                 'sql':'SELECT 3 FROM team LIMIT 1','rows':[[3]],'row_count':1}]
        received=[]
        def fake_open(request,timeout=None):
            if isinstance(request,str) and request.endswith('/health'):
                return FakeResponse({'status':'ok'})
            received.append(1)
            return FakeResponse(values.pop(0))

        captured=[]
        def capture(path,doc,markdown=False):
            captured.append((path.name,doc))
        case={'id':'example','question_en':'Count teams?','question_fa':'',
              'expected_rows':[[3]]}
        with patch.object(evaluate_live,'CASES',[case]),\
             patch.object(evaluate_live,'urlopen',fake_open),\
             patch.object(evaluate_live,'_write_report',capture),\
             patch.object(evaluate_live.time,'sleep',lambda n:None),\
             patch.object(sys,'argv',['evaluate_live.py','http://localhost:3000']):
            self.assertEqual(evaluate_live.main(),0)
        self.assertEqual(len(received),2)
        complete=next(doc for name,doc in captured if name=='eval_report.json')
        self.assertEqual(complete['results'][0]['attempts'],2)
        self.assertTrue(complete['results'][0]['pass'])

    def test_security_refusal_is_not_retried(self):
        from unittest.mock import patch
        from scripts import evaluate_live
        import sys
        import json
        class FakeResponse:
            status=200
            def __init__(self, data):self.data=data
            def __enter__(self):return self
            def __exit__(self,*a):pass
            def read(self):return json.dumps(self.data).encode()
        received=[]
        def fake_open(request,timeout=None):
            if isinstance(request,str):return FakeResponse({'status':'ok'})
            received.append(1)
            return FakeResponse({'validation':'blocked_by_policy', 'dry_run':'not_run',
                'action':'refuse_write','sql':None,'database_executed':False})
        case={'id':'trap','question_en':'Delete matches.','question_fa':'',
              'expected_behaviour':'refuse'}
        with patch.object(evaluate_live,'CASES',[case]),\
             patch.object(evaluate_live,'urlopen',fake_open),\
             patch.object(evaluate_live,'_write_report',lambda *a,**k:None),\
             patch.object(sys,'argv',['evaluate_live.py','http://localhost:3000']):
            self.assertEqual(evaluate_live.main(),0)
        self.assertEqual(len(received),1)
