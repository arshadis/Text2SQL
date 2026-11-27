"""Domain-grounded counterexample tests for SQL validation.

The queries are independent counterexamples, not reference solutions for
benchmark questions. No expected benchmark rows are imported or supplied to
an LLM. Tests operate against the actual read-only football SQLite snapshot.
"""
from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from app.context_compiler import compiled_context
from app.db import execute_readonly
from app.query_plan import derive_query_plan
from app.semantic_checks import inspect


SCORER_QUESTION='Which starting goalkeepers kept clean sheets for their clubs?'
VALID_SQL='''SELECT p.name_fa AS keeper, t.name AS team, COUNT(*) AS clean_sheets
    FROM lineup AS l
    JOIN v_team_match AS side ON side.match_id=l.match_id AND side.team_id=l.team_id
    JOIN player AS p ON p.player_id=l.player_id
    JOIN team AS t ON t.team_id=l.team_id
    WHERE l.is_starter=1 AND l.position='GK' AND side.goals_against=0
    GROUP BY l.player_id,l.team_id ORDER BY clean_sheets DESC,p.name_fa'''


class SemanticContextTests(unittest.TestCase):
    def test_scoped_context_keeps_real_dictionary(self):
        context=compiled_context('Count goalkeeper clean sheets by club')
        self.assertIn('lineup',context)
        self.assertIn('goalkeeper',context.casefold())
        self.assertIn('Join `v_team_match` to `lineup` on **both**',context)
        self.assertIn('Read-only SQL',context)
        self.assertNotIn('expected_rows',context)
        self.assertNotIn('eval_questions.json',context)

    def test_scorer_club_vs_credited_team_documented(self):
        context=compiled_context('Which footballers scored own goals?')
        self.assertIn('scorer_team_id',context)
        self.assertIn('credited',context.casefold())

    def test_context_retains_selected_ddl(self):
        context=compiled_context('Which goalkeepers have clean sheets?')
        self.assertIn('CREATE TABLE lineup',context)
        self.assertIn('CREATE VIEW v_team_match',context)

    def test_rank_k_unset_when_user_does_not_name_k(self):
        self.assertIsNone(derive_query_plan('Which keepers recorded the most shutouts?').requested_top_n)
        self.assertEqual(derive_query_plan('Top 6 goalkeepers by clean sheets').requested_top_n,6)


class GoalkeeperRoleTests(unittest.TestCase):
    def _warnings(self,sql,question=SCORER_QUESTION):
        return inspect(question,sql,execute_readonly(sql))

    def test_valid_join_avoids_role_warnings(self):
        data=execute_readonly(VALID_SQL)
        self.assertTrue(data['rows'])
        issues=self._warnings(VALID_SQL)
        self.assertFalse(any('goalkeeper position' in w or 'clean sheet reports' in w.lower()
                             or 'BOTH match_id' in w or 'goals_against' in w for w in issues),issues)

    def test_generic_lineup_players_are_not_goalkeepers(self):
        bad=VALID_SQL.replace("l.is_starter=1 AND l.position='GK' AND ",'')
        warnings=self._warnings(bad)
        self.assertTrue(any('goalkeeper position' in w for w in warnings),warnings)

    def test_join_only_on_match_duplicates_team_sides(self):
        bad=VALID_SQL.replace(' AND side.team_id=l.team_id','')
        warnings=self._warnings(bad)
        self.assertTrue(any('BOTH match_id and team_id' in w for w in warnings),warnings)

    def test_zero_on_other_side_is_not_clean_sheet(self):
        bad=VALID_SQL.replace('side.goals_against=0','side.goals_for=0')
        warnings=self._warnings(bad)
        self.assertTrue(any('goals_against=0' in w for w in warnings),warnings)

    def test_no_lineup_cannot_claim_starting_keeper(self):
        sql=('SELECT p.name_fa AS player_name, COUNT(*) AS clean_sheets '
             'FROM player p JOIN goal g ON g.player_id=p.player_id '
             'GROUP BY p.player_id')
        warnings=self._warnings(sql)
        self.assertTrue(any('recorded lineup' in w for w in warnings),warnings)

    def test_persian_paraphrase_flags_missing_keeper_position(self):
        bad=VALID_SQL.replace("l.is_starter=1 AND l.position='GK' AND ",'')
        issues=self._warnings(bad,'دروازه‌بان‌های فیکس کدام تیم‌ها بیشترین کلین‌شیت را دارند؟')
        self.assertTrue(any('goalkeeper position' in w for w in issues),issues)


if __name__=='__main__':unittest.main()

class EventRoleTests(unittest.TestCase):
    def test_venue_count_does_not_count_scheduled_fixtures(self):
        q='How many games were played at each registered stadium?'
        bad=('SELECT s.name_fa AS stadium_name, COUNT(m.match_id) AS games '
             'FROM stadium s LEFT JOIN "match" m ON m.stadium_id=s.stadium_id '
             'GROUP BY s.stadium_id')
        good=('SELECT s.name_fa AS stadium_name, COUNT(m.match_id) AS games '
              'FROM stadium s LEFT JOIN "match" m '
              "ON m.stadium_id=s.stadium_id AND m.status='finished' "
              'GROUP BY s.stadium_id')
        self.assertTrue(any('stadium' in w and 'scheduled' in w
                            for w in inspect(q,bad,execute_readonly(bad))))
        self.assertFalse(any('count of games played at a stadium' in w.lower()
                             for w in inspect(q,good,execute_readonly(good))))

    def test_explicit_scheduled_stadium_count_not_forced_finished(self):
        q='How many scheduled fixtures are assigned to each stadium?'
        sql=('SELECT s.name_fa, COUNT(m.match_id) AS scheduled_games '
             'FROM stadium s LEFT JOIN "match" m ON m.stadium_id=s.stadium_id '
             'GROUP BY s.stadium_id')
        issues=inspect(q,sql,execute_readonly(sql))
        self.assertFalse(any('games played at a stadium' in w for w in issues),issues)

    def test_own_goal_listing_requires_own_goal_event_flag(self):
        q='List all own goal events with the scorer and the beneficiary club'
        bad=('SELECT p.name_fa AS scorer, t.name AS beneficiary '
             'FROM goal g JOIN player p ON p.player_id=g.player_id '
             'JOIN team t ON t.team_id=g.team_id')
        good=bad+ ' WHERE g.is_own_goal=1'
        self.assertTrue(any('is_own_goal=1' in w for w in inspect(q,bad,execute_readonly(bad))))
        self.assertFalse(any('is_own_goal=1' in w for w in inspect(q,good,execute_readonly(good))))


class EvidenceOnlyAuditTests(unittest.TestCase):
    def test_audit_ignores_gold_data(self):
        from scripts.audit_live_semantics import audit_cases
        case={'question':'Which starting goalkeepers had clean sheets?',
              'pass':True, 'expected_rows':[['invented fake answer']],
              'action':'answer_from_query','sql':VALID_SQL,
              'rows':execute_readonly(VALID_SQL)['rows'],
              'columns':execute_readonly(VALID_SQL)['columns']}
        result=audit_cases([case])[0]
        self.assertNotIn('invented fake answer',str(result))
        self.assertEqual(result['action'],'answer_from_query')
        self.assertEqual(result['status'],'no_obvious_contradiction')
