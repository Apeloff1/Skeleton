"""Mongo role custody is an observation, never an authorization grant."""
import unittest

from skeleton.ai.runtime.inference.compose_activation import (
    ActivationBlocked, _role_custody,
)


class MongoRoleCustodyTests(unittest.TestCase):
    def test_missing_role_inventory_fails_closed(self):
        for auth in ({"authInfo": {}}, {"authInfo": {"authenticatedUserRoles": None}}, {}):
            with self.subTest(auth=auth), self.assertRaisesRegex(ActivationBlocked, "role custody"):
                _role_custody(auth)

    def test_explicit_empty_role_inventory_is_not_missing(self):
        self.assertEqual(_role_custody({"authInfo": {"authenticatedUserRoles": []}}), ())

    def test_order_independent_role_identity(self):
        roles = [{"db": "admin", "role": "read"}, {"db": "local", "role": "write"}]
        left = _role_custody({"authInfo": {"authenticatedUserRoles": roles}})
        right = _role_custody({"authInfo": {"authenticatedUserRoles": list(reversed(roles))}})
        self.assertEqual(left, right)
        self.assertNotEqual(left, _role_custody({"authInfo": {
            "authenticatedUserRoles": [{"db": "admin", "role": "read"}]}))

    def test_explicit_null_and_duplicates_fail_closed(self):
        for roles in (None, {}, [None], [{"db": "admin", "role": "read"}] * 2):
            with self.subTest(roles=roles), self.assertRaises(ActivationBlocked):
                _role_custody({"authInfo": {"authenticatedUserRoles": roles}})

    def test_malformed_role_identifiers_fail_closed(self):
        for role in (
            {"db": "admin", "role": ""},
            {"db": "admin", "role": "read\\nwrite"},
            {"db": "admin", "role": "réad"},
            {"db": "admin", "role": 3},
            {"db": "admin", "role": "x" * 129},
            {"db": "admin", "role": "read", "extra": object()},
        ):
            # Unknown additional fields are inert; only declared authority
            # fields are interpreted, never coerced.
            if role.get("role") == "read":
                self.assertEqual(_role_custody({"authInfo": {
                    "authenticatedUserRoles": [role]}}), (("admin", "read"),))
            else:
                with self.subTest(role=repr(role)), self.assertRaises(ActivationBlocked):
                    _role_custody({"authInfo": {"authenticatedUserRoles": [role]}})


if __name__ == "__main__":
    unittest.main()
