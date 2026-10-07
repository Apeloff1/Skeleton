import unittest
from skeleton.ai.training.dataset_lineage import DatasetRevision
D="a"*64
E="b"*64

class TestDatasetLineage(unittest.TestCase):
    def test_revision_chain_is_explicit(self):
        base=DatasetRevision("d",0,D,D,D)
        nxt=base.revise(E,D,E)
        self.assertEqual(nxt.revision,1)
        self.assertEqual(nxt.parent_digest,base.digest)

if __name__=="__main__": unittest.main()
