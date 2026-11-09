import unittest
from skeleton.game.build.release_artifact_verification import ReleaseArtifact, verify_release_artifact
D="a"*64
class T(unittest.TestCase):
 def test_signature_required(self):
  self.assertTrue(verify_release_artifact(ReleaseArtifact(D,D,D,D,D)))
  self.assertFalse(verify_release_artifact(ReleaseArtifact(D,D,None,D,D)))
if __name__=="__main__": unittest.main()
