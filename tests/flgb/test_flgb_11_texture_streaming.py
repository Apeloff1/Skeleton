import unittest
from skeleton.game.render.texture_streaming import RenderContractError, TextureMip, texture_residency
D="a"*64

class TestTextureStreaming(unittest.TestCase):
    def test_residency_obeys_budget_and_unique_mips(self):
        mips=(TextureMip(0,D,100),TextureMip(1,D,40),TextureMip(2,D,10))
        self.assertEqual(texture_residency(mips,50),(1,2))
        with self.assertRaises(RenderContractError):
            texture_residency((TextureMip(1,D,10),TextureMip(1,D,10)),100)

if __name__=="__main__": unittest.main()
