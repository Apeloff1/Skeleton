import unittest
from skeleton.ai.context.code_retrieval import CodeHit, ContextContractError, rank_code_hits
D="a"*64
class TestCodeRetrieval(unittest.TestCase):
    def test_repo_relative_and_stable_rank(self):
        hits=(CodeHit("a.py","x",D,D,1,2,500000),CodeHit("b.py","y",D,D,1,1,900000))
        self.assertEqual(rank_code_hits(hits)[0].path,"b.py")
        with self.assertRaises(ContextContractError): CodeHit("../x.py","x",D,D,1,1,1)
if __name__=="__main__": unittest.main()
