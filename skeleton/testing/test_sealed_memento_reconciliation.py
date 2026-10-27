"""Dual Ed25519 authorization and exact-one-step crash reconciliation drills."""

import asyncio
from dataclasses import replace

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from skeleton.context.sealed_memento import MementoCatalogHead, MementoRecord
from skeleton.persistence.sealed_memento_reconciliation import (
    MementoRecoveryDenied, RecoveryGrant, RecoverySignature,
    SignedMementoReconciler,
)
from skeleton.persistence.sealed_memento_witness import (
    MementoWitnessDivergence, MementoWitnessIndeterminate, _binding_digest,
)
from skeleton.testing.test_sealed_memento_witness import add, setup


def keys():
    raw = (Ed25519PrivateKey.generate(), Ed25519PrivateKey.generate())
    public = {
        f"operator-{index}": item.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
        for index, item in enumerate(raw)
    }
    return raw, public


def approval(grant, raw):
    return tuple(RecoverySignature(f"operator-{index}", key.sign(grant.signed_bytes()))
                 for index, key in enumerate(raw))


async def crash_candidate():
    archive, mongo, witness, guarded = setup()
    await add(archive, guarded)
    old = await witness.read(binding_digest=_binding_digest(archive))
    wire, proposed = archive.seal(MementoRecord(2, "llm", b"actual response", causal_serial=1),
                                   previous=old.head)
    await mongo.publish(archive=archive, expected_head=old.head,
                        expected_thread_version=1, stream="llm", ciphertext=wire)
    assert mongo.head == proposed
    return archive, mongo, witness, old, proposed


def setup_grant(archive, old, proposed, *, now=1900000000):
    return RecoveryGrant(
        incident_id="INC-93001", binding_digest=_binding_digest(archive),
        witness_revision=old.revision, witness_head=old.head,
        candidate_head=proposed, source_thread_version=1,
        issued_at=now-20, expires_at=now+200,
    )


def test_two_operator_reconciles_once_then_normal_reads_resume():
    async def scenario():
        archive, mongo, witness, old, proposed = await crash_candidate()
        private, public = keys()
        grant = setup_grant(archive, old, proposed)
        verifier = SignedMementoReconciler(public_keys=public, clock=lambda: 1900000000)
        receipt = await verifier.reconcile_one(
            archive=archive, mongo=mongo, witness=witness, grant=grant,
            signatures=approval(grant, private),
        )
        assert receipt.committed_head == proposed
        assert receipt.committed_revision == old.revision + 1
        assert witness.positions[grant.binding_digest].head == proposed
        with pytest.raises(MementoWitnessDivergence):
            await verifier.reconcile_one(
                archive=archive, mongo=mongo, witness=witness, grant=grant,
                signatures=approval(grant, private),
            )
    asyncio.run(scenario())


def test_forged_signature_and_one_operator_rejected_before_mutation():
    async def scenario():
        archive, mongo, witness, old, proposed = await crash_candidate()
        private, public = keys()
        grant = setup_grant(archive, old, proposed)
        verifier = SignedMementoReconciler(public_keys=public, clock=lambda: 1900000000)
        signatures = approval(grant, private)
        bad = (signatures[0], RecoverySignature(signatures[1].signer_id, b"0" * 64))
        for attempted in (bad, (signatures[0], signatures[0]), (signatures[0],)):
            with pytest.raises(MementoRecoveryDenied):
                await verifier.reconcile_one(
                    archive=archive, mongo=mongo, witness=witness, grant=grant,
                    signatures=attempted,
                )
        assert witness.positions[grant.binding_digest] == old
    asyncio.run(scenario())


def test_reject_tampered_claims_missing_keys_duplicate_keys_and_expiration():
    async def scenario():
        archive, mongo, witness, old, proposed = await crash_candidate()
        private, public = keys()
        grant = setup_grant(archive, old, proposed)
        verifier = SignedMementoReconciler(public_keys=public, clock=lambda: 1900000000)
        signatures = approval(grant, private)
        altered = (
            replace(grant, incident_id="different"),
            replace(grant, source_thread_version=2),
            replace(grant, witness_revision=old.revision + 1),
            replace(grant, binding_digest="f" * 64),
        )
        for forged in altered:
            with pytest.raises((MementoRecoveryDenied, MementoWitnessDivergence)):
                await verifier.reconcile_one(archive=archive, mongo=mongo, witness=witness,
                                             grant=forged, signatures=signatures)
        expired = SignedMementoReconciler(public_keys=public, clock=lambda: 1900000300)
        with pytest.raises(MementoRecoveryDenied):
            await expired.reconcile_one(archive=archive, mongo=mongo, witness=witness,
                                        grant=grant, signatures=signatures)
        with pytest.raises(MementoRecoveryDenied):
            SignedMementoReconciler(public_keys={"a": public["operator-0"],
                                                     "b": public["operator-0"]})
        with pytest.raises(MementoRecoveryDenied):
            RecoveryGrant("X", grant.binding_digest, old.revision, old.head,
                          proposed, 1, 100, 1500)
    asyncio.run(scenario())


def test_retired_or_rolled_back_database_never_reconciled():
    async def scenario():
        archive, mongo, witness, old, proposed = await crash_candidate()
        private, public = keys()
        grant = setup_grant(archive, old, proposed)
        verifier = SignedMementoReconciler(public_keys=public, clock=lambda: 1900000000)
        signatures = approval(grant, private)
        scope = grant.binding_digest
        witness.positions[scope] = replace(old, retired=True)
        with pytest.raises(MementoWitnessDivergence):
            await verifier.reconcile_one(archive=archive, mongo=mongo, witness=witness,
                                         grant=grant, signatures=signatures)
        witness.positions[scope] = old
        mongo.head = MementoCatalogHead()
        with pytest.raises(MementoRecoveryDenied):
            await verifier.reconcile_one(archive=archive, mongo=mongo, witness=witness,
                                         grant=grant, signatures=signatures)
        assert witness.positions[scope] == old
    asyncio.run(scenario())


def test_rejected_or_unacknowledged_witness_cas_is_indeterminate():
    async def scenario():
        archive, mongo, witness, old, proposed = await crash_candidate()
        private, public = keys()
        grant = setup_grant(archive, old, proposed)
        verifier = SignedMementoReconciler(public_keys=public, clock=lambda: 1900000000)
        witness.reject = True
        with pytest.raises(MementoWitnessIndeterminate):
            await verifier.reconcile_one(archive=archive, mongo=mongo, witness=witness,
                                         grant=grant, signatures=approval(grant, private))
        assert witness.positions[grant.binding_digest] == old
    asyncio.run(scenario())


def test_source_version_race_is_rejected_before_cas():
    async def scenario():
        archive, mongo, witness, old, proposed = await crash_candidate()
        private, public = keys()
        grant = setup_grant(archive, old, proposed)
        verifier = SignedMementoReconciler(public_keys=public, clock=lambda: 1900000000)
        base_read = mongo.read_window
        calls = 0

        async def mutation(**kwargs):
            nonlocal calls
            page = await base_read(**kwargs)
            calls += 1
            if calls == 1:
                mongo.version += 1
            return page

        mongo.read_window = mutation
        with pytest.raises(MementoWitnessDivergence):
            await verifier.reconcile_one(archive=archive, mongo=mongo, witness=witness,
                                         grant=grant, signatures=approval(grant, private))
        assert witness.positions[grant.binding_digest] == old
    asyncio.run(scenario())