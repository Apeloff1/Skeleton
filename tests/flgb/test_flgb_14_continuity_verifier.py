import unittest
from skeleton.game.generation.continuity_verifier import ContinuityObservation
D="a"*64

class TestContinuityVerifier(unittest.TestCase):
    def test_any_violation_marks_observation_unclean(self):
        clean=ContinuityObservation("ok",(),(),(),D)
        broken=ContinuityObservation("bad",("canon-1",),(),("style-2",),D)
        self.assertTrue(clean.clean)
        self.assertFalse(broken.clean)
        self.assertEqual(len(broken.digest),64)

if __name__=="__main__": unittest.main()
