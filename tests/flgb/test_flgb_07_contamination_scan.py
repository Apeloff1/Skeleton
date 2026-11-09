import unittest
from skeleton.ai.training.contamination_scan import scan_contamination
D="a"*64
E="b"*64
F="c"*64

class TestContamination(unittest.TestCase):
    def test_exact_overlap_is_reported(self):
        findings=scan_contamination((D,E),(E,F))
        self.assertEqual(len(findings),1)
        self.assertEqual(findings[0].dataset_item_digest,E)

if __name__=="__main__": unittest.main()
