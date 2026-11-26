"""General answerability, no benchmark output shapes or gold SQL."""
import unittest
from app.pipeline import answer
from app.quality import reconsider_clarification

class ClarificationTests(unittest.TestCase):
    @staticmethod
    def diagnostic():
        return {'model':'mock','status':'ok','latency_ms':1}

    def test_concrete_metrics_reconsidered(self):
        self.assertTrue(reconsider_clarification('Count the substitutions for the selected club'))
        self.assertTrue(reconsider_clarification('What is the match result for these clubs?'))
        self.assertFalse(reconsider_clarification('Who is the most inspirational person?'))
        self.assertFalse(reconsider_clarification('Which person do you mean?'))
        self.assertFalse(reconsider_clarification('Which team has the highest ticket revenue?'))

    def test_one_second_look_can_resolve_a_real_count(self):
        def first(*a, **k):
            return ({'action':'ask_clarifying_question', 'intent':'need details', 'sql':None,
                     'clarification':'Which count?'},self.diagnostic())
        seen=[]
        def second(*a, **k):
            seen.append(k['feedback']['mode'])
            return ({'action':'answer_from_query', 'intent':'count recorded substitutions',
                     'sql':'SELECT COUNT(*) AS n FROM substitution'},self.diagnostic())
        r=answer('Count all substitutions',planner=first,reviewer=second)
        self.assertEqual(r['action'],'answer_from_query')
        self.assertTrue(r['database_executed'])
        self.assertEqual(seen[0],'clarification_necessity_check')

    def test_subjective_question_remains_clarification(self):
        def first(*a, **k):
            return ({'action':'ask_clarifying_question','intent':'unknown', 'sql':None,
                     'clarification':'By what criterion?'},self.diagnostic())
        def never(*a, **k):
            raise AssertionError('No reconsideration for subjective questions')
        r=answer('Who is the most inspirational person?',planner=first,reviewer=never)
        self.assertEqual(r['action'],'ask_clarifying_question')
        self.assertFalse(r['database_executed'])

    def test_review_maintains_readonly_policy(self):
        def first(*a, **k):
            return ({'action':'ask_clarifying_question','intent':'unknown','sql':None,
                     'clarification':'What count?'},self.diagnostic())
        def bad(*a, **k):
            return ({'action':'answer_from_query','intent':'unsafe',
                     'sql':'DROP TABLE substitution'},self.diagnostic())
        r=answer('Count substitutions',planner=first,reviewer=bad)
        self.assertFalse(r['database_executed'])
        self.assertIsNone(r['sql'])
        self.assertEqual(r['validation'],'rejected')

if __name__=='__main__':unittest.main()
