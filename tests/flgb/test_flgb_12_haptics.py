import unittest
from skeleton.game.presentation.haptics import HapticPattern, HapticSegment, PresentationContractError
class TestHaptics(unittest.TestCase):
    def test_segments_do_not_overlap(self):
        p=HapticPattern("p",(HapticSegment(0,10,100,200),HapticSegment(10,10,0,300)))
        self.assertEqual(len(p.digest),64)
        with self.assertRaises(PresentationContractError):
            HapticPattern("bad",(HapticSegment(0,10,100,100),HapticSegment(5,10,100,100)))
if __name__=="__main__": unittest.main()
