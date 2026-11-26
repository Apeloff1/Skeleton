"""Regression boundaries for advertised Mongo primary membership.

These are source-only deterministic tests; they do not certify live Mongo,
writer inventory, reviewer custody, model binding or consumer readiness.
"""
from __future__ import annotations

import unittest

from skeleton.app.compose_guarded_preflight import _trusted_topology


class ComposePrimaryMembershipTests(unittest.TestCase):
    def setUp(self):
        self.base = {
            "setName": "rs0",
            "isWritablePrimary": True,
            "me": "mongo-a:27017",
            "primary": "mongo-a:27017",
            "hosts": ["mongo-a:27017", "mongo-b:27017"],
        }

    def test_consistent_primary_is_only_a_topology_observation(self):
        observed = _trusted_topology(self.base)
        self.assertIsNotNone(observed)
        self.assertEqual(observed, _trusted_topology(dict(self.base)))

    def test_primary_must_be_a_voting_host_when_advertised(self):
        for field in ("me", "primary"):
            with self.subTest(field=field):
                claim = dict(self.base)
                claim[field] = "mongo-c:27017"
                self.assertIsNone(_trusted_topology(claim))

    def test_primary_cannot_be_passive_or_arbiter(self):
        for field in ("passives", "arbiters"):
            with self.subTest(field=field):
                claim = dict(self.base)
                claim[field] = ["mongo-a:27017"]
                self.assertIsNone(_trusted_topology(claim))

    def test_advertised_membership_changes_snapshot(self):
        before = _trusted_topology(self.base)
        claim = dict(self.base)
        claim["hosts"] = ["mongo-a:27017", "mongo-c:27017"]
        self.assertNotEqual(before, _trusted_topology(claim))

    def test_duplicate_membership_is_rejected(self):
        for field in ("hosts", "passives", "arbiters"):
            with self.subTest(field=field):
                claim = dict(self.base)
                claim[field] = ["mongo-b:27017", "mongo-b:27017"]
                self.assertIsNone(_trusted_topology(claim))

    def test_duplicate_across_roles_is_rejected(self):
        for field in ("passives", "arbiters"):
            with self.subTest(field=field):
                claim = dict(self.base)
                claim[field] = ["mongo-b:27017"]
                self.assertIsNone(_trusted_topology(claim))

    def test_malformed_membership_is_rejected(self):
        for hosts in (
            [], (), "mongo-a:27017", [""], [None], [123],
            ["mongo-a:27017\\n"], ["mongo-a:27017"] * 65,
            ["x" * 513], ["møngo:27017"],
        ):
            with self.subTest(hosts=repr(hosts)):
                claim = dict(self.base)
                claim["hosts"] = hosts
                self.assertIsNone(_trusted_topology(claim))

    def test_primary_role_conflicts_are_rejected(self):
        for field, value in (
            ("secondary", True), ("arbiterOnly", True),
            ("secondary", 1), ("arbiterOnly", "false"),
            ("ismaster", False), ("ismaster", 1),
        ):
            with self.subTest(field=field, value=value):
                claim = dict(self.base)
                claim[field] = value
                self.assertIsNone(_trusted_topology(claim))

    def test_no_election_or_authorization_claim_from_membership(self):
        # A topology snapshot is never an activation or fencing permit.
        claim = dict(self.base)
        claim["electionId"] = "election-a"
        observed = _trusted_topology(claim)
        self.assertIsNotNone(observed)
        claim["electionId"] = "election-b"
        self.assertNotEqual(observed, _trusted_topology(claim))


if __name__ == "__main__":
    unittest.main()
