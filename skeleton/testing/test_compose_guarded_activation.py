"""Deterministic fail-closed activation tests; Mongo integration still needs CI."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
import unittest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from skeleton.ai.runtime.inference.reviewer_custody import ReviewerTrustAnchor
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
        self.auth = {"authInfo": {"authenticatedUsers": [
            {"user": "guarded-owner", "db": "admin"},
        ], "authenticatedUserRoles": []}}
        self.error = None

    async def command(self, command: str):
        assert command in ("hello", "connectionStatus")
        if self.error is not None:
            raise self.error
        return self.hello if command == "hello" else self.auth


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


class FakeReviewer:
    def __init__(self, signer):
        self.signer = signer
        self.challenge_count = 0
        self.replayed_signature = None
        self.last_signature = None
        self.on_challenge = None

    def __call__(self, *args):
        return True

    async def attest_challenge(self, payload):
        self.challenge_count += 1
        if self.on_challenge is not None:
            await self.on_challenge(payload)
        if self.replayed_signature is not None:
            return self.replayed_signature
        self.last_signature = self.signer.sign(payload)
        return self.last_signature


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
        self.signer = Ed25519PrivateKey.generate()
        self.reviewer = FakeReviewer(self.signer)
        self.trust_anchor = ReviewerTrustAnchor(
            authority_id="security-reviewer-prod",
            deployment_domain="separate-reviewer-domain",
            ed25519_public_key=self.signer.public_key().public_bytes(
                encoding=serialization.Encoding.Raw,
                format=serialization.PublicFormat.Raw,
            ),
        )
        self.reviewer._anchor = self.trust_anchor
        self.native_patch = patch(
            "skeleton.ai.runtime.inference.native_transformer.NativeTransformerModel",
            FakeNative,
        )
        self.inventory_patch = patch(
            "skeleton.ai.runtime.inference.compose_activation."
            "verify_canonical_source_writer_inventory"
        )
        self.native_patch.start()
        self.reviewer_client_patch = patch(
            "skeleton.ai.runtime.inference.signed_reviewer_client.SignedReviewerClient",
            FakeReviewer,
        )
        self.reviewer_client_patch.start()
        self.addCleanup(self.reviewer_client_patch.stop)
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
            reviewer_trust_anchor=self.trust_anchor,
            tenant_id="tenant",
            actor_id="owner",
            context_id="context",
            expected_model_digest="a" * 64,
            expected_runtime_digest="b" * 64,
            expected_tokenizer_digest="c" * 64,
        )
        options.update(overrides)
        return MongoGuardedActivation(**options)

    async def test_role_rotation_between_successful_probes_invalidates_generation(self):
        self.database.auth["authInfo"]["authenticatedUserRoles"] = [
            {"db": "admin", "role": "readWrite"},
        ]
        gate = self.make()
        permit = await gate.activate()
        self.database.auth["authInfo"]["authenticatedUserRoles"] = [
            {"db": "admin", "role": "read"},
        ]
        with self.assertRaises(ActivationBlocked):
            await gate.assert_active(permit)
        self.assertEqual(gate.phase, ActivationPhase.BLOCKED)

    async def test_role_rotation_during_reviewer_challenge_denies(self):
        async def rotate(_payload):
            self.database.auth["authInfo"]["authenticatedUserRoles"] = [
                {"db": "admin", "role": "read"},
            ]
        self.reviewer.on_challenge = rotate
        gate = self.make()
        with self.assertRaisesRegex(ActivationBlocked, "principal changed"):
            await gate.activate()
        self.assertEqual(gate.phase, ActivationPhase.BLOCKED)

    async def test_role_rotation_during_final_epoch_read_denies(self):
        original = self.epoch.read_epoch
        calls = 0

        async def rotating_epoch(**kwargs):
            nonlocal calls
            calls += 1
            result = await original(**kwargs)
            if calls == 2:
                self.database.auth["authInfo"]["authenticatedUserRoles"] = [
                    {"db": "admin", "role": "read"},
                ]
            return result

        self.epoch.read_epoch = rotating_epoch
        gate = self.make()
        with self.assertRaisesRegex(ActivationBlocked, "principal changed"):
            await gate.activate()
        self.assertEqual(gate.phase, ActivationPhase.BLOCKED)

    async def test_reviewer_anchor_rotation_during_final_mongo_observation_denies(self):
        # The final Mongo status command is an await boundary after the
        # reviewer challenge. Even with an unchanged primary and epoch, a
        # transport trust-anchor swap must not yield an activation permit.
        original_command = self.database.command
        status_reads = 0

        async def rotate_on_final_status(command):
            nonlocal status_reads
            result = await original_command(command)
            if command == "connectionStatus":
                status_reads += 1
                if status_reads == 3:
                    self.reviewer._anchor = object()
            return result

        self.database.command = rotate_on_final_status
        gate = self.make()
        with self.assertRaisesRegex(ActivationBlocked, "trust anchor changed"):
            await gate.activate()
        self.assertEqual(status_reads, 3)
        self.assertEqual(gate.phase, ActivationPhase.BLOCKED)
        self.assertIsNone(gate._epoch_at_activation)

    async def test_executable_topology_equality_denied_before_reviewer(self):
        class ForgedElection:
            def __eq__(self, other):
                return True

        self.database.hello["electionId"] = ForgedElection()
        with self.assertRaisesRegex(ActivationBlocked, "topology identity malformed"):
            await self.make().activate()
        self.assertEqual(self.reviewer.challenge_count, 0)
        self.assertEqual(self.inventory.call_count, 0)

    async def test_invalid_topology_set_version_denied(self):
        for version in (True, -1, 2147483648, "7"):
            with self.subTest(version=version):
                self.database.hello["setVersion"] = version
                with self.assertRaisesRegex(ActivationBlocked, "topology identity malformed"):
                    await self.make().activate()
        self.assertEqual(self.reviewer.challenge_count, 0)

    async def test_topology_rotation_after_reviewer_denied(self):
        self.database.hello["setVersion"] = 7
        async def rotate(_payload):
            self.database.hello["setVersion"] = 8
        self.reviewer.on_challenge = rotate
        with self.assertRaisesRegex(ActivationBlocked, "primary changed"):
            await self.make().activate()
        self.assertEqual(self.make().phase, ActivationPhase.BLOCKED)

    async def test_activation_and_rechecks(self):
        gate = self.make()
        self.assertEqual(gate.phase, ActivationPhase.BLOCKED)
        permit = await gate.activate()
        self.assertEqual(gate.phase, ActivationPhase.ACTIVE)
        self.assertEqual(permit.epoch, 2)
        self.assertEqual(await gate.assert_active(permit), permit)
        self.assertEqual(await gate.assert_active(), permit)
        self.assertEqual(self.inventory.call_count, 3)


    async def test_principal_rotation_during_final_epoch_read_denies(self):
        original = self.epoch.read_epoch
        calls = 0

        async def rotating_epoch(**kwargs):
            nonlocal calls
            calls += 1
            result = await original(**kwargs)
            if calls == 2:
                self.database.auth = {"authInfo": {"authenticatedUsers": [
                    {"user": "rotated-principal", "db": "admin"},
                ]}}
            return result

        self.epoch.read_epoch = rotating_epoch
        gate = self.make()
        with self.assertRaisesRegex(ActivationBlocked, "principal changed during final epoch read"):
            await gate.activate()
        self.assertEqual(gate.phase, ActivationPhase.BLOCKED)

    async def test_duplicate_authenticated_principal_denies(self):
        self.database.auth = {"authInfo": {"authenticatedUsers": [
            {"user": "guarded-owner", "db": "admin"},
            {"user": "guarded-owner", "db": "admin"},
        ]}}
        with self.assertRaisesRegex(ActivationBlocked, "duplicated"):
            await self.make().activate()

    async def test_oversized_or_control_principal_denies(self):
        for username in ("x" * 129, "bad\\nprincipal", "bad\\u007fprincipal"):
            with self.subTest(username=repr(username)):
                self.database.auth = {"authInfo": {"authenticatedUsers": [
                    {"user": username, "db": "admin"},
                ]}}
                with self.assertRaisesRegex(ActivationBlocked, "principal invalid"):
                    await self.make().activate()

    async def test_duplicate_principal_after_reviewer_denies(self):
        original = self.epoch.read_epoch
        calls = 0
        async def mutate(**kwargs):
            nonlocal calls
            calls += 1
            result = await original(**kwargs)
            if calls == 1:
                self.database.auth = {"authInfo": {"authenticatedUsers": [
                    {"user": "guarded-owner", "db": "admin"},
                    {"user": "guarded-owner", "db": "admin"},
                ]}}
            return result
        self.epoch.read_epoch = mutate
        with self.assertRaisesRegex(ActivationBlocked, "principal changed"):
            await self.make().activate()

    async def test_primary_rotation_during_final_epoch_read_denies(self):
        original = self.epoch.read_epoch
        calls = 0

        async def rotating_epoch(**kwargs):
            nonlocal calls
            calls += 1
            result = await original(**kwargs)
            if calls == 2:
                self.database.hello = {"setName": "rs0", "isWritablePrimary": False}
            return result

        self.epoch.read_epoch = rotating_epoch
        gate = self.make()
        with self.assertRaisesRegex(ActivationBlocked, "primary changed during final epoch read"):
            await gate.activate()
        self.assertEqual(gate.phase, ActivationPhase.BLOCKED)

    async def test_unprovisioned_epoch_denies(self):
        self.epoch_error = MongoSourceEpochError("private db credentials")
        gate = self.make()
        with self.assertRaisesRegex(ActivationBlocked, "canonical source epoch unavailable") as caught:
            await gate.activate()
        self.assertNotIn("credentials", str(caught.exception))
        self.assertEqual(gate.phase, ActivationPhase.BLOCKED)

    async def test_executable_replica_set_name_denies_before_reviewer(self):
        class ForgedSetName(str):
            def __eq__(self, other):
                return True

        self.database.hello["setName"] = ForgedSetName("rs0")
        gate = self.make()
        with self.assertRaisesRegex(ActivationBlocked, "replica-set primary"):
            await gate.activate()
        self.assertEqual(gate.phase, ActivationPhase.BLOCKED)
        self.assertEqual(self.inventory.call_count, 0)

    async def test_executable_database_name_denies_before_reviewer(self):
        class ForgedDatabaseName(str):
            def __eq__(self, other):
                return True

        self.database.name = ForgedDatabaseName("tutolage")
        gate = self.make()
        with self.assertRaisesRegex(ActivationBlocked, "database identity missing"):
            await gate.activate()
        self.assertEqual(gate.phase, ActivationPhase.BLOCKED)
        self.assertEqual(self.inventory.call_count, 0)

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

    async def test_unauthenticated_replica_set_denies_activation(self):
        self.database.auth = {"authInfo": {"authenticatedUsers": []}}
        gate = self.make()
        with self.assertRaisesRegex(ActivationBlocked, "authenticated canonical"):
            await gate.activate()
        self.assertEqual(gate.phase, ActivationPhase.BLOCKED)
        self.assertEqual(self.inventory.call_count, 0)

    async def test_malformed_auth_session_denies_activation(self):
        for bad in (None, {}, {"authInfo": {}},
                    {"authInfo": {"authenticatedUsers": [1]}},
                    {"authInfo": {"authenticatedUsers": [
                        {"user": "guarded-owner", "db": ""}]}}):
            with self.subTest(auth=repr(bad)):
                self.database.auth = bad
                gate = self.make()
                with self.assertRaises(ActivationBlocked):
                    await gate.activate()
                self.assertEqual(gate.phase, ActivationPhase.BLOCKED)
        self.assertEqual(self.inventory.call_count, 0)

    async def test_authenticated_mongo_principal_rotation_blocks_existing_permit(self):
        gate = self.make()
        permit = await gate.activate()
        self.database.auth = {"authInfo": {"authenticatedUsers": [
            {"user": "different-writer", "db": "admin"},
        ]}}
        with self.assertRaisesRegex(ActivationBlocked, "authority changed"):
            await gate.assert_active(permit)
        self.assertEqual(gate.phase, ActivationPhase.BLOCKED)
        self.assertIsNone(gate._auth_at_activation)
        self.assertNotIn("different-writer", str(gate.phase))

    async def test_authentication_loss_blocks_existing_permit(self):
        gate = self.make()
        permit = await gate.activate()
        self.database.auth = {"authInfo": {"authenticatedUsers": []}}
        with self.assertRaises(ActivationBlocked):
            await gate.assert_active(permit)
        self.assertEqual(gate.phase, ActivationPhase.BLOCKED)

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

    async def test_native_factory_requires_independent_operator_pins(self):
        import inspect
        from skeleton.ai.runtime.inference.compose_activation import (
            compose_mongo_guarded_native_adapter,
        )
        parameters = inspect.signature(compose_mongo_guarded_native_adapter).parameters
        for name in ("operator_model_digest", "operator_runtime_digest",
                     "operator_tokenizer_digest"):
            self.assertIn(name, parameters)
            self.assertIs(parameters[name].default, inspect.Parameter.empty)
            self.assertEqual(parameters[name].kind, inspect.Parameter.KEYWORD_ONLY)

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

    async def test_old_failed_probe_cannot_block_new_activation(self):
        gate = self.make()
        await gate.activate()
        original_probe = gate._probe
        entered = asyncio.Event()
        release = asyncio.Event()

        async def delayed_failure():
            entered.set()
            await release.wait()
            raise ActivationBlocked("old generation failed")

        gate._probe = delayed_failure
        stale = asyncio.create_task(gate.assert_active())
        await entered.wait()
        # Model an independent authority failure invalidating the old
        # generation before the stale asynchronous probe completes.
        gate._phase = ActivationPhase.BLOCKED
        gate._generation += 1
        gate._epoch_at_activation = None
        gate._auth_at_activation = None
        gate._probe = original_probe
        new_permit = await gate.activate()
        release.set()
        with self.assertRaises(ActivationBlocked):
            await stale
        self.assertEqual(gate.phase, ActivationPhase.ACTIVE)
        self.assertEqual(await gate.assert_active(new_permit), new_permit)

    async def test_old_successful_probe_cannot_erase_new_activation(self):
        gate = self.make()
        await gate.activate()
        original_probe = gate._probe
        entered = asyncio.Event()
        release = asyncio.Event()

        async def delayed_success():
            entered.set()
            await release.wait()
            return await original_probe()

        gate._probe = delayed_success
        stale = asyncio.create_task(gate.assert_active())
        await entered.wait()
        # A concurrent failed authority check blocks the old generation.
        gate._phase = ActivationPhase.BLOCKED
        gate._generation += 1
        gate._probe = original_probe
        new_permit = await gate.activate()
        release.set()
        with self.assertRaisesRegex(ActivationBlocked, "authority changed"):
            await stale
        self.assertEqual(gate.phase, ActivationPhase.ACTIVE)
        self.assertEqual(await gate.assert_active(new_permit), new_permit)

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

    async def test_verdict_and_challenge_cannot_use_distinct_trust_anchors(self):
        alternate = ReviewerTrustAnchor(
            authority_id="security-reviewer-prod",
            deployment_domain="separate-reviewer-domain",
            ed25519_public_key=Ed25519PrivateKey.generate().public_key().public_bytes(
                encoding=serialization.Encoding.Raw,
                format=serialization.PublicFormat.Raw,
            ),
        )
        with self.assertRaisesRegex(ActivationBlocked, "trust anchor mismatch"):
            self.make(reviewer_trust_anchor=alternate)
        other_domain = ReviewerTrustAnchor(
            authority_id="security-reviewer-prod",
            deployment_domain="unrelated-deployment-domain",
            ed25519_public_key=self.trust_anchor.ed25519_public_key,
        )
        with self.assertRaisesRegex(ActivationBlocked, "trust anchor mismatch"):
            self.make(reviewer_trust_anchor=other_domain)

    async def test_unsigned_verdict_client_denied_even_with_valid_challenge_signer(self):
        # A challenge signature alone does not authenticate review verdicts.
        # Production must use the concrete signed transport, not a local
        # permissive callable that happens to delegate attest_challenge().
        from skeleton.ai.runtime.inference.signed_reviewer_client import (
            SignedReviewerClient,
        )
        with patch(
            "skeleton.ai.runtime.inference.signed_reviewer_client.SignedReviewerClient",
            SignedReviewerClient,
        ):
            with self.assertRaisesRegex(ActivationBlocked, "signed independent"):
                self.make()

    async def test_reviewer_anchor_rotation_after_activation_denies(self):
        gate = self.make()
        permit = await gate.activate()
        self.reviewer._anchor = ReviewerTrustAnchor(
            authority_id="security-reviewer-prod",
            deployment_domain="separate-reviewer-domain",
            ed25519_public_key=Ed25519PrivateKey.generate().public_key().public_bytes(
                encoding=serialization.Encoding.Raw,
                format=serialization.PublicFormat.Raw,
            ),
        )
        with self.assertRaisesRegex(ActivationBlocked, "trust anchor changed"):
            await gate.assert_active(permit)
        self.assertEqual(gate.phase, ActivationPhase.BLOCKED)

    async def test_reviewer_anchor_rotation_during_attestation_denies(self):
        async def rotate(_payload):
            self.reviewer._anchor = ReviewerTrustAnchor(
                authority_id="security-reviewer-prod",
                deployment_domain="different-domain",
                ed25519_public_key=self.trust_anchor.ed25519_public_key,
            )
        self.reviewer.on_challenge = rotate
        gate = self.make()
        with self.assertRaisesRegex(ActivationBlocked, "trust anchor changed"):
            await gate.activate()
        self.assertEqual(gate.phase, ActivationPhase.BLOCKED)

    async def test_fresh_reviewer_attestation_on_each_probe(self):
        gate = self.make()
        permit = await gate.activate()
        self.assertEqual(self.reviewer.challenge_count, 1)
        self.assertEqual(await gate.assert_active(permit), permit)
        self.assertEqual(self.reviewer.challenge_count, 2)

    async def test_replayed_reviewer_signature_blocks(self):
        gate = self.make()
        permit = await gate.activate()
        self.reviewer.replayed_signature = self.reviewer.last_signature
        with self.assertRaisesRegex(ActivationBlocked, "reviewer custody"):
            await gate.assert_active(permit)
        self.assertEqual(gate.phase, ActivationPhase.BLOCKED)

    async def test_wrong_signer_blocks(self):
        self.reviewer.signer = Ed25519PrivateKey.generate()
        with self.assertRaisesRegex(ActivationBlocked, "reviewer custody"):
            await self.make().activate()

    async def test_unpinned_reviewer_blocks(self):
        with self.assertRaisesRegex(ActivationBlocked, "trust anchor"):
            self.make(reviewer_trust_anchor=None)
        with self.assertRaisesRegex(ActivationBlocked, "trust anchor"):
            self.make(reviewer_authority_id="untrusted-reviewer")

    async def test_mongo_principal_changes_during_reviewer_challenge(self):
        async def rotate(_payload):
            self.database.auth = {"authInfo": {"authenticatedUsers": [
                {"user": "replacement", "db": "admin"},
            ]}}
        self.reviewer.on_challenge = rotate
        gate = self.make()
        with self.assertRaisesRegex(ActivationBlocked, "principal changed"):
            await gate.activate()
        self.assertEqual(gate.phase, ActivationPhase.BLOCKED)

    async def test_mongo_election_changes_during_reviewer_challenge(self):
        self.database.hello["electionId"] = "election-a"
        async def rotate(_payload):
            self.database.hello["electionId"] = "election-b"
        self.reviewer.on_challenge = rotate
        gate = self.make()
        with self.assertRaisesRegex(ActivationBlocked, "primary changed"):
            await gate.activate()
        self.assertEqual(gate.phase, ActivationPhase.BLOCKED)

    async def test_writer_enters_during_reviewer_challenge(self):
        async def writer_started(_payload):
            self.epoch_value = 3
        self.reviewer.on_challenge = writer_started
        gate = self.make()
        with self.assertRaisesRegex(ActivationBlocked, "source changed"):
            await gate.activate()
        self.assertEqual(gate.phase, ActivationPhase.BLOCKED)

    async def test_total_authority_probe_timeout_blocks(self):
        gate = self.make()
        self.wait_for_epoch = asyncio.Event()
        with patch(
            "skeleton.ai.runtime.inference.compose_activation._MAX_TOTAL_AUTHORITY_SECONDS",
            0.01,
        ):
            with self.assertRaisesRegex(ActivationBlocked, "timed out"):
                await gate.activate()
        self.assertEqual(gate.phase, ActivationPhase.BLOCKED)

    async def test_scope_and_digest_denies(self):
        with self.assertRaises(ActivationBlocked):
            self.make(tenant_id=" tenant ")
        with self.assertRaises(ActivationBlocked):
            self.make(actor_id="")
        with self.assertRaises(ActivationBlocked):
            self.make(expected_runtime_digest="not-a-digest")

    async def test_owner_scope_rejects_unencodable_and_control_identity(self):
        for scope in ("tenant_id", "actor_id", "context_id"):
            for invalid in ("broken\\ud800", "broken\\udfff", "name\\x7f", "x" * 513):
                with self.subTest(scope=scope, invalid=repr(invalid)):
                    with self.assertRaisesRegex(ActivationBlocked, "owner scope invalid"):
                        self.make(**{scope: invalid})

    async def test_owner_scope_rejects_string_subclass_and_digest_subclass(self):
        class IdentitySubclass(str):
            pass

        with self.assertRaisesRegex(ActivationBlocked, "owner scope invalid"):
            self.make(actor_id=IdentitySubclass("owner"))
        with self.assertRaisesRegex(ActivationBlocked, "artifact digest invalid"):
            self.make(expected_model_digest=IdentitySubclass("a" * 64))


if __name__ == "__main__":
    unittest.main()
