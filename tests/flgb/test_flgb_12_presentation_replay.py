import unittest
from skeleton.game.presentation.presentation_replay import PresentationContractError, PresentationFrame, PresentationReplay
D="a"*64
E="b"*64
class TestReplay(unittest.TestCase):
    def test_frame_sequence_is_strict(self):
        replay=PresentationReplay().append(D,D,D,D,D,E).append(E,E,E,E,E,D)
        self.assertEqual([f.frame_id for f in replay.frames],[0,1])
        with self.assertRaises(PresentationContractError):
            PresentationReplay((PresentationFrame(1,D,D,D,D,D,E),))
if __name__=="__main__": unittest.main()
