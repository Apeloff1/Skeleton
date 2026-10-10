import unittest
from skeleton.ai.assurance.drift_detection import DriftSignal

class TestDriftDetection(unittest.TestCase):
    def test_threshold_is_strict(self):
        self.assertFalse(DriftSignal("m",500000,550000,50000).drifted)
        self.assertTrue(DriftSignal("m",500000,550001,50000).drifted)

if __name__=="__main__": unittest.main()
