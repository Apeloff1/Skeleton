"""Regression coverage for authenticated Mongo role inventory custody."""
from __future__ import annotations
import unittest
from skeleton.ai.runtime.inference.compose_activation import ActivationBlocked, _role_custody

class RoleInventoryCustodyTests(unittest.TestCase):
    def test_missing_inventory_fails_closed(self):
        with self.assertRaises(ActivationBlocked):
            _role_custody({"authInfo": {"authenticatedUsers": [{"db": "admin", "user": "operator"}]}})

    def test_explicit_empty_inventory_is_not_missing(self):
        self.assertEqual(_role_custody({"authInfo": {"authenticatedUserRoles": []}}), ())

    def test_null_inventory_fails_closed(self):
        with self.assertRaises(ActivationBlocked):
            _role_custody({"authInfo": {"authenticatedUserRoles": None}})

    def test_rotation_changes_snapshot(self):
        def inventory(role):
            return {"authInfo": {"authenticatedUserRoles": [{"db": "admin", "role": role}]}}
        self.assertNotEqual(_role_custody(inventory("read")), _role_custody(inventory("readWrite")))

if __name__ == "__main__":
    unittest.main()
