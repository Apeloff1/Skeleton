import unittest
from skeleton.game.presentation.spatial_audio import PresentationContractError, SpatialAudioSource
D="a"*64
class TestSpatialAudio(unittest.TestCase):
    def test_spatial_source_is_bounded(self):
        s=SpatialAudioSource("s",(1,2,3),1000,10000,D)
        self.assertEqual(s.max_distance,10000)
        with self.assertRaises(PresentationContractError):SpatialAudioSource("s",(1,2,3),1000,0,D)
if __name__=="__main__":unittest.main()
