"""Release scoring and data-source separation checks, with no live API calls."""
import json
import unittest
from pathlib import Path

from scripts.evaluate_live import score
from app.db import execute_readonly, RejectedSQL
from app.llm import _extract, ModelError, SYSTEM

ROOT=Path(__file__).resolve().parents[1]

class ReleaseChecks(unittest.TestCase):
    def test_refusal_trap_never_runs_sql(self):
        case={'expected_behaviour':'refuse_or_explain'}
        self.assertTrue(score(case,{'action':'refuse_out_of_scope','sql':None,'database_executed':False})[0])
        self.assertTrue(score(case,{'action':'refuse_write','sql':None,'database_executed':False})[0])
        self.assertFalse(score(case,{'action':'refuse_write','sql':'SELECT * FROM team','database_executed':False})[0])
        self.assertFalse(score(case,{'action':'answer_from_query','sql':'SELECT * FROM team','database_executed':True})[0])
    def test_evaluator_ignores_order_except_rankings(self):
        base={'expected_rows':[[1],[2]],'question_en':'List all records','question_fa':''}
        data={'action':'answer_from_query','validation':'passed','dry_run':'ok','rows':[[2],[1]]}
        self.assertTrue(score(base,data)[0])
        self.assertFalse(score({**base,'question_en':'Top 2 records'},data)[0])
    def test_evaluator_compares_actual_values_not_only_counts(self):
        case={'expected_rows':[[95]],'question_en':'How many?','question_fa':''}
        data={'action':'answer_from_query','validation':'passed','dry_run':'ok','rows':[[94]]}
        self.assertFalse(score(case,data)[0])
    def test_all_source_evaluation_questions_present(self):
        items=json.loads((ROOT/'data'/'eval_questions.json').read_text(encoding='utf8'))
        self.assertEqual(len(items),17)
        self.assertEqual(sum(v.get('gold_sql') is not None for v in items),15)
    def test_model_never_receives_gold_queries(self):
        self.assertNotIn('gold_sql',SYSTEM)
        # The app reads only these two independent context files; eval data is
        # kept in scripts/ and excluded from the production Docker image.
        from app import llm
        self.assertIn('schema.sql',str(llm.ROOT/'data'/'schema.sql'))
        self.assertNotIn('eval_questions.json',llm.__dict__.get('SCHEMA',''))
        self.assertNotIn('eval_questions.json',llm.__dict__.get('SEMANTIC',''))
    def test_llm_action_schema_fail_closed(self):
        with self.assertRaises(ModelError):_extract('{"action":"answer_from_query", "sql":null}')
        with self.assertRaises(ModelError):_extract('{"action":"refuse_write", "sql":"SELECT 1"}')
    def test_reserved_match_table_can_be_queried_with_quotes(self):
        self.assertEqual(execute_readonly('SELECT COUNT(*) FROM "match" WHERE status = \'finished\'')['rows'],[[95]])
        with self.assertRaises(RejectedSQL):execute_readonly('SELECT unknown_column FROM "match"')

if __name__=='__main__':unittest.main()
