import unittest
from skeleton.game.render.lighting_model import Light, order_lights
D="a"*64

class TestLighting(unittest.TestCase):
    def test_light_budget_is_deterministic(self):
        lights=(Light("b","point",100,10,D,True),Light("a","point",100,10,D,False),Light("c","point",50,10,D,False))
        self.assertEqual([l.light_id for l in order_lights(lights,2)],["a","b"])

if __name__=="__main__": unittest.main()
