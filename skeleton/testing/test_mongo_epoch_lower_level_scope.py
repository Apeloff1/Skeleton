"""Lower-level Mongo source mutations must not trust executable scope scalars."""
from __future__ import annotations

import asyncio
from contextvars import ContextVar
import unittest

from skeleton.persistence.mongo_source_epoch import (
    MongoCanonicalSourceEpoch, MongoSourceEpochError, _BoundWriter,
)


class ForgedIdentity(str):
    """A hostile scalar which claims equality with every authenticated ID."""

    def __eq__(self, other):
        return True

    __hash__ = str.__hash__


class LowerLevelScopeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.epoch = object.__new__(MongoCanonicalSourceEpoch)
        self.epoch._active = ContextVar("lower-level-scope-test", default=None)
        self.binding = _BoundWriter(
            tenant_id="real-tenant", actor_id="real-actor",
            task=asyncio.current_task(), token="real-token",
        )
        self.scope = self.epoch._active.set(self.binding)

    async def asyncTearDown(self):
        self.epoch._active.reset(self.scope)

    async def test_real_actor_scope_admitted(self):
        self.epoch.require_actor_writer(tenant_id="real-tenant", actor_id="real-actor")

    async def test_real_tenant_scope_admitted(self):
        self.epoch.require_tenant_writer(tenant_id="real-tenant")

    async def test_actor_subclass_rejected_before_equality(self):
        with self.assertRaisesRegex(MongoSourceEpochError, "identity invalid"):
            self.epoch.require_actor_writer(
                tenant_id="real-tenant", actor_id=ForgedIdentity("other-actor"),
            )

    async def test_tenant_subclass_rejected_before_equality(self):
        with self.assertRaisesRegex(MongoSourceEpochError, "identity invalid"):
            self.epoch.require_actor_writer(
                tenant_id=ForgedIdentity("other-tenant"), actor_id="real-actor",
            )

    async def test_deletion_tenant_subclass_rejected(self):
        with self.assertRaisesRegex(MongoSourceEpochError, "identity invalid"):
            self.epoch.require_tenant_writer(tenant_id=ForgedIdentity("other-tenant"))

    async def test_cross_task_context_inheritance_rejected(self):
        async def child():
            with self.assertRaisesRegex(MongoSourceEpochError, "owner-scoped epoch"):
                self.epoch.require_actor_writer(tenant_id="real-tenant", actor_id="real-actor")
            with self.assertRaisesRegex(MongoSourceEpochError, "actor writer"):
                self.epoch.require_tenant_writer(tenant_id="real-tenant")
        await asyncio.create_task(child())

    async def test_poisoned_binding_rejected(self):
        self.binding.poisoned = True
        with self.assertRaisesRegex(MongoSourceEpochError, "poisoned"):
            self.epoch.require_actor_writer(tenant_id="real-tenant", actor_id="real-actor")
        with self.assertRaisesRegex(MongoSourceEpochError, "poisoned"):
            self.epoch.require_tenant_writer(tenant_id="real-tenant")

    async def test_malformed_unicode_rejected(self):
        malformed = "\\ud800"
        with self.assertRaisesRegex(MongoSourceEpochError, "identity invalid"):
            self.epoch.require_tenant_writer(tenant_id=malformed)


if __name__ == "__main__":
    unittest.main()
