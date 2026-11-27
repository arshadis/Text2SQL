"""Independent regressions: provider identity and response fidelity.

No eval rows or canonical SQL are sent to the model. The same tests pass
against any database with the documented relations.
"""
from __future__ import annotations
import os
import unittest
from unittest.mock import patch
from app import llm, source_fingerprint, pipeline, normalizer
from app.db import execute_readonly
from app.semantic_checks import inspect


class ProviderVerification(unittest.TestCase):
    def test_default_is_official_gapgpt(self):
        with patch.dict(os.environ, {'GAPGPT_BASE_URL': 'https://api.gapgpt.app/v1'}):
            self.assertEqual(llm.configured_gapgpt_base(), 'https://api.gapgpt.app/v1')
    def test_prevent_secrets_leaking_to_foreign_hosts(self):
        for host in ('https://api.openai.com/v1',
                     'https://api.gapgpt.app.attacker.tld/v1',
                     'http://api.gapgpt.app/v1',
                     'https://api.gapgpt.app@attacker.tld/v1',
                     'https://api.gapgpt.app/v1?redirect=https://example.com'):
            with self.subTest(host=host), patch.dict(os.environ, {
                    'GAPGPT_BASE_URL':host, 'GAPGPT_API_KEY':'fake-not-a-real-key'}):
                with self.assertRaises(llm.ModelError):
                    llm.plan('Count teams',transport=lambda *_: self.fail('Provider request should not be sent'))
    def test_model_request_targets_gapgpt_chat_completions(self):
        import json
        observations=[]
        def pretend_transport(request):
            observations.append(request.full_url)
            body=json.loads(request.data.decode('utf-8'))
            self.assertEqual(body['model'],'gpt-4o-mini')
            payload={'choices':[{'message':{'content':json.dumps({
                'action':'ask_clarifying_question',
                'intent':'missing referent','sql':None,
                'clarification':'Which match?','reason':'Need match identity'
            })}}]}
            return payload,200
        with patch.dict(os.environ, {'GAPGPT_BASE_URL':'https://api.gapgpt.app/v1',
                                     'GAPGPT_API_KEY':'fake-not-a-real-key',
                                     'GAPGPT_MODEL':'gpt-4o-mini'}):
            result,diag=llm.plan('Which match?',transport=pretend_transport)
        self.assertEqual(result['action'],'ask_clarifying_question')
        self.assertEqual(observations,['https://api.gapgpt.app/v1/chat/completions'])
        self.assertEqual(diag['provider'],'GapGPT')
        self.assertEqual(diag['provider_base_url'],'https://api.gapgpt.app/v1')
        self.assertEqual(diag['http_status'],200)

    def test_runtime_digest_tracks_nonsecret_base_url(self):
        with patch.dict(os.environ, {'GAPGPT_BASE_URL':'https://api.gapgpt.app/v1'}):
            a=source_fingerprint.runtime_config_sha256()
        with patch.dict(os.environ, {'GAPGPT_BASE_URL':'https://another-provider.invalid/v1'}):
            b=source_fingerprint.runtime_config_sha256()
        self.assertNotEqual(a,b)


class ReportGroundedGeneralization(unittest.TestCase):
    def test_named_scorer_is_recognized_even_without_name_suffix(self):
        sql=('SELECT g.match_id, p.name_fa AS scorer, t.name AS benefiting_team '
             'FROM goal g JOIN player p ON p.player_id = g.player_id '
             'JOIN team t ON t.team_id = g.team_id WHERE g.is_own_goal = 1')
        data=execute_readonly(sql)
        issues=inspect('Show own-goal events: scorer and benefited club',sql,data)
        self.assertFalse(any('does not identify a named player' in x for x in issues),issues)

    def test_entity_sets_dedupe_when_a_subquery_contains_group_and_count(self):
        sql=('SELECT c.name_fa AS coach_name, t.name AS team_name '
             'FROM match_coach mc JOIN coach c ON c.coach_id=mc.coach_id '
             'JOIN team t ON t.team_id=mc.team_id '
             'WHERE mc.match_id IN (SELECT match_id FROM \"match\" WHERE round <= 3) '
             'AND mc.team_id IN (SELECT team_id FROM match_coach '
             'GROUP BY team_id HAVING COUNT(*) > 0)')
        data=execute_readonly(sql)
        self.assertGreater(data['row_count'], 25)
        candidate=normalizer.dedupe_entity_listing('Show the names of coaches and their teams',sql,data)
        self.assertTrue(candidate and candidate.startswith('SELECT DISTINCT '),candidate)
        after=execute_readonly(candidate)
        self.assertTrue(pipeline._verified_entity_set_dedupe(data,after))
        self.assertLess(after['row_count'],data['row_count'])

    def test_event_lists_not_deduped_even_with_duplicate_display_rows(self):
        sql=('SELECT c.name_fa AS coach_name, t.name AS team_name '
             'FROM match_coach mc JOIN coach c ON c.coach_id=mc.coach_id '
             'JOIN team t ON t.team_id=mc.team_id')
        data=execute_readonly(sql)
        self.assertIsNone(normalizer.dedupe_entity_listing(
            'Show the coaches and clubs for each match',sql,data))

    def test_id_projection_removal_preserves_observed_facts(self):
        sql=('SELECT p.player_id AS player_id, p.name_fa AS player_name '
             'FROM player p ORDER BY p.player_id LIMIT 10')
        before=execute_readonly(sql)
        candidate=normalizer.remove_unrequested_ids('Show ten player names',sql,before)
        self.assertIsNotNone(candidate)
        after=execute_readonly(candidate)
        self.assertTrue(pipeline._same_facts_after_projection(before,after))


if __name__=='__main__':unittest.main()
