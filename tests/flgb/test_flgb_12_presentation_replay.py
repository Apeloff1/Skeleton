import unittest
from skeleton.game.presentation.presentation_replay import PresentationContractError, PresentationFrame, PresentationReplay
D="a"*64
E="b"*64
F="c"*64

class TestPresentationReplay(unittest.TestCase):
    def test_frame_chain_binds_simulation_and_presentation(self):
        replay=PresentationReplay().append(0,D,D,D,D).append(1,E,E,E,E)
        self.assertEqual(replay.frames[1].prior_frame_digest,replay.frames[0].digest)
        self.assertEqual(len(replay.digest),64)
        with self.assertRaises(PresentationContractError):
            PresentationReplay((PresentationFrame(1,0,D,D,F,D),))

if __name__=="__main__": unittest.main()
