import unittest
from skeleton.game.presentation.spatial_audio import SpatialSource

class TestSpatialAudio(unittest.TestCase):
    def test_attenuation_is_integer_and_bounded(self):
        source=SpatialSource("s",0,0,0,1000000,10)
        self.assertEqual(source.attenuated_gain((0,0,0)),1000000)
        self.assertEqual(source.attenuated_gain((10,0,0)),0)
        self.assertGreater(source.attenuated_gain((5,0,0)),0)

if __name__=="__main__": unittest.main()
