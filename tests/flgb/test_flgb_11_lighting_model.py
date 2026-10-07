import unittest
from skeleton.game.render.lighting_model import Light, RenderContractError

class TestLighting(unittest.TestCase):
    def test_light_color_and_intensity_are_bounded(self):
        light=Light("sun","directional",1000,(1000,900,800),True)
        self.assertTrue(light.casts_shadow)
        with self.assertRaises(RenderContractError):
            Light("bad","point",1,(1001,0,0),False)

if __name__=="__main__": unittest.main()
