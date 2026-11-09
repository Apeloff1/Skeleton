import unittest
from skeleton.ai.multimodal.image_ingest import ImageArtifact, MultimodalContractError
D="a"*64

class TestImageIngest(unittest.TestCase):
    def test_image_identity_binds_rights_and_provenance(self):
        image=ImageArtifact("i",D,"image/png",1920,1080,1000,D,D)
        self.assertEqual(len(image.digest),64)
        with self.assertRaises(MultimodalContractError):
            ImageArtifact("i",D,"image/svg+xml",1,1,1,D,D)

if __name__=="__main__": unittest.main()
