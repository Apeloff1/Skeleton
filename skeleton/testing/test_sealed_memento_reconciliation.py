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
from skeleton.persistence.sealed_memento_recovery_journal import RecoveryJournalError
from skeleton.persistence.sealed_memento_witness import (
    MementoWitnessDivergence, MementoWitnessIndeterminate, _binding_digest,
)
from skeleton.testing.test_sealed_memento_witness import add, setup


class ExternalRecoveryJournal:
    """Unit-test double of externally durable, linearizable incident storage."""

    def __init__(self):
        self.entries = {}
        self.reject = False
        self.fail_read = False
        self.fail_finish = False
        self.reserve_calls = 0

    async def reserve(self, *, record):
        self.reserve_calls += 1
        if self.reject:
            return False
        key = (record.binding_digest, record.incident_id)
        if key in self.entries:
            return False
        self.entries[key] = record
        return True

    async def read(self, *, binding_digest, incident_id):
        if self.fail_read:
            raise OSError("external journal unavailable")
        return self.entries.get((binding_digest, incident_id))

    async def complete(self, *, previous, successor):
        if self.fail_finish:
            raise OSError("journal completion interrupted")
        key = (previous.binding_digest, previous.incident_id)
        if self.entries.get(key) != previous:
            return False
        self.entries[key] = successor
        return True



def trusted_auth(public):
    return {
        "public_keys": public,
        "operator_principals": {
            key: "principal:" + key for key in public
        },
        "operator_roles": {
            key: ("security" if key.endswith("0") else "operations") for key in public
        },
    }


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
        verifier = SignedMementoReconciler(**trusted_auth(public), journal=ExternalRecoveryJournal(), clock=lambda: 1900000000)
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
        verifier = SignedMementoReconciler(**trusted_auth(public), journal=ExternalRecoveryJournal(), clock=lambda: 1900000000)
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
        verifier = SignedMementoReconciler(**trusted_auth(public), journal=ExternalRecoveryJournal(), clock=lambda: 1900000000)
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
        expired = SignedMementoReconciler(**trusted_auth(public), journal=ExternalRecoveryJournal(), clock=lambda: 1900000300)
        with pytest.raises(MementoRecoveryDenied):
            await expired.reconcile_one(archive=archive, mongo=mongo, witness=witness,
                                        grant=grant, signatures=signatures)
        with pytest.raises(MementoRecoveryDenied):
            SignedMementoReconciler(**trusted_auth({"a": public["operator-0"],
                                            "b": public["operator-0"]}),
                                    journal=ExternalRecoveryJournal())
        with pytest.raises(MementoRecoveryDenied):
            RecoveryGrant("X", grant.binding_digest, old.revision, old.head,
                          proposed, 1, 100, 1500)
    asyncio.run(scenario())


def test_retired_or_rolled_back_database_never_reconciled():
    async def scenario():
        archive, mongo, witness, old, proposed = await crash_candidate()
        private, public = keys()
        grant = setup_grant(archive, old, proposed)
        verifier = SignedMementoReconciler(**trusted_auth(public), journal=ExternalRecoveryJournal(), clock=lambda: 1900000000)
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
        verifier = SignedMementoReconciler(**trusted_auth(public), journal=ExternalRecoveryJournal(), clock=lambda: 1900000000)
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
        verifier = SignedMementoReconciler(**trusted_auth(public), journal=ExternalRecoveryJournal(), clock=lambda: 1900000000)
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


def test_unavailable_or_duplicate_incident_denied_before_witness_mutation():
    async def scenario():
        archive, mongo, witness, old, proposed = await crash_candidate()
        raw, public = keys()
        grant = setup_grant(archive, old, proposed)
        journal = ExternalRecoveryJournal()
        verifier = SignedMementoReconciler(
            **trusted_auth(public), journal=journal, clock=lambda: 1900000000,
        )
        journal.reject = True
        with pytest.raises(RecoveryJournalError):
            await verifier.reconcile_one(
                archive=archive, mongo=mongo, witness=witness,
                grant=grant, signatures=approval(grant, raw),
            )
        assert witness.positions[grant.binding_digest] == old
        journal.reject = False
        journal.fail_read = True
        with pytest.raises(RecoveryJournalError):
            await verifier.reconcile_one(
                archive=archive, mongo=mongo, witness=witness,
                grant=grant, signatures=approval(grant, raw),
            )
        assert witness.positions[grant.binding_digest] == old
        # The reserve succeeded but read confirmation was lost. The incident
        # must remain spent: manual investigation is required.
        journal.fail_read = False
        with pytest.raises(RecoveryJournalError):
            await verifier.reconcile_one(
                archive=archive, mongo=mongo, witness=witness,
                grant=grant, signatures=approval(grant, raw),
            )
        assert journal.reserve_calls == 3
        assert witness.positions[grant.binding_digest] == old
    asyncio.run(scenario())


def test_completed_recovery_has_single_use_durable_receipt():
    async def scenario():
        archive, mongo, witness, old, proposed = await crash_candidate()
        raw, public = keys()
        journal = ExternalRecoveryJournal()
        grant = setup_grant(archive, old, proposed)
        verifier = SignedMementoReconciler(
            **trusted_auth(public), journal=journal, clock=lambda: 1900000000,
        )
        receipt = await verifier.reconcile_one(
            archive=archive, mongo=mongo, witness=witness,
            grant=grant, signatures=approval(grant, raw),
        )
        entry = await journal.read(
            binding_digest=grant.binding_digest, incident_id=grant.incident_id,
        )
        assert receipt.committed_head == proposed
        assert entry.state == "completed" and len(entry.receipt_digest) == 64
        assert entry.candidate_commitment == proposed.commitment
        assert entry.approvers == ("operator-0", "operator-1")
        assert journal.reserve_calls == 1
        assert not await journal.reserve(record=entry)
    asyncio.run(scenario())


def test_post_commit_journal_failure_is_indeterminate_not_success():
    async def scenario():
        archive, mongo, witness, old, proposed = await crash_candidate()
        raw, public = keys()
        journal = ExternalRecoveryJournal()
        journal.fail_finish = True
        grant = setup_grant(archive, old, proposed)
        verifier = SignedMementoReconciler(
            **trusted_auth(public), journal=journal, clock=lambda: 1900000000,
        )
        with pytest.raises(MementoWitnessIndeterminate):
            await verifier.reconcile_one(
                archive=archive, mongo=mongo, witness=witness,
                grant=grant, signatures=approval(grant, raw),
            )
        assert witness.positions[grant.binding_digest].head == proposed
        entry = await journal.read(
            binding_digest=grant.binding_digest, incident_id=grant.incident_id,
        )
        assert entry.state == "reserved" and entry.receipt_digest is None
    asyncio.run(scenario())


def test_untrusted_recovery_journal_not_optional():
    _, public = keys()
    with pytest.raises(MementoRecoveryDenied):
        SignedMementoReconciler(**trusted_auth(public), journal=None)


def test_two_different_keys_from_same_operator_are_not_two_approvals():
    async def scenario():
        archive, mongo, witness, old, proposed = await crash_candidate()
        raw, public = keys()
        grant = setup_grant(archive, old, proposed)
        registry = trusted_auth(public)
        registry["operator_principals"]["operator-1"] = "principal:operator-0"
        verifier = SignedMementoReconciler(
            **registry, journal=ExternalRecoveryJournal(), clock=lambda: 1900000000,
        )
        with pytest.raises(MementoRecoveryDenied):
            await verifier.reconcile_one(
                archive=archive, mongo=mongo, witness=witness, grant=grant,
                signatures=approval(grant, raw),
            )
        assert witness.positions[grant.binding_digest] == old
    asyncio.run(scenario())


def test_operator_approval_requires_distinct_separation_roles():
    _, public = keys()
    registry = trusted_auth(public)
    registry["operator_roles"]["operator-1"] = "security"
    with pytest.raises(MementoRecoveryDenied):
        SignedMementoReconciler(**registry, journal=ExternalRecoveryJournal())
    registry = trusted_auth(public)
    registry["operator_principals"].pop("operator-1")
    with pytest.raises(MementoRecoveryDenied):
        SignedMementoReconciler(**registry, journal=ExternalRecoveryJournal())


def test_read_only_incident_triage_covers_all_recovery_crash_windows():
    from skeleton.persistence.sealed_memento_recovery_journal import (
        claim_record, completed_record, inspect_recovery_incident,
    )
    from skeleton.persistence.sealed_memento_witness import WitnessPosition

    async def scenario():
        archive, mongo, witness, old, proposed = await crash_candidate()
        private, public = keys()
        grant = setup_grant(archive, old, proposed)
        journal = ExternalRecoveryJournal()
        claim = claim_record(grant, tuple(s.signer_id for s in approval(grant, private)))
        assert await journal.reserve(record=claim)
        args = dict(archive=archive, incident_id=grant.incident_id,
                    mongo=mongo, witness=witness, journal=journal)
        reserved = await inspect_recovery_incident(**args)
        assert reserved.classification == "reserved_unwitnessed"
        assert reserved.manual_intervention_required
        successor = WitnessPosition(grant.binding_digest, old.revision + 1, proposed)
        assert await witness.compare_and_set(binding_digest=grant.binding_digest,
                                             previous=old, successor=successor)
        incomplete = await inspect_recovery_incident(**args)
        assert incomplete.classification == "receipt_missing"
        assert incomplete.manual_intervention_required
        complete = completed_record(claim, grant.signed_bytes())
        assert await journal.complete(previous=claim, successor=complete)
        stable = await inspect_recovery_incident(**args)
        assert stable.classification == "completed_verified"
        assert not stable.manual_intervention_required
    asyncio.run(scenario())


def test_read_only_incident_triage_detects_evidence_loss_and_mutation():
    from skeleton.persistence.sealed_memento_recovery_journal import (
        claim_record, inspect_recovery_incident,
    )

    async def scenario():
        archive, mongo, witness, old, proposed = await crash_candidate()
        raw, public = keys()
        grant = setup_grant(archive, old, proposed)
        journal = ExternalRecoveryJournal()
        args = dict(archive=archive, incident_id=grant.incident_id,
                    mongo=mongo, witness=witness, journal=journal)
        with pytest.raises(RecoveryJournalError):
            await inspect_recovery_incident(**args)
        record = claim_record(grant, tuple(s.signer_id for s in approval(grant, raw)))
        assert await journal.reserve(record=record)
        mongo.version += 1
        with pytest.raises(MementoWitnessDivergence):
            await inspect_recovery_incident(**args)
        mongo.version -= 1
        scope = grant.binding_digest
        witness.positions[scope] = replace(old, retired=True)
        with pytest.raises(Exception):
            await inspect_recovery_incident(**args)
    asyncio.run(scenario())
