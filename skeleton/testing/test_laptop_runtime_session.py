"""Offline laptop runtime qualification: session; test-double only, not real native E2E."""
import unittest
from skeleton.testing.laptop_runtime_test_support import FakeWorker
from skeleton.ai.runtime.operational_ai.laptop_runtime.session_adapter import create,close,get_history
from skeleton.ai.runtime.operational_ai.laptop_runtime.contracts import ContractViolation
class TestSession(unittest.TestCase):
    def test_session_names_are_server_generated_and_distinct(self):
        fake=FakeWorker()
        left=create(fake);right=create(fake)
        self.assertNotEqual(left,right)
        self.assertTrue(left.startswith("s_"))
        self.assertTrue(right.startswith("s_"))
        self.assertEqual(len(get_history(fake,left)),1)
        self.assertTrue(close(fake,left))
        self.assertFalse(close(fake,left))
    def test_missing_session_never_implicitly_created(self):
        fake=FakeWorker()
        with self.assertRaises(ValueError):get_history(fake,"missing")
        self.assertEqual(len(fake.spine.created),0)

if __name__=="__main__":
    unittest.main()
