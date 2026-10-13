import unittest

from skeleton.security.tenant_isolation import (
    TenantBoundary, TenantIsolationError, TenantScope, authorize_tenant_access,
)


class TestTenantIsolation(unittest.TestCase):
    def test_cross_tenant_and_cross_workspace_access_fail_closed(self):
        scope = TenantScope("t1", "w1", "s1", "t1:w1:res:")
        allowed = authorize_tenant_access(
            scope, TenantBoundary("t1:w1:res:1", "t1", "w1", "internal"),
            operation="read",
        )
        self.assertTrue(allowed.allowed)
        tenant = authorize_tenant_access(
            scope, TenantBoundary("t1:w1:res:1", "t2", "w1", "internal"),
            operation="read",
        )
        workspace = authorize_tenant_access(
            scope, TenantBoundary("t1:w1:res:1", "t1", "w2", "internal"),
            operation="read",
        )
        foreign_key = authorize_tenant_access(
            scope, TenantBoundary("t2:w1:res:1", "t1", "w1", "internal"),
            operation="read",
        )
        self.assertEqual(tenant.reason_code, "tenant_mismatch")
        self.assertEqual(workspace.reason_code, "workspace_mismatch")
        self.assertEqual(foreign_key.reason_code, "resource_scope_mismatch")
        self.assertFalse(foreign_key.allowed)

    def test_legacy_unscoped_resource_prefix_cannot_grant_authority(self):
        with self.assertRaisesRegex(
            TenantIsolationError, "exact tenant/workspace authority"
        ):
            TenantScope("t1", "w1", "s1", "res:")


if __name__ == "__main__":
    unittest.main()

