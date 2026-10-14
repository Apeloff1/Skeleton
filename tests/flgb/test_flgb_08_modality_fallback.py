import unittest
from skeleton.ai.multimodal.modality_fallback import FallbackOption, MultimodalContractError, choose_fallback

class TestModalityFallback(unittest.TestCase):
    def test_fallback_never_widens_authority(self):
        options=(FallbackOption("image","vision.read",True,900000),FallbackOption("text","text.read",True,800000))
        self.assertEqual(choose_fallback(options,("text.read",)).modality,"text")
        with self.assertRaises(MultimodalContractError):
            choose_fallback(options,("audio.read",))

if __name__=="__main__": unittest.main()
