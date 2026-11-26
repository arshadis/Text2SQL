"""Independent behavioral checks: no gold queries, no expected benchmark rows."""
from __future__ import annotations
import unittest
from app.contract import diagnostics
from app.semantic_checks import inspect
from app.pipeline import answer


class SemanticsFromQuestions(unittest.TestCase):
    def test_model_config_provenance_never_contains_keys(self):
        from app.source_fingerprint import runtime_config_sha256
        from unittest.mock import patch
        with patch.dict('os.environ',{'GAPGPT_API_KEY':'secret-value','GAPGPT_MODEL':'model-alpha'}):
            a=runtime_config_sha256()
        with patch.dict('os.environ',{'GAPGPT_API_KEY':'another-secret','GAPGPT_MODEL':'model-alpha'}):
            self.assertEqual(a,runtime_config_sha256())
        with patch.dict('os.environ',{'GAPGPT_API_KEY':'secret-value','GAPGPT_MODEL':'model-beta'}):
            self.assertNotEqual(a,runtime_config_sha256())

    def test_completed_fixture_is_not_an_admin_award(self):
        data={'columns':['fixtures'],'rows':[[42]],'row_count':1,'truncated':False}
        incomplete='SELECT COUNT(*) AS fixtures FROM "match" WHERE status IN (\'finished\',\'awarded\')'
        self.assertTrue(any('played fixtures' in x or 'awarded records' in x
                            for x in diagnostics('How many fixtures were completed?',incomplete,data)))
        correct='SELECT COUNT(*) AS fixtures FROM "match" WHERE status=\'finished\''
        self.assertFalse(any('played fixtures' in x or 'awarded records' in x
                             for x in diagnostics('How many fixtures were completed?',correct,data)))

    def test_duplicated_team_side_rows_not_counted_as_unique_matches(self):
        data={'columns':['n'],'rows':[[10]],'row_count':1}
        wrong='SELECT COUNT(*) AS n FROM v_team_match'
        self.assertTrue(any('two-sided' in x for x in inspect('How many matches are in the league?',wrong,data)))
        good='SELECT COUNT(DISTINCT match_id) AS n FROM v_team_match'
        self.assertFalse(any('two-sided' in x for x in inspect('How many matches are in the league?',good,data)))

    def test_all_records_not_truncated_to_one(self):
        issue=inspect('List all venues', 'SELECT name FROM stadium LIMIT 1',
                      {'columns':['name'], 'row_count':1})
        self.assertTrue(any('all matching' in x for x in issue))

    def test_only_explicit_n_can_create_fixed_limit(self):
        from app.contract import infer_contract
        self.assertIsNone(infer_contract('Which coaches managed the most games?').target_rows)
        self.assertIsNone(infer_contract('Rank the clubs by total wins').target_rows)
        self.assertEqual(infer_contract('Top 6 teams by points').target_rows,6)
        issue=inspect('Top 6 teams by points','SELECT name FROM team LIMIT 2',
                      {'columns':['name'], 'row_count':2},explicit_limit=6)
        self.assertTrue(any('explicitly requested' in x for x in issue))

    def test_identifiers_are_not_fan_facing_names(self):
        data={'columns':['player_id','n'], 'rows':[[33,2]],'row_count':1}
        self.assertTrue(any('internal' in x for x in inspect('Which players appeared?',
                          'SELECT player_id, COUNT(*) AS n FROM lineup GROUP BY player_id',data)))
        self.assertFalse(inspect('Show player identifiers','SELECT player_id FROM player',data))

    def test_no_fake_readonly_writes_or_gold_keys(self):
        from app import semantic_checks
        from pathlib import Path
        content=Path(semantic_checks.__file__).read_text(encoding='utf-8')
        for forbidden in ('eval_questions', 'gold_sql', 'expected_rows', 'q01', 'q10', 'LIMIT 5'):
            self.assertNotIn(forbidden, content)


class ReviewDecisionIsQuestionGrounded(unittest.TestCase):
    @staticmethod
    def diag():return {'status':'ok','latency_ms':1}

    def test_revision_correcting_status_is_adopted(self):
        def candidate(*a,**kw):
            return ({'action':'answer_from_query','intent':'count completed fixtures',
                     'sql':"SELECT COUNT(*) AS n FROM \"match\" WHERE status IN ('finished','awarded')"}, self.diag())
        def reviewer(*a,**kw):
            return ({'action':'answer_from_query','intent':'count completed fixtures',
                     'sql':"SELECT COUNT(*) AS n FROM \"match\" WHERE status='finished'"}, self.diag())
        response=answer('How many fixtures were completed?',planner=candidate,reviewer=reviewer)
        self.assertEqual(response['action'],'answer_from_query')
        self.assertEqual(response['quality_review'],'adopted')
        self.assertTrue(response['review_evidence'])
        self.assertEqual(response['review_evidence'][0]['introduced_semantic_issues'],[])

    def test_revision_introducing_inconsistency_is_rejected(self):
        def candidate(*a,**kw):
            return ({'action':'answer_from_query','intent':'count completed fixtures',
                     'sql':"SELECT COUNT(*) AS n FROM \"match\" WHERE status='finished'"}, self.diag())
        def reviewer(*a,**kw):
            return ({'action':'answer_from_query','intent':'count fixtures',
                     'sql':"SELECT COUNT(*) AS n FROM \"match\" WHERE status IN ('finished','awarded')"}, self.diag())
        response=answer('How many fixtures were completed?',planner=candidate,reviewer=reviewer)
        self.assertEqual(response['action'],'answer_from_query')
        self.assertEqual(response['quality_review'],'rejected_regression')
        self.assertTrue(response['review_evidence'][0]['introduced_semantic_issues'])
        self.assertIn("status='finished'",response['sql'])

if __name__=='__main__':unittest.main()
