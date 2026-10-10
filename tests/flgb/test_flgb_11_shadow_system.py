import unittest
from skeleton.game.render.shadow_system import RenderContractError, ShadowRequest, plan_shadows

class TestShadowSystem(unittest.TestCase):
    def test_budget_and_power_of_two_resolution(self):
        high=ShadowRequest("sun",1024,2,10)
        low=ShadowRequest("lamp",512,1,1)
        self.assertEqual(plan_shadows((low,high),high.texel_cost),("sun",))
        with self.assertRaises(RenderContractError):
            ShadowRequest("bad",1000,1,1)

if __name__=="__main__": unittest.main()
