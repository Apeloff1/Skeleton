import unittest
from skeleton.game.presentation.procedural_animation import PresentationContractError, ProceduralLayer, order_procedural_layers
D="a"*64
class TestProcedural(unittest.TestCase):
    def test_order_is_priority_then_identity(self):
        layers=(ProceduralLayer("b","ik",D,D,1),ProceduralLayer("a","look",D,D,1),ProceduralLayer("c","noise",D,D,2))
        self.assertEqual([x.layer_id for x in order_procedural_layers(layers)],["a","b","c"])
        with self.assertRaises(PresentationContractError): order_procedural_layers((layers[0],layers[0]))
if __name__=="__main__": unittest.main()
