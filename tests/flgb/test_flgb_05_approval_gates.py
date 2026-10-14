import unittest
from skeleton.security.approval_gates import ApprovalGate, SecurityPlaneError, approval_satisfied

class TestApprovalGates(unittest.TestCase):
    def test_distinct_authorized_approvers_required(self):
        gate=ApprovalGate("g","release",2,("security","owner"))
        self.assertTrue(approval_satisfied(gate,(("a","security"),("b","owner"))))
        self.assertFalse(approval_satisfied(gate,(("a","security"),)))
        with self.assertRaises(SecurityPlaneError):
            approval_satisfied(gate,(("a","security"),("a","owner")))

if __name__=="__main__": unittest.main()
