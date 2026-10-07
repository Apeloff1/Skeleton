import unittest
from skeleton.ai.multimodal.cross_modal_retrieval import CrossModalCandidate, rank_cross_modal
D="a"*64

class TestCrossModalRetrieval(unittest.TestCase):
    def test_semantic_signal_dominates_deterministically(self):
        a=CrossModalCandidate("a","image",D,D,900000,100000)
        b=CrossModalCandidate("b","audio",D,D,500000,1000000)
        self.assertEqual(rank_cross_modal((b,a))[0].candidate_id,"a")

if __name__=="__main__": unittest.main()
