"""Deterministic fail-closed activation tests; Mongo integration still needs CI."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from skeleton.ai.runtime.inference.compose_activation import (
    ActivationBlocked, ActivationPhase, ActivationPermit, MongoGuardedActivation,
)
from skeleton.persistence.mongo_source_epoch import (
    MongoCanonicalSourceEpoch, MongoSourceEpochError,
)


class FakeDatabase:
    def __init__(self) -> None:
        self.name = "tutolage"
        self.client = object()
        self.hello = {"setName": "rs0", "isWritablePrimary": True}
        self.error = None

    async def command(self, command: str):
        assert command == "hello"
        if self.error is not None:
            raise self.error
        return self.hello


class FakeTokenizer:
    def __init__(self) -> None:
        self.digest = "c" * 64
        self.valid = True

    def assert_unchanged(self):
        if not self.valid:
            raise ValueError("secret tokenizer diagnostic")


class FakeNative:
    def __init__(self) -> None:
        self.model_digest = "a" * 64
        self.runtime_digest = "b" * 64
        self.runtime = SimpleNamespace(tokenizer=FakeTokenizer())
        self.valid = True

    def assert_identity(self):
        if not self.valid:
            raise ValueError("secret model diagnostic")


class ActivationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.database = FakeDatabase()
        self.epoch = object.__new__(MongoCanonicalSourceEpoch)
        self.epoch._database = self.database
        self.epoch._collection = SimpleNamespace(database=self.database)
        self.epoch._reader = SimpleNamespace(database=self.database)
        self.epoch_value = 2
        self.epoch_error = None
        self.wait_for_epoch = None

        async def read_epoch(*, tenant_id, actor_id, context_id):
            self.assertEqual((tenant_id, actor_id, context_id), ("tenant", "owner", "context"))
            if self.wait_for_epoch is not None:
                await self.wait_for_epoch.wait()
            if self.epoch_error is not None:
                raise self.epoch_error
            return self.epoch_value

        self.epoch.read_epoch = read_epoch
        self.backend = FakeNative()
        collection = lambda: SimpleNamespace(database=self.database)
        self.conversation = SimpleNamespace(threads=collection(), messages=collection())
        self.memory = SimpleNamespace(
            records=collection(), idempotency=collection(),
            revisions=collection(), projection_outbox=collection(),
        )
        self.reviewer = lambda *args: True
        self.native_patch = patch(
            "skeleton.ai.runtime.inference.native_transformer.NativeTransformerModel",
            FakeNative,
        )
        self.inventory_patch = patch(
            "skeleton.ai.runtime.inference.compose_activation."
            "verify_canonical_source_writer_inventory"
        )
        self.native_patch.start()
        self.inventory = self.inventory_patch.start()
        self.addCleanup(self.native_patch.stop)
        self.addCleanup(self.inventory_patch.stop)

    def make(self, **overrides):
        options = dict(
            database=self.database,
            epoch=self.epoch,
            conversation=self.conversation,
            memory=self.memory,
            backend=self.backend,
            reviewer=self.reviewer,
            reviewer_authority_id="security-reviewer-prod",
            tenant_id="tenant",
            actor_id="owner",
            context_id="context",
            expected_model_digest="a" * 64,
            expected_runtime_digest="b" * 64,
            expected_tokenizer_digest="c" * 64,
        )
        options.update(overrides)
        return MongoGuardedActivation(**options)

    async def test_activation_and_rechecks(self):
        gate = self.make()
        self.assertEqual(gate.phase, ActivationPhase.BLOCKED)
        permit = await gate.activate()
        self.assertEqual(gate.phase, ActivationPhase.ACTIVE)
        self.assertEqual(permit.epoch, 2)
        self.assertEqual(await gate.assert_active(permit), permit)
        self.assertEqual(await gate.assert_active(), permit)
        self.assertEqual(self.inventory.call_count, 3)

    async def test_unprovisioned_epoch_denies(self):
        self.epoch_error = MongoSourceEpochError("private db credentials")
        gate = self.make()
        with self.assertRaisesRegex(ActivationBlocked, "canonical source epoch unavailable") as caught:
            await gate.activate()
        self.assertNotIn("credentials", str(caught.exception))
        self.assertEqual(gate.phase, ActivationPhase.BLOCKED)

    async def test_standalone_mongo_denies_without_migration(self):
        self.database.hello = {"isWritablePrimary": True}
        gate = self.make()
        with self.assertRaisesRegex(ActivationBlocked, "replica-set primary"):
            await gate.activate()
        self.assertEqual(gate.phase, ActivationPhase.BLOCKED)
        self.assertEqual(self.inventory.call_count, 0)

    async def test_secondary_denies(self):
        self.database.hello = {"setName": "rs0", "isWritablePrimary": False}
        with self.assertRaises(ActivationBlocked):
            await self.make().activate()

    async def test_malformed_hello_denies(self):
        self.database.hello = {"setName": "rs0", "isWritablePrimary": 1}
        with self.assertRaises(ActivationBlocked):
            await self.make().activate()

    async def test_db_exception_redacted(self):
        self.database.error = RuntimeError("mongo password leaked in exception")
        with self.assertRaises(ActivationBlocked) as caught:
            await self.make().activate()
        self.assertNotIn("password", str(caught.exception))

    async def test_cross_database_conversation_denies(self):
        self.conversation.threads.database = FakeDatabase()
        with self.assertRaisesRegex(ActivationBlocked, "ownership mismatch"):
            await self.make().activate()
        self.assertEqual(self.inventory.call_count, 0)

    async def test_cross_client_memory_denies(self):
        self.memory.records.database = FakeDatabase()
        with self.assertRaisesRegex(ActivationBlocked, "ownership mismatch"):
            await self.make().activate()

    async def test_cross_database_epoch_collection_denies(self):
        self.epoch._reader.database = FakeDatabase()
        with self.assertRaisesRegex(ActivationBlocked, "ownership mismatch"):
            await self.make().activate()

    async def test_missing_inventory_denies(self):
        self.inventory.side_effect = MongoSourceEpochError("unfenced writer")
        gate = self.make()
        with self.assertRaises(ActivationBlocked):
            await gate.activate()
        self.assertEqual(gate.phase, ActivationPhase.BLOCKED)

    async def test_model_identity_denies(self):
        self.backend.valid = False
        with self.assertRaises(ActivationBlocked) as caught:
            await self.make().activate()
        self.assertNotIn("secret", str(caught.exception))

    async def test_tokenizer_identity_denies(self):
        self.backend.runtime.tokenizer.valid = False
        with self.assertRaises(ActivationBlocked):
            await self.make().activate()

    async def test_artifact_binding_denies(self):
        gate_tokenizer = self.make(expected_tokenizer_digest="f" * 64)
        with self.assertRaises(ActivationBlocked):
            await gate_tokenizer.activate()
        gate = self.make(expected_model_digest="d" * 64)
        with self.assertRaises(ActivationBlocked):
            await gate.activate()

    async def test_stable_epoch_change_blocks_inference(self):
        gate = self.make()
        permit = await gate.activate()
        self.epoch_value = 4
        with self.assertRaisesRegex(ActivationBlocked, "authority changed"):
            await gate.assert_active(permit)
        self.assertEqual(gate.phase, ActivationPhase.BLOCKED)
        with self.assertRaises(ActivationBlocked):
            await gate.assert_active(permit)

    async def test_writing_or_revoked_epoch_denies(self):
        gate = self.make()
        permit = await gate.activate()
        self.epoch_error = MongoSourceEpochError("writing or revoked")
        with self.assertRaises(ActivationBlocked):
            await gate.assert_active(permit)
        self.assertEqual(gate.phase, ActivationPhase.BLOCKED)

    async def test_local_revoke_is_terminal(self):
        gate = self.make()
        permit = await gate.activate()
        await gate.revoke()
        self.assertEqual(gate.phase, ActivationPhase.REVOKED)
        with self.assertRaises(ActivationBlocked):
            await gate.assert_active(permit)
        with self.assertRaises(ActivationBlocked):
            await gate.activate()

    async def test_stale_permit_denies(self):
        gate = self.make()
        permit = await gate.activate()
        forged = ActivationPermit(
            permit.generation + 1, permit.tenant_id, permit.actor_id,
            permit.context_id, permit.epoch, permit.model_digest,
            permit.runtime_digest, permit.tokenizer_digest,
        )
        with self.assertRaises(ActivationBlocked):
            await gate.assert_active(forged)
        self.assertEqual(gate.phase, ActivationPhase.ACTIVE)

    async def test_revoke_during_probe_remains_terminal(self):
        gate = self.make()
        permit = await gate.activate()
        self.wait_for_epoch = asyncio.Event()
        pending = asyncio.create_task(gate.assert_active(permit))
        await asyncio.sleep(0)
        await gate.revoke()
        self.wait_for_epoch.set()
        with self.assertRaises(ActivationBlocked):
            await pending
        self.assertEqual(gate.phase, ActivationPhase.REVOKED)
        with self.assertRaises(ActivationBlocked):
            await gate.activate()

    async def test_cancellation_blocks_activation(self):
        gate = self.make()
        self.wait_for_epoch = asyncio.Event()
        pending = asyncio.create_task(gate.activate())
        await asyncio.sleep(0)
        pending.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await pending
        self.assertEqual(gate.phase, ActivationPhase.BLOCKED)

    async def test_mismatched_database_denies(self):
        with self.assertRaisesRegex(ActivationBlocked, "canonical epoch database"):
            self.make(database=FakeDatabase())

    async def test_reviewer_identity_denies(self):
        with self.assertRaises(ActivationBlocked):
            self.make(reviewer=None)
        with self.assertRaises(ActivationBlocked):
            self.make(reviewer_authority_id="\nunsafe")
        with self.assertRaises(ActivationBlocked):
            self.make(reviewer_authority_id="")

    async def test_scope_and_digest_denies(self):
        with self.assertRaises(ActivationBlocked):
            self.make(tenant_id=" tenant ")
        with self.assertRaises(ActivationBlocked):
            self.make(actor_id="")
        with self.assertRaises(ActivationBlocked):
            self.make(expected_runtime_digest="not-a-digest")


if __name__ == "__main__":
    unittest.main()
