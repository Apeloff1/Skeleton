import unittest
from skeleton.security.authorization import AuthorizationRequest, authorize

class TestAuthorization(unittest.TestCase):
    def test_required_capabilities_must_be_subset(self):
        allowed=authorize(AuthorizationRequest("s","read","r",("read","write"),("read",)))
        denied=authorize(AuthorizationRequest("s","admin","r",("read","write"),("admin",)))
        self.assertTrue(allowed.allowed)
        self.assertFalse(denied.allowed)
        self.assertEqual(denied.reason,"capability-missing")

if __name__=="__main__": unittest.main()
