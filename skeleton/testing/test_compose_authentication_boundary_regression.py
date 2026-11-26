"""Fail-closed authentication snapshot regression for guarded Compose.

These are parser/denial tests, not proof of live writer coverage or readiness.
"""
from __future__ import annotations

import unittest
from unittest.mock import patch

from skeleton.app.compose_guarded_preflight import (
    _authenticated_principals,
    inspect_compose_mongo_epoch,
)


class _Database:
    def __init__(self, auth):
        self.auth = auth
        self.commands = []

    async def command(self, name):
        self.commands.append(name)
        if name == "hello":
            return {
                "isWritablePrimary": True,
                "setName": "rs0",
                "me": "mongo-a:27017",
                "primary": "mongo-a:27017",
                "hosts": ["mongo-a:27017"],
            }
        if name == "connectionStatus":
            return self.auth
        raise AssertionError("unexpected command")


class _ForbiddenEpoch:
    def __init__(self, database):
        raise AssertionError("invalid authentication must never reach epoch")


class AuthenticationBoundaryRegression(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.user = {"db": "admin", "user": "operator"}
        self.role = {"db": "admin", "role": "readWrite"}

    async def _assert_rejected(self, auth):
        db = _Database(auth)
        with patch(
            "skeleton.app.compose_guarded_preflight.MongoCanonicalSourceEpoch",
            _ForbiddenEpoch,
        ):
            result = await inspect_compose_mongo_epoch(
                db, tenant_id="tenant", actor_id="actor", context_id="context",
            )
        self.assertEqual(result["code"], "mongo_authenticated_session_required")
        self.assertFalse(result["guarded_local_ai_ready"])
        self.assertFalse(result["writes_performed"])
        self.assertEqual(db.commands, ["hello", "connectionStatus"])

    async def test_duplicate_users_and_roles_fail_before_epoch(self):
        for auth in (
            {"authInfo": {"authenticatedUsers": [self.user, dict(self.user)]}},
            {"authInfo": {
                "authenticatedUsers": [self.user],
                "authenticatedUserRoles": [self.role, dict(self.role)],
            }},
        ):
            with self.subTest(auth=auth):
                self.assertIsNone(_authenticated_principals(auth))
                await self._assert_rejected(auth)

    async def test_non_scalar_and_subclass_principals_fail_before_epoch(self):
        class Forged(str):
            def __eq__(self, other):
                return True

        for bad in (Forged("operator"), 1, True, None, [], {}, "\noperator", " operator"):
            auth = {"authInfo": {
                "authenticatedUsers": [{"db": "admin", "user": bad}],
            }}
            with self.subTest(value=repr(bad)):
                self.assertIsNone(_authenticated_principals(auth))
                await self._assert_rejected(auth)

    async def test_oversized_and_malformed_role_metadata_fails_before_epoch(self):
        for roles in (
            [dict(self.role)] * 65,
            [{"db": "admin", "role": "read\nWrite"}],
            [{"db": "admin", "role": ""}],
            [{"db": "admin", "role": 1}],
            {"db": "admin", "role": "readWrite"},
        ):
            auth = {"authInfo": {
                "authenticatedUsers": [self.user],
                "authenticatedUserRoles": roles,
            }}
            with self.subTest(roles=repr(roles)[:80]):
                self.assertIsNone(_authenticated_principals(auth))
                await self._assert_rejected(auth)

    def test_role_rotation_changes_observation_without_granting_readiness(self):
        base = {"authInfo": {
            "authenticatedUsers": [self.user],
            "authenticatedUserRoles": [self.role],
        }}
        rotated = {"authInfo": {
            "authenticatedUsers": [self.user],
            "authenticatedUserRoles": [{"db": "admin", "role": "read"}],
        }}
        self.assertNotEqual(
            _authenticated_principals(base),
            _authenticated_principals(rotated),
        )


if __name__ == "__main__":
    unittest.main()
