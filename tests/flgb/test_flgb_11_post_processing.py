import unittest
from skeleton.game.render.post_processing import PostEffect, RenderContractError, order_post_effects
D="a"*64

class TestPostProcessing(unittest.TestCase):
    def test_disabled_effects_are_omitted_and_order_is_stable(self):
        effects=(PostEffect("bloom",2,D),PostEffect("tone",1,D),PostEffect("debug",0,D,False))
        self.assertEqual([e.effect_id for e in order_post_effects(effects)],["tone","bloom"])
        with self.assertRaises(RenderContractError):
            order_post_effects((PostEffect("x",0,D),PostEffect("x",1,D)))

if __name__=="__main__": unittest.main()
