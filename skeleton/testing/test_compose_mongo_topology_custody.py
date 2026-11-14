"""Fail-closed topology snapshots for guarded Compose preflight."""
from __future__ import annotations

import unittest

from skeleton.app.compose_guarded_preflight import _trusted_topology


class HostileString(str):
    def __eq__(self, other):
        raise AssertionError("untrusted equality must not execute")

    def __str__(self):
        raise AssertionError("untrusted conversion must not execute")


class HostileInteger(int):
    def __eq__(self, other):
        raise AssertionError("untrusted equality must not execute")


class ComposeTopologyCustodyTests(unittest.TestCase):
    def test_valid_minimal_and_stable_topology(self):
        hello = {"setName": "rs0", "isWritablePrimary": True}
        self.assertEqual(_trusted_topology(hello), ("rs0", None, None, None, None))
        self.assertEqual(_trusted_topology(dict(hello)), _trusted_topology(hello))

    def test_empty_advertised_voting_hosts_fail_closed(self):
        # An explicit empty voting set cannot establish a primary identity.
        # Omitted hosts remain observation-only for older server versions.
        hello = {"setName": "rs0", "isWritablePrimary": True}
        self.assertIsNotNone(_trusted_topology(hello))
        self.assertIsNone(_trusted_topology({**hello, "hosts": []}))
        self.assertIsNone(_trusted_topology({**hello, "hosts": [], "me": "mongo:27017"}))
        self.assertIsNotNone(_trusted_topology({**hello, "hosts": ["mongo:27017"], "me": "mongo:27017"}))

    def test_hostile_fields_never_execute_user_defined_equality(self):
        for field, value in (
            ("setName", HostileString("rs0")),
            ("me", HostileString("mongo:27017")),
            ("primary", HostileString("mongo:27017")),
            ("electionId", HostileString("abc")),
            ("setVersion", HostileInteger(1)),
        ):
            with self.subTest(field=field):
                hello = {"setName": "rs0", "isWritablePrimary": True, field: value}
                self.assertIsNone(_trusted_topology(hello))

    def test_malformed_fields_rejected(self):
        for field, value in (
            ("me", []), ("primary", {}), ("electionId", []),
            ("setVersion", True), ("setVersion", -1),
            ("me", "bad\\naddress"), ("primary", "x" * 513),
            ("electionId", "bad\\nvalue"),
        ):
            with self.subTest(field=field, value=repr(value)):
                self.assertIsNone(_trusted_topology({
                    "setName": "rs0", "isWritablePrimary": True, field: value,
                }))

    def test_non_primary_and_mapping_subclasses_rejected(self):
        self.assertIsNone(_trusted_topology({"setName": "rs0", "isWritablePrimary": 1}))
        class UntrustedDict(dict):
            def get(self, key, default=None):
                raise AssertionError("untrusted mapping access")
        self.assertIsNone(_trusted_topology(UntrustedDict(
            setName="rs0", isWritablePrimary=True)))

    def test_election_change_is_detected(self):
        initial = _trusted_topology({"setName": "rs0", "isWritablePrimary": True,
                                     "electionId": "old"})
        rotated = _trusted_topology({"setName": "rs0", "isWritablePrimary": True,
                                     "electionId": "new"})
        self.assertNotEqual(initial, rotated)


if __name__ == "__main__":
    unittest.main()
