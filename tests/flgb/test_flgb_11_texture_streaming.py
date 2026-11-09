import unittest
from skeleton.game.render.texture_streaming import TextureRequest, plan_texture_streaming
D="a"*64

class TestTextureStreaming(unittest.TestCase):
    def test_budget_prefers_priority_then_size(self):
        reqs=(TextureRequest("low",D,40,0,0,4),TextureRequest("high",D,70,2,0,4),TextureRequest("mid",D,30,1,0,4))
        self.assertEqual(plan_texture_streaming(reqs,100),("high","mid"))

if __name__=="__main__": unittest.main()
