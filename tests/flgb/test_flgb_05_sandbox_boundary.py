import unittest
from skeleton.security.sandbox_boundary import SandboxBoundary, SecurityPlaneError

class TestSandboxBoundary(unittest.TestCase):
    def test_write_scope_and_traversal_fail_closed(self):
        boundary=SandboxBoundary("b",("/workspace",),"deny",False)
        self.assertTrue(boundary.allows_path("/workspace/file.txt"))
        self.assertFalse(boundary.allows_path("/other/file.txt"))
        with self.assertRaises(SecurityPlaneError):
            boundary.allows_path("/workspace/../etc/passwd")

if __name__=="__main__": unittest.main()
