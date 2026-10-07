import unittest
from skeleton.security.tenant_isolation import TenantBoundary, TenantScope, authorize_tenant_access

class TestTenantIsolation(unittest.TestCase):
    def test_cross_tenant_and_cross_workspace_access_fail_closed(self):
        scope=TenantScope("t1","w1","s1","res:")
        ok=authorize_tenant_access(scope,TenantBoundary("res:1","t1","w1","internal"),operation="read")
        self.assertTrue(ok.allowed)
        tenant=authorize_tenant_access(scope,TenantBoundary("res:1","t2","w1","internal"),operation="read")
        workspace=authorize_tenant_access(scope,TenantBoundary("res:1","t1","w2","internal"),operation="read")
        self.assertEqual(tenant.reason_code,"tenant_mismatch")
        self.assertEqual(workspace.reason_code,"workspace_mismatch")

if __name__=="__main__": unittest.main()
