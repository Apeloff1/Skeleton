import unittest
from skeleton.ai.context.hybrid_retrieval import RetrievalCandidate, hybrid_rank
D="a"*64
class TestHybridRetrieval(unittest.TestCase):
    def test_multi_signal_rank(self):
        a=RetrievalCandidate("a","mem",D,D,900000,100000,1000000)
        b=RetrievalCandidate("b","mem",D,D,100000,900000,1000000)
        ranked=hybrid_rank((a,b),lexical_weight=1,semantic_weight=2,freshness_weight=0)
        self.assertEqual(ranked[0].candidate_id,"b")
if __name__=="__main__": unittest.main()
