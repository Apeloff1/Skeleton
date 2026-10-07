import unittest
from skeleton.ai.training.deduplication import DedupRecord, TrainingContractError, deduplicate
D="a"*64
E="b"*64

class TestDeduplication(unittest.TestCase):
    def test_fingerprint_dedup_is_deterministic(self):
        records=(DedupRecord("b",D,E),DedupRecord("a",D,D),DedupRecord("c",E,E))
        self.assertEqual([x.item_id for x in deduplicate(records)],["a","c"])
        with self.assertRaises(TrainingContractError):
            deduplicate((DedupRecord("a",D,D),DedupRecord("a",E,E)))

if __name__=="__main__": unittest.main()
