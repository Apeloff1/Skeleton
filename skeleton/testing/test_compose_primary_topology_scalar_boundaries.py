"""Fail-closed regression cases for Compose Mongo primary topology snapshots.

These tests qualify pure parsing only, not live Mongo writer fencing or AI activation.
"""
from __future__ import annotations

import unittest

from skeleton.app.compose_guarded_preflight import _trusted_topology


class PrimaryTopologyScalarBoundaries(unittest.TestCase):
    def setUp(self) -> None:
        self.hello = {
            "setName": "rs0",
            "isWritablePrimary": True,
            "me": "mongo-a:27017",
            "primary": "mongo-a:27017",
            "hosts": ["mongo-a:27017", "mongo-b:27017"],
        }

    def test_boolean_set_version_is_not_an_integer_generation(self) -> None:
        for value in (True, False, -1, 1 << 63, 1.5, "1"):
            with self.subTest(value=value):
                hello = dict(self.hello, setVersion=value)
                self.assertIsNone(_trusted_topology(hello))

    def test_primary_flag_must_be_exact_boolean_true(self) -> None:
        for value in (1, "true", False, None, 0):
            with self.subTest(value=value):
                hello = dict(self.hello, isWritablePrimary=value)
                self.assertIsNone(_trusted_topology(hello))

    def test_endpoint_subclasses_are_rejected(self) -> None:
        class ForgedHost(str):
            def __eq__(self, other: object) -> bool:
                return True

            __hash__ = str.__hash__

        for field in ("me", "primary"):
            with self.subTest(field=field):
                hello = dict(self.hello)
                hello[field] = ForgedHost("mongo-a:27017")
                self.assertIsNone(_trusted_topology(hello))
        hello = dict(self.hello)
        hello["hosts"] = [ForgedHost("mongo-a:27017")]
        self.assertIsNone(_trusted_topology(hello))

    def test_role_list_must_not_duplicate_across_roles(self) -> None:
        hello = dict(self.hello)
        hello["passives"] = ["mongo-c:27017"]
        hello["arbiters"] = ["mongo-c:27017"]
        self.assertIsNone(_trusted_topology(hello))

    def test_stable_snapshot_is_not_readiness_evidence(self) -> None:
        first = _trusted_topology(self.hello)
        self.assertIsNotNone(first)
        hello = dict(self.hello)
        hello["hosts"] = list(reversed(self.hello["hosts"]))
        self.assertEqual(first, _trusted_topology(hello))
        hello["setVersion"] = 2
        self.assertNotEqual(first, _trusted_topology(hello))


if __name__ == "__main__":
    unittest.main()
