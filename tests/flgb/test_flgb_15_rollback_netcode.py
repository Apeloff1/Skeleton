import unittest
from skeleton.game.platform.rollback_netcode import PlatformContractError, RollbackFrame, validate_rollback_chain
D="a"*64
class T(unittest.TestCase):
 def test_chain(self):
  a=RollbackFrame(0,D,D); b=RollbackFrame(1,D,D,a.digest); validate_rollback_chain((a,b))
  with self.assertRaises(PlatformContractError): validate_rollback_chain((b,))
if __name__=="__main__": unittest.main()
