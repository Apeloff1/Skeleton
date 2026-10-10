import unittest
from skeleton.game.presentation.procedural_animation import PresentationContractError, ProceduralLayer
D="a"*64

class TestProceduralAnimation(unittest.TestCase):
    def test_seed_input_and_weight_are_receipted(self):
        layer=ProceduralLayer("look-at","ik",D,D,D,500000)
        self.assertEqual(len(layer.digest),64)
        with self.assertRaises(PresentationContractError):
            ProceduralLayer("bad","ik",D,D,D,1000001)

if __name__=="__main__": unittest.main()
