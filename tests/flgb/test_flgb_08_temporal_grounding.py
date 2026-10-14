import unittest
from skeleton.ai.multimodal.temporal_grounding import MultimodalContractError, TemporalGrounding
D="a"*64

class TestTemporalGrounding(unittest.TestCase):
    def test_grounding_requires_nonempty_bounded_interval(self):
        item=TemporalGrounding("g",D,10,20,D,D)
        self.assertEqual(item.start_ms,10)
        with self.assertRaises(MultimodalContractError):
            TemporalGrounding("g",D,20,20,D,D)

if __name__=="__main__": unittest.main()
