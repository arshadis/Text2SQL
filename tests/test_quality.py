"""Offline regression tests: the quality loop must never bypass SQLite safety."""
import unittest
from app.pipeline import answer
from app.quality import reconsider_refusal, review_feedback

class QualityReviewTests(unittest.TestCase):
    @staticmethod
    def _diag():
        return {'provider':'mock','model':'unit','status':'ok','http_status':200,'latency_ms':1}

    def test_catches_semantically_wrong_but_valid_count(self):
        wrong = '''SELECT COUNT(*) AS played FROM "match" WHERE status IN ('finished','awarded')'''
        right = '''SELECT COUNT(*) AS played FROM "match" WHERE status='finished' '''
        def planner(*_, **kw):
            return ({'action':'answer_from_query','intent':'count_played','sql':wrong},self._diag())
        seen=[]
        def reviewer(*_,**kw):
            self.assertEqual(kw['feedback']['candidate_sql'],wrong)
            self.assertEqual(kw['feedback']['database_sample_rows'],[[96]])
            seen.append('called')
            return ({'action':'answer_from_query','intent':'count_played','sql':right},self._diag())
        result=answer('How many matches have been played?', planner=planner,reviewer=reviewer)
        self.assertEqual(result['rows'],[[95]])
        self.assertEqual(result['quality_review'],'adopted')
        self.assertEqual(len(seen),1)
        self.assertTrue(result['database_executed'])

    def test_generated_write_in_second_pass_is_rejected_without_execution(self):
        sql='SELECT COUNT(*) FROM team'
        def planner(*_,**kw):
            return ({'action':'answer_from_query','intent':'count_teams','sql':sql},self._diag())
        def reviewer(*_,**kw):
            return ({'action':'answer_from_query','intent':'bad','sql':'DELETE FROM team'},self._diag())
        result=answer('How many teams?',planner=planner,reviewer=reviewer)
        self.assertEqual(result['rows'],[[18]])
        self.assertEqual(result['sql'],sql)
        self.assertEqual(result['quality_review'],'rejected_revision')

    def test_recorded_coaches_can_be_derived_from_match_coach(self):
        def planner(*_,**kw):
            return ({'action':'refuse_out_of_scope','intent':'coach','sql':None,'reason':'No history table'},self._diag())
        def reviewer(*_,**kw):
            return ({'action':'answer_from_query','intent':'recorded_coaches',
                     'sql':'SELECT COUNT(DISTINCT coach_id) AS coaches FROM match_coach'},self._diag())
        result=answer('How many different coaches are recorded?',planner=planner,reviewer=reviewer)
        self.assertEqual(result['action'],'answer_from_query')
        self.assertEqual(result['validation'],'passed')
        self.assertGreater(result['rows'][0][0],0)

    def test_fans_remain_out_of_scope_and_not_reconsidered(self):
        def planner(*_,**kw):
            return ({'action':'refuse_out_of_scope','intent':'fans','sql':None,'reason':'Not measured'},self._diag())
        def reviewer(*_,**kw):
            raise AssertionError('Unsupported concept must not trigger review')
        result=answer('Which team has most fans?',planner=planner,reviewer=reviewer)
        self.assertEqual(result['action'],'refuse_out_of_scope')
        self.assertIsNone(result['sql'])
        self.assertFalse(result['database_executed'])

    def test_feedback_uses_live_rows_not_gold(self):
        f=review_feedback('Which player scored most?', 'SELECT name_fa FROM player LIMIT 1',
                          {'columns':['name_fa'],'row_count':1,'rows':[['پرسپولیس']], 'truncated':False})
        self.assertEqual(f['database_sample_rows'],[['پرسپولیس']])
        self.assertNotIn('expected_rows',repr(f))
        self.assertNotIn('gold_sql',repr(f))

    def test_supported_scope_detection(self):
        self.assertTrue(reconsider_refusal('Which coach managed most matches?'))
        self.assertFalse(reconsider_refusal('How many spectators attended?'))

if __name__=='__main__':unittest.main()
