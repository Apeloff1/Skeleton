import unittest
from skeleton.game.platform.cloud_save import CloudSaveRevision, PlatformContractError
D="a"*64
class T(unittest.TestCase):
 def test_revision_requires_parent(self):
  base=CloudSaveRevision("slot",0,D,"dev")
  self.assertEqual(len(base.digest),64)
  with self.assertRaises(PlatformContractError): CloudSaveRevision("slot",1,D,"dev")
if __name__=="__main__": unittest.main()
