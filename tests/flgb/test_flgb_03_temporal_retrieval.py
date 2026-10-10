import unittest
from skeleton.ai.context.temporal_retrieval import TemporalRecord, temporal_retrieve
D="a"*64
class TestTemporalRetrieval(unittest.TestCase):
    def test_half_open_validity(self):
        records=(TemporalRecord("old",D,D,0,5),TemporalRecord("new",D,D,5,None))
        self.assertEqual([r.record_id for r in temporal_retrieve(records,4)],["old"])
        self.assertEqual([r.record_id for r in temporal_retrieve(records,5)],["new"])
if __name__=="__main__": unittest.main()
