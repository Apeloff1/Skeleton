import unittest
from skeleton.ai.multimodal.artifact_alignment import ArtifactAlignment, MultimodalContractError
D="a"*64
E="b"*64

class TestArtifactAlignment(unittest.TestCase):
    def test_alignment_requires_distinct_artifacts_and_evidence(self):
        item=ArtifactAlignment("a",D,E,"transcript-of",900000,D)
        self.assertEqual(item.relation,"transcript-of")
        with self.assertRaises(MultimodalContractError):
            ArtifactAlignment("a",D,D,"supports",1,D)

if __name__=="__main__": unittest.main()
