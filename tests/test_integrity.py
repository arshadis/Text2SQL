"""Audited-release invariants; no live provider calls or reference-answer tuning."""
from __future__ import annotations
import json
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from app import llm, contract, normalizer, source_fingerprint, narrative, pipeline
from app.db import execute_readonly, RejectedSQL
from scripts.capture_traces import valid_join, valid_refusal, valid_clarification, CLARIFICATION_CANDIDATES

ROOT=Path(__file__).resolve().parents[1]

class PromptIndependence(unittest.TestCase):
    def test_no_specialized_evaluation_recipes_in_semantic_model(self):
        semantic=(ROOT/'data/semantic_model.md').read_text(encoding='utf-8')
        self.assertIn('v_team_match',semantic)
        self.assertIn('scorer_team_id',semantic)
        self.assertIn('second_yellow',semantic)
        self.assertNotIn('## Analytic result shapes and temporal derivations',semantic)
        for forbidden in ('minute>75','MIN(match.round)', 'COUNT(DISTINCT match_id)', 'prefer 3 for team', 'prefer 5 for player'):
            self.assertNotIn(forbidden,semantic)
    def test_model_prompt_no_fixed_top_k_or_eval_gold_recipe(self):
        self.assertIn('do not assume a universal top-3/top-5',llm.SYSTEM)
        self.assertNotIn('minute>75',llm.SYSTEM)
        self.assertNotIn('first recorded round',llm.SYSTEM)
    def test_no_inference_path_loads_eval_queries(self):
        for filename in ('app/contract.py','app/normalizer.py','app/llm.py','app/quality.py','app/pipeline.py','app/narrative.py'):
            src=(ROOT/filename).read_text(encoding='utf-8')
            self.assertNotIn("open('data/eval_questions",src)
            self.assertNotIn('CASES=',src)
    def test_ranking_count_only_user_explicit(self):
        self.assertIsNone(contract.infer_contract('Which referee has the most bookings?').target_rows)
        self.assertIsNone(contract.infer_contract('Which player has the most minutes?').target_rows)
        self.assertEqual(contract.infer_contract('Top 4 scorers').target_rows,4)
        self.assertEqual(contract.infer_contract('۵ گلزن برتر').target_rows,5)
        self.assertEqual(contract.infer_contract('Who is top of the league table?').target_rows,1)
    def test_no_uncalled_special_sql_rewrite(self):
        self.assertFalse(hasattr(normalizer,'_restrict_goalkeeper_role'))
        self.assertFalse(hasattr(normalizer,'_complete_own_goal_club_projection'))
        self.assertFalse(hasattr(normalizer,'_align_goal_view_team_join'))
        self.assertIsNone(normalizer.normalize('Which team scored most goals?',
            'SELECT name FROM team',{'columns':['name'],'rows':[['A']],'row_count':1}))
    def test_explicit_limit_normalization_only(self):
        sql='SELECT team, points FROM v_standings ORDER BY points DESC'
        rows=execute_readonly(sql)
        self.assertIsNone(normalizer.normalize('Which teams have most points?',sql,rows))
        candidate=normalizer.normalize('Top 4 clubs by points',sql,rows)
        self.assertIsNotNone(candidate)
        self.assertEqual(execute_readonly(candidate)['row_count'],4)
        self.assertEqual(candidate.endswith('LIMIT 4'),True)
    def test_model_return_schema_remains_fail_closed(self):
        with self.assertRaises(llm.ModelError):
            llm._extract('{"action":"refuse_write","sql":"DELETE FROM team"}')

class EvidenceAndSafety(unittest.TestCase):
    def test_readonly_invariant_and_sql_injection(self):
        with self.assertRaises(RejectedSQL):
            execute_readonly('SELECT * FROM team; DELETE FROM team')
    def test_factual_summary_comes_from_rows(self):
        result={'columns':['player','team','goals'],
                'rows':[['بازیکن نمونه','Team Alpha',5],['بازیکن دوم','Team Beta',4]], 'row_count':2}
        txt=narrative.summarize(result)
        self.assertIn('بازیکن نمونه',txt)
        self.assertIn('Team Beta',txt)
        self.assertIn('۵ گل',txt)
        self.assertNotIn('پرسپولیس',txt)
    def test_summary_never_asserts_unobserved_row(self):
        txt=narrative.summarize({'columns':['n'],'rows':[[23]],'row_count':1})
        self.assertIn('۲۳',txt)
    def test_refusal_never_executes(self):
        result=pipeline.answer('بازی ها را پاک کن',planner=lambda *a,**k: (_ for _ in ()).throw(AssertionError('model must not be called')))
        self.assertEqual(result['action'],'refuse_write')
        self.assertIsNone(result['sql'])
        self.assertFalse(result['database_executed'])
    def test_clarification_trace_authentic(self):
        data={'action':'ask_clarifying_question','sql':None,'database_executed':False,'answer':'کدام معیار؟'}
        self.assertTrue(valid_clarification(data))
        self.assertFalse(valid_clarification({**data,'sql':'SELECT 1'}))
        self.assertIn('بهترین بازیکن کیست؟',CLARIFICATION_CANDIDATES[:1])
    def test_review_evidence_public_on_mock(self):
        def plan(*a,**k):
            return {'action':'answer_from_query','intent':'teams','sql':'SELECT name FROM team LIMIT 2'}, {'status':'ok','latency_ms':1}
        r=pipeline.answer('Show some teams',planner=plan,reviewer=plan)
        self.assertIn('review_evidence',r)
        self.assertTrue(r['database_executed'])

class ReleaseProvenance(unittest.TestCase):
    def test_source_hash_64_character_and_stable(self):
        x=source_fingerprint.pipeline_sha256()
        self.assertEqual(len(x),64)
        self.assertRegex(x,r'^[0-9a-f]{64}$')
        self.assertEqual(x,source_fingerprint.pipeline_sha256())
    def test_old_report_cannot_be_packaged_as_new_release(self):
        from scripts import build_submission
        import sys
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            (root/'reports').mkdir()
            (root/'reports'/'eval_report.json').write_text(json.dumps({
                'url':'https://example.darkube.ir', 'pipeline_sha256':'old',
                'total':17, 'results':[{'pass':True}]*17, 'passed':17}),encoding='utf-8')
            (root/'reports'/'eval_report.md').write_text('historical sample',encoding='utf-8')
            (root/'reports'/'traces.json').write_text(json.dumps({
                'public_url':'https://example.darkube.ir','pipeline_sha256':'old','traces':[]}),encoding='utf-8')
            (root/'reports'/'traces.md').write_text('historical sample',encoding='utf-8')
            with patch.object(build_submission,'ROOT',root),patch.object(sys,'argv',[
                'build_submission.py','https://example.darkube.ir']):
                with self.assertRaises(SystemExit) as ex:
                    build_submission.main()
                self.assertEqual(ex.exception.code,2)

    def test_fingerprint_changes_when_source_changes(self):
        with tempfile.TemporaryDirectory() as td:
            d=Path(td)
            (d/'app').mkdir();(d/'data').mkdir()
            (d/'app'/'llm.py').write_text('one')
            for f in ('semantic_model.md','schema.sql','football.db'):(d/'data'/f).write_text('same')
            with patch.object(source_fingerprint,'ROOT',d):
                first=source_fingerprint.pipeline_sha256()
                (d/'app'/'llm.py').write_text('two')
                self.assertNotEqual(first,source_fingerprint.pipeline_sha256())

if __name__=='__main__':unittest.main()
