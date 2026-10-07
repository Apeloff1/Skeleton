import unittest
from skeleton.game.render.post_processing import PostProcessPass, post_process_order
D="a"*64

class TestPostProcessing(unittest.TestCase):
    def test_disabled_passes_are_not_promoted_to_frame_plan(self):
        passes=(PostProcessPass("tone","tonemap",D,True),PostProcessPass("debug","overlay",D,False))
        self.assertEqual([p.pass_id for p in post_process_order(passes)],["tone"])

if __name__=="__main__": unittest.main()
