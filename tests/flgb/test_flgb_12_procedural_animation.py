import unittest
from skeleton.game.presentation.procedural_animation import PresentationContractError, ProceduralModifier
D="a"*64
class TestProceduralAnimation(unittest.TestCase):
    def test_modifier_binds_seed_config_and_weight(self):
        m=ProceduralModifier("ik","foot_ik",D,7,500000)
        self.assertEqual(len(m.digest),64)
        with self.assertRaises(PresentationContractError):ProceduralModifier("ik","foot_ik",D,7,1000001)
if __name__=="__main__":unittest.main()
