"""Independent tests: no benchmark question IDs, gold SQL or expected rows."""
import unittest
from app.schema_evidence import explain_available_data
from app.pipeline import answer

class EvidenceTests(unittest.TestCase):
    @staticmethod
    def diag(): return {'status':'ok','latency_ms':1}

    def test_coach_observation_exists_without_change_log(self):
        evidence=explain_available_data('Can managers change during recorded fixtures?')
        observed={r['relation']:r for r in evidence['relations']}
        self.assertIn('match_coach',observed)
        self.assertIn('match_id',observed['match_coach']['columns'])
        self.assertGreater(observed['match_coach']['observations'],0)

    def test_formation_columns_exist(self):
        evidence=explain_available_data('Which starting formations were recorded in matches?')
        match=next(r for r in evidence['relations'] if r['relation']=='match')
        self.assertGreater(next(x for x in match['field_statistics'] if x['column']=='home_formation')['non_null'],0)

    def test_revenue_has_no_schema_evidence(self):
        self.assertFalse(explain_available_data('What is revenue from tickets?')['relations'])

    def test_grounded_second_refusal_check(self):
        first={'action':'refuse_out_of_scope','intent':'manager count','sql':None,'reason':'No manager data'}
        def plan(*a,**kw): return first,self.diag()
        modes=[]
        def reviewer(*a,**kw):
            mode=kw['feedback']['mode'];modes.append(mode)
            if mode=='reconsider_out_of_scope': return first,self.diag()
            if mode=='schema_evidence_answerability_check':
                self.assertIn('match_coach',{r['relation'] for r in kw['feedback']['readonly_schema_evidence']['relations']})
            return {'action':'answer_from_query','intent':'count recorded managers',
                    'sql':'SELECT COUNT(DISTINCT coach_id) AS n FROM match_coach'},self.diag()
        response=answer('How many coaches appeared across recorded fixtures?',planner=plan,reviewer=reviewer)
        self.assertEqual(response['action'],'answer_from_query')
        self.assertIn('schema_evidence_answerability_check',modes)
        self.assertTrue(response['database_executed'])

    def test_grounded_second_clarification_check(self):
        initial={'action':'ask_clarifying_question','intent':'formation variety','sql':None,
                 'clarification':'Which fixtures?'}
        def plan(*a,**kw):return initial,self.diag()
        modes=[]
        def reviewer(*a,**kw):
            mode=kw['feedback']['mode'];modes.append(mode)
            if mode=='clarification_necessity_check': return initial,self.diag()
            if mode=='schema_evidence_clarification_check':
                self.assertIn('match',{r['relation'] for r in kw['feedback']['readonly_schema_evidence']['relations']})
            return {'action':'answer_from_query','intent':'formation variety',
                    'sql':'SELECT COUNT(DISTINCT home_formation) AS n FROM "match"'},self.diag()
        response=answer('How many starting formations are recorded?',planner=plan,reviewer=reviewer)
        self.assertEqual(response['action'],'answer_from_query')
        self.assertIn('schema_evidence_clarification_check',modes)

    def test_no_guessing_missing_referent(self):
        initial={'action':'ask_clarifying_question','intent':'unknown',
                 'sql':None,'clarification':'Which person?'}
        def plan(*a,**kw):return initial,self.diag()
        def reviewer(*a,**kw):raise AssertionError('Must not force a missing referent')
        self.assertEqual(answer('Which person is better?',planner=plan,reviewer=reviewer)['action'],
                         'ask_clarifying_question')

    def test_goalkeeper_team_role_warning(self):
        from app.semantic_checks import inspect
        question='Show keeper clean sheets when their own club conceded zero'
        columns={'columns':['player_id','n'],'rows':[[9,4]],'row_count':1}
        bad='SELECT l.player_id, COUNT(*) AS n FROM lineup l JOIN "match" m ON m.match_id=l.match_id WHERE l.position=\'GK\' AND l.is_starter=1 AND m.home_goals=0 GROUP BY l.player_id'
        good='SELECT l.player_id, COUNT(*) AS n FROM lineup l JOIN "match" m ON m.match_id=l.match_id WHERE l.position=\'GK\' AND l.is_starter=1 AND ((l.team_id=m.home_team_id AND m.away_goals=0) OR (l.team_id=m.away_team_id AND m.home_goals=0)) GROUP BY l.player_id'
        self.assertTrue(any('SAME team' in x for x in inspect(question,bad,columns)))
        self.assertFalse(any('SAME team' in x for x in inspect(question,good,columns)))

    def test_persian_units(self):
        from app.narrative import summarize
        self.assertIn('تصمیم VAR',summarize({'columns':['var_decision_count'],'rows':[[39]],'row_count':1}))
        text=summarize({'columns':['stadium_name','match_count'],
                        'rows':[['ورزشگاه الف',3],['ورزشگاه ب',2]],'row_count':2})
        self.assertIn('۳ بازی',text)
        self.assertNotIn('match count',text)

if __name__=='__main__':unittest.main()
