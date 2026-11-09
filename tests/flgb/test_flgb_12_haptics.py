import unittest
from skeleton.game.presentation.haptics import HapticPattern, HapticSegment, PresentationContractError

class TestHaptics(unittest.TestCase):
    def test_pattern_duration_and_intensity_are_bounded(self):
        pattern=HapticPattern("hit",(HapticSegment(50,1000000,500000),HapticSegment(25,0,250000)))
        self.assertEqual(pattern.total_duration_ms,75)
        self.assertEqual(len(pattern.digest),64)
        with self.assertRaises(PresentationContractError):
            HapticSegment(10,1000001,0)

if __name__=="__main__": unittest.main()
