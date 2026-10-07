import unittest
from skeleton.game.presentation.presentation_replay import PresentationContractError, append_presentation_frame
D="a"*64
E="b"*64
class TestPresentationReplay(unittest.TestCase):
    def test_frame_chain_is_append_only(self):
        frames=append_presentation_frame((),0,D,D,D,D)
        frames=append_presentation_frame(frames,1,E,D,D,E)
        self.assertEqual(frames[1].prior_frame_digest,frames[0].digest)
        with self.assertRaises(PresentationContractError):
            append_presentation_frame((frames[1],),2,D,D,D,D)
if __name__=="__main__":unittest.main()
