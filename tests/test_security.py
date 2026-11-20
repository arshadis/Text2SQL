import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from app.db import validate_sql, RejectedSQL, execute_readonly, DB_PATH
from app.pipeline import answer
from app.llm import ModelError, _extract

class SqlSecurityTests(unittest.TestCase):
    def test_readonly_connection_and_valid_existing_sql(self):
        r=execute_readonly("SELECT COUNT(*) AS played FROM \"match\" WHERE status='finished'")
        self.assertEqual(r['rows'],[[95]])
        self.assertEqual(r['validation'],'passed')
        self.assertIn('match',r['tables'])
        self.assertIn('match.status',r['fields'])
    def test_views_and_columns_exist(self):
        r=execute_readonly('SELECT team, played, points FROM v_standings ORDER BY points DESC LIMIT 1')
        self.assertEqual(r['rows'][0][0],'Persepolis')
    def test_cte_allowed(self):
        r=execute_readonly('WITH x AS (SELECT team_id FROM team) SELECT COUNT(*) FROM x')
        self.assertEqual(r['rows'],[[18]])
    def test_single_statement_only(self):
        for sql in ['SELECT 1; DELETE FROM team', 'SELECT 1; SELECT 2', 'SELECT 1;;',
                    'WITH t AS (DELETE FROM team RETURNING *) SELECT * FROM t']:
            with self.subTest(sql=sql), self.assertRaises(RejectedSQL):validate_sql(sql)
    def test_forbidden_actions(self):
        for sql in ['DELETE FROM match', 'UPDATE team SET name="x"', 'DROP TABLE team',
                    'ATTACH DATABASE "/tmp/test.db" AS other','PRAGMA table_info(team)',
                    'INSERT INTO team VALUES (1,2)', 'SELECT load_extension("x")']:
            with self.subTest(sql=sql), self.assertRaises(RejectedSQL):validate_sql(sql)
    def test_embedded_keywords_in_literal_are_safe(self):
        self.assertEqual(execute_readonly("SELECT 'DELETE; DROP' AS example FROM team LIMIT 1")['rows'],[['DELETE; DROP']])
    def test_query_must_retrieve_from_real_db(self):
        with self.assertRaises(RejectedSQL):execute_readonly("SELECT 'Persepolis has 99 points'")
    def test_forged_schema_table(self):
        with self.assertRaises(RejectedSQL):execute_readonly('SELECT name FROM sqlite_master')
        with self.assertRaises(RejectedSQL):execute_readonly('SELECT unknown_field FROM team')
    def test_unknown_function_rejected(self):
        with self.assertRaises(RejectedSQL):execute_readonly('SELECT sqlite_version()')
    def test_external_file_not_readable(self):
        for sql in ["SELECT readfile('/etc/passwd')", "SELECT * FROM sqlite_dbpage"]:
            with self.subTest(sql=sql), self.assertRaises(RejectedSQL):execute_readonly(sql)
    def test_immutable_database_never_writable(self):
        from app.db import ro_connection
        c=ro_connection()
        try:
            with self.assertRaises(sqlite3.OperationalError):c.execute('DELETE FROM team')
        finally:c.close()
    def test_write_refused_before_model(self):
        def bad(*a,**kw):raise AssertionError('Model must not be called')
        r=answer('بازی‌های لغو شده را پاک کن',planner=bad)
        self.assertEqual(r['action'],'refuse_write')
        self.assertFalse(r['database_executed'])
        self.assertIsNone(r['sql'])
    def test_model_classification_refusal(self):
        def mock(*a,**kw):return ({'action':'refuse_out_of_scope','intent':'fan_count','reason':'No fans table','sql':None}, {'status':'ok'})
        r=answer('Which team has the most fans?',planner=mock)
        self.assertEqual(r['action'],'refuse_out_of_scope')
        self.assertFalse(r['database_executed'])
    def test_gapgpt_sql_pipeline_join(self):
        def mock(*a,**kw):return ({'action':'answer_from_query','intent':'league_leader','sql':
            'SELECT t.name, COUNT(g.goal_id) AS goals FROM goal g JOIN team t ON t.team_id=g.scorer_team_id GROUP BY t.team_id LIMIT 2'}, {'status':'ok'})
        r=answer('Top scorers?',planner=mock)
        self.assertEqual(r['action'],'answer_from_query')
        self.assertTrue(r['database_executed'])
        self.assertIn('team',r['tables']);self.assertIn('goal',r['tables'])
    def test_model_generated_write_rejected_before_execution(self):
        def evil(*a,**kw):return ({'action':'answer_from_query','intent':'x','sql':'DELETE FROM team'}, {'status':'ok'})
        r=answer('Summarize a team',planner=evil,try_repair=False)
        self.assertEqual(r['validation'],'rejected');self.assertFalse(r['database_executed'])
    def test_clarification_no_sql(self):
        def mock(*a,**kw):return ({'action':'ask_clarifying_question','intent':'best_player','sql':None,'clarification':'By goals or minutes?'}, {'status':'ok'})
        r=answer('Who is best?',planner=mock)
        self.assertEqual(r['action'],'ask_clarifying_question')
        self.assertTrue(r['next_state'])
        self.assertFalse(r['database_executed'])
    def test_model_response_must_be_json(self):
        with self.assertRaises(ModelError):_extract('Sure, here is SQL: SELECT * FROM team')
    def test_row_limit(self):
        r=execute_readonly('SELECT * FROM player',row_limit=7)
        self.assertEqual(r['row_count'],7);self.assertTrue(r['truncated'])
    def test_no_candidate_sql_on_refusals(self):
        with self.assertRaises(ModelError):_extract('{"action":"refuse_write","sql":"SELECT * FROM team"}')

if __name__=='__main__':unittest.main()
