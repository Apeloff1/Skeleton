import unittest
from skeleton.game.presentation.spatial_audio import SpatialEmitter
class TestSpatialAudio(unittest.TestCase):
    def test_integer_attenuation_is_bounded(self):
        emitter=SpatialEmitter("e",0,0,0,1000,10,110)
        self.assertEqual(emitter.attenuation_milli(10),1000)
        self.assertEqual(emitter.attenuation_milli(60),500)
        self.assertEqual(emitter.attenuation_milli(110),0)
if __name__=="__main__": unittest.main()
