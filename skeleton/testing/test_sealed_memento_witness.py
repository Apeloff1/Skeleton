"""Independently witnessed memento anti-rollback and crash-window drills."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from types import SimpleNamespace

import pytest

from skeleton.context.sealed_memento import (
    MementoCatalogHead, MementoRecord, SealedMementoArchive, _advance, stream_binding,
)
from skeleton.context.sealed_memento_audit import audit_memento_chain_async
from skeleton.context.sealed_sandwich import (
    ContextBinding, ContextSandwichCodec, SealedContextBoundaryError,
    SealedContextReplayError,
)
from skeleton.persistence.sealed_memento_witness import (
    MementoWitnessDivergence, MementoWitnessIndeterminate,
    MementoWitnessUnavailable, WitnessedMongoMementoAuthority, WitnessPosition,
    _binding_digest,
)


class ExternalMemoryWitness:
    """Test double only; never use this volatile witness in production."""

    def __init__(self, position):
        self.positions = {position.binding_digest: position}
        self.reject = False
        self.fail = False
        self.flip_confirmation = False
        self.calls = 0

    async def read(self, *, binding_digest):
        if self.fail:
            raise OSError("simulated witness outage")
        item = self.positions.get(binding_digest)
        if self.flip_confirmation and self.calls:
            return replace(item, revision=item.revision + 1)
        return item

    async def compare_and_set(self, *, binding_digest, previous, successor):
        self.calls += 1
        if self.fail:
            raise OSError("witness refused commit")
        if self.reject or self.positions.get(binding_digest) != previous:
            return False
        if successor.binding_digest != binding_digest or successor.revision != previous.revision + 1:
            return False
        if previous.retired or successor.head.serial < previous.head.serial:
            return False
        if not successor.retired and successor.head.serial != previous.head.serial + 1:
            return False
        self.positions[binding_digest] = successor
        return True


class TransactionalMongoDouble:
    """Models the encrypted canonical-head commit point and retired fencing."""

    def __init__(self, archive):
        self.archive = archive
        self.head = MementoCatalogHead()
        self.rows = []
        self.retired = False
        self.version = 1
        self.fail_purge = False
        self.publish_calls = 0

    async def trusted_head(self, *, archive):
        if self.retired:
            raise SealedContextBoundaryError("conversation retired")
        assert archive is self.archive
        return self.head

    async def publish(self, *, archive, expected_head, expected_thread_version, stream, ciphertext):
        self.publish_calls += 1
        assert archive is self.archive
        if self.retired or expected_thread_version != self.version:
            raise SealedContextBoundaryError("conversation invalid")
        if expected_head != self.head:
            raise SealedContextReplayError("stale head")
        record, head = archive.verify_append(stream, ciphertext, previous=self.head)
        self.rows.append((stream, ciphertext, record))
        self.head = head
        return head

    async def read_window(self, *, archive, after_serial=0, limit=2000,
                          expected_starting_head=None):
        assert archive is self.archive
        starts = [MementoCatalogHead()]
        for stream, ciphertext, _record in self.rows:
            frame = archive.codec.open(
                ciphertext, binding=stream_binding(archive.binding, stream),
                previous=starts[-1].stream_head(stream),
            )
            starts.append(_advance(starts[-1], stream, frame.head, ciphertext))
        beginning = starts[after_serial]
        if expected_starting_head is not None and beginning != expected_starting_head:
            raise SealedContextReplayError("bad pinned resume cursor")
        selected = self.rows[after_serial:after_serial + limit]
        ending = starts[after_serial + len(selected)]
        records = archive.replay(
            ((stream, wire) for stream, wire, _ in selected),
            starting_head=beginning, trusted_head=ending,
        ) if selected else ()
        return SimpleNamespace(
            records=records, starting_head=beginning, verified_head=ending,
            authoritative_head=self.head, source_thread_version=self.version,
            has_more=ending.serial < self.head.serial,
        )

    async def retire_thread(self, *, tenant_id, owner_id, thread_id):
        assert (tenant_id, owner_id, thread_id) == (
            self.archive.binding.tenant_id, self.archive.binding.owner_id,
            self.archive.binding.conversation_id,
        )
        if self.fail_purge:
            raise OSError("simulated failed purge")
        count = len(self.rows)
        self.rows.clear()
        self.retired = True
        return count


def setup():
    archive = SealedMementoArchive(
        ContextSandwichCodec({"key": b"a" * 32}, active_key_id="key"),
        ContextBinding("tenant", "owner", "thread", "model", "policy"),
    )
    position = WitnessPosition(_binding_digest(archive), 1, MementoCatalogHead())
    witness = ExternalMemoryWitness(position)
    mongo = TransactionalMongoDouble(archive)
    return archive, mongo, witness, WitnessedMongoMementoAuthority(mongo, witness=witness)


async def add(archive, guarded, serial=1):
    previous = await guarded.trusted_head(archive=archive)
    wire, expected = archive.seal(
        MementoRecord(serial, "user", f"message:{serial}".encode()), previous=previous,
    )
    observed = await guarded.publish(
        archive=archive, expected_head=previous, expected_thread_version=1,
        stream="user", ciphertext=wire,
    )
    assert observed == expected
    return expected


def test_witnessed_publish_and_pinned_read_across_restart():
    async def scenario():
        a, m, w, guard = setup()
        await add(a, guard)
        await add(a, guard, 2)
        restarted = WitnessedMongoMementoAuthority(m, witness=w)
        page = await restarted.read_window(archive=a)
        assert len(page.records) == 2
        assert page.authoritative_head == await restarted.trusted_head(archive=a)
    asyncio.run(scenario())


def test_missing_or_cross_scope_witness_never_auto_provisions():
    async def scenario():
        a, m, w, guard = setup()
        w.positions.clear()
        with pytest.raises(MementoWitnessUnavailable):
            await guard.trusted_head(archive=a)
        w.positions[_binding_digest(a)] = WitnessPosition("0" * 64, 1, MementoCatalogHead())
        with pytest.raises(MementoWitnessUnavailable):
            await guard.trusted_head(archive=a)
        assert m.publish_calls == 0
    asyncio.run(scenario())


def test_rewound_database_with_valid_old_ciphertext_is_denied():
    async def scenario():
        a, m, w, guard = setup()
        await add(a, guard)
        m.head = MementoCatalogHead()
        m.rows = []
        with pytest.raises(MementoWitnessDivergence):
            await guard.trusted_head(archive=a)
        with pytest.raises(MementoWitnessDivergence):
            await guard.read_window(archive=a)
    asyncio.run(scenario())


def test_failed_external_cas_is_indeterminate_and_denies_recovery():
    async def scenario():
        a, m, w, guard = setup()
        w.reject = True
        before = await guard.trusted_head(archive=a)
        wire, _ = a.seal(MementoRecord(1, "user", b"proof"), previous=before)
        with pytest.raises(MementoWitnessIndeterminate):
            await guard.publish(
                archive=a, expected_head=before, expected_thread_version=1,
                stream="user", ciphertext=wire,
            )
        assert m.head.serial == 1
        with pytest.raises(MementoWitnessDivergence):
            await guard.read_window(archive=a)
    asyncio.run(scenario())


def test_witness_outage_denies_before_mongo_write():
    async def scenario():
        a, m, w, guard = setup()
        w.fail = True
        with pytest.raises(MementoWitnessUnavailable):
            await guard.trusted_head(archive=a)
        assert m.publish_calls == 0
    asyncio.run(scenario())


def test_stale_expected_head_is_rejected_without_writing():
    async def scenario():
        a, m, w, guard = setup()
        await add(a, guard)
        wire, _ = a.seal(MementoRecord(1, "user", b"stale"), previous=MementoCatalogHead())
        with pytest.raises(MementoWitnessDivergence):
            await guard.publish(
                archive=a, expected_head=MementoCatalogHead(),
                expected_thread_version=1, stream="user", ciphertext=wire,
            )
        assert m.publish_calls == 1
    asyncio.run(scenario())


def test_tombstone_precedes_deletion_and_blocks_reactivation():
    async def scenario():
        a, m, w, guard = setup()
        await add(a, guard)
        deleted = await guard.retire_thread(archive=a)
        assert deleted == 1 and m.retired
        assert w.positions[_binding_digest(a)].retired
        with pytest.raises(SealedContextBoundaryError):
            await guard.trusted_head(archive=a)
        with pytest.raises(SealedContextBoundaryError):
            await guard.retire_thread(archive=a)
    asyncio.run(scenario())


def test_failed_mongo_deletion_stays_tombstoned():
    async def scenario():
        a, m, w, guard = setup()
        await add(a, guard)
        m.fail_purge = True
        with pytest.raises(MementoWitnessIndeterminate):
            await guard.retire_thread(archive=a)
        assert len(m.rows) == 1 and w.positions[_binding_digest(a)].retired
        with pytest.raises(SealedContextBoundaryError):
            await guard.read_window(archive=a)
    asyncio.run(scenario())


def test_independent_async_audit_uses_witnessed_authority():
    async def scenario():
        a, m, w, guard = setup()
        await add(a, guard)
        await add(a, guard, 2)
        receipt = await audit_memento_chain_async(
            archive=a, read_window=guard.read_window, trusted_head=guard.trusted_head,
        )
        assert receipt.verified_records == 2 and receipt.pages == 1
        assert receipt.head == await guard.trusted_head(archive=a)
    asyncio.run(scenario())


def test_external_post_commit_confirmation_failure_is_indeterminate():
    async def scenario():
        a, m, w, guard = setup()
        w.flip_confirmation = True
        before = await guard.trusted_head(archive=a)
        wire, _ = a.seal(MementoRecord(1, "user", b"payload"), previous=before)
        with pytest.raises(MementoWitnessIndeterminate):
            await guard.publish(
                archive=a, expected_head=before, expected_thread_version=1,
                stream="user", ciphertext=wire,
            )
        assert m.publish_calls == 1
    asyncio.run(scenario())


def test_recovery_inspection_consistent_and_single_unwitnessed_commit():
    from skeleton.persistence.sealed_memento_recovery import inspect_memento_recovery

    async def scenario():
        a, m, w, guard = setup()
        matching = await inspect_memento_recovery(archive=a, mongo=m, witness=w)
        assert matching.classification == "consistent" and not matching.manual_intervention_required
        await add(a, guard)
        w.reject = True
        wire, _ = a.seal(MementoRecord(2, "user", b"after crash"), previous=m.head)
        with pytest.raises(MementoWitnessIndeterminate):
            await guard.publish(
                archive=a, expected_head=m.head, expected_thread_version=1,
                stream="user", ciphertext=wire,
            )
        inspected = await inspect_memento_recovery(archive=a, mongo=m, witness=w)
        assert inspected.classification == "single_verified_unwitnessed_commit"
        assert inspected.witness_serial == 1 and inspected.mongo_serial == 2
        assert inspected.candidate_serial == 2 and inspected.manual_intervention_required
        assert w.positions[_binding_digest(a)].head.serial == 1
    asyncio.run(scenario())


def test_recovery_inspection_reports_rollback_fork_and_multiple_commits():
    from skeleton.persistence.sealed_memento_recovery import inspect_memento_recovery

    async def scenario():
        a, m, w, guard = setup()
        await add(a, guard)
        committed = m.head
        m.head = MementoCatalogHead()
        rollback = await inspect_memento_recovery(archive=a, mongo=m, witness=w)
        assert rollback.classification == "database_rollback_or_loss"
        m.head = replace(committed, commitment="e" * 64)
        fork = await inspect_memento_recovery(archive=a, mongo=m, witness=w)
        assert fork.classification == "same_serial_fork_or_corruption"
        m.head = committed
        w.positions[_binding_digest(a)] = WitnessPosition(_binding_digest(a), 1, MementoCatalogHead())
        await m.publish(
            archive=a, expected_head=m.head, expected_thread_version=1,
            stream="user", ciphertext=a.seal(
                MementoRecord(2, "user", b"next"), previous=m.head,
            )[0],
        )
        multi = await inspect_memento_recovery(archive=a, mongo=m, witness=w)
        assert multi.classification == "unwitnessed_multiple_commits"
    asyncio.run(scenario())


def test_recovery_inspection_retired_tombstone_and_stability_race():
    from skeleton.persistence.sealed_memento_recovery import inspect_memento_recovery
    from skeleton.context.sealed_sandwich import SealedContextReplayError

    async def scenario():
        a, m, w, guard = setup()
        await add(a, guard)
        await guard.retire_thread(archive=a)
        retired = await inspect_memento_recovery(archive=a, mongo=m, witness=w)
        assert retired.classification == "retired" and retired.mongo_serial is None
        assert retired.manual_intervention_required
        b, mongo, store, guarded = setup()
        original = store.read
        calls = 0

        async def changing(*, binding_digest):
            nonlocal calls
            calls += 1
            item = await original(binding_digest=binding_digest)
            return replace(item, revision=item.revision + 1) if calls == 2 else item

        store.read = changing
        with pytest.raises(SealedContextReplayError):
            await inspect_memento_recovery(archive=b, mongo=mongo, witness=store)
    asyncio.run(scenario())


def test_recovery_inspection_denies_missing_witness_and_forged_suffix():
    from skeleton.persistence.sealed_memento_recovery import inspect_memento_recovery

    async def scenario():
        a, m, w, guard = setup()
        w.positions.clear()
        with pytest.raises(MementoWitnessUnavailable):
            await inspect_memento_recovery(archive=a, mongo=m, witness=w)
        w.positions[_binding_digest(a)] = WitnessPosition(_binding_digest(a), 1, MementoCatalogHead())
        wire, _ = a.seal(MementoRecord(1, "user", b"unwitnessed"), previous=m.head)
        await m.publish(
            archive=a, expected_head=m.head, expected_thread_version=1,
            stream="user", ciphertext=wire,
        )
        raw_read = m.read_window

        async def altered(**kwargs):
            page = await raw_read(**kwargs)
            return SimpleNamespace(**{**vars(page), "authoritative_head": MementoCatalogHead()})

        m.read_window = altered
        with pytest.raises(MementoWitnessDivergence):
            await inspect_memento_recovery(archive=a, mongo=m, witness=w)
    asyncio.run(scenario())


def test_canonical_governed_deletion_needs_no_decryption_key():
    from skeleton.context.sealed_memento import encode_catalog_head

    async def scenario():
        a, m, w, guard = setup()
        await add(a, guard)

        async def authoritative_thread(query):
            assert query == {"_id": "thread", "tenant_id": "tenant", "owner_id": "owner"}
            return {"_sealed_memento_binding": _binding_digest(a),
                    "_sealed_memento_head": encode_catalog_head(m.head)}

        m.conversation = SimpleNamespace(threads=SimpleNamespace(find_one=authoritative_thread))
        removed = await guard.retire_bound_thread(
            tenant_id="tenant", owner_id="owner", thread_id="thread",
            binding_digest=_binding_digest(a),
        )
        assert removed == 1 and m.retired and not m.rows
        assert w.positions[_binding_digest(a)].retired
    asyncio.run(scenario())


def test_governed_deletion_retry_after_tombstone_purges_remaining_frames():
    from skeleton.context.sealed_memento import encode_catalog_head

    async def scenario():
        a, m, w, guard = setup()
        await add(a, guard)

        async def authoritative_thread(query):
            return {"_sealed_memento_binding": _binding_digest(a),
                    "_sealed_memento_head": encode_catalog_head(m.head)}

        m.conversation = SimpleNamespace(threads=SimpleNamespace(find_one=authoritative_thread))
        m.fail_purge = True
        args = dict(tenant_id="tenant", owner_id="owner", thread_id="thread",
                    binding_digest=_binding_digest(a))
        with pytest.raises(MementoWitnessIndeterminate):
            await guard.retire_bound_thread(**args)
        first_position = w.positions[_binding_digest(a)]
        assert first_position.retired and len(m.rows) == 1
        m.fail_purge = False
        assert await guard.retire_bound_thread(**args) == 1
        assert w.positions[_binding_digest(a)] == first_position
        assert m.retired and not m.rows
    asyncio.run(scenario())


def test_canonical_bound_deletion_does_not_accept_untrusted_binding_or_tenant():
    from skeleton.context.sealed_memento import encode_catalog_head

    async def scenario():
        a, m, w, guard = setup()
        await add(a, guard)

        async def authoritative_thread(query):
            if query["tenant_id"] != "tenant":
                return None
            return {"_sealed_memento_binding": _binding_digest(a),
                    "_sealed_memento_head": encode_catalog_head(m.head)}

        m.conversation = SimpleNamespace(threads=SimpleNamespace(find_one=authoritative_thread))
        for extra in ({"tenant_id": "other"}, {"binding_digest": "b" * 64}):
            args = {"tenant_id": "tenant", "owner_id": "owner", "thread_id": "thread",
                    "binding_digest": _binding_digest(a), **extra}
            with pytest.raises(SealedContextBoundaryError):
                await guard.retire_bound_thread(**args)
        assert not w.positions[_binding_digest(a)].retired
        assert len(m.rows) == 1
    asyncio.run(scenario())

def test_retired_deletion_retries_after_inflight_mongo_head_change():
    """Irreversible erasure beats a stale retired head, never before retirement."""
    from skeleton.context.sealed_memento import encode_catalog_head

    async def scenario():
        a, m, w, guard = setup()
        await add(a, guard)

        async def canonical(query):
            return {"_sealed_memento_binding": _binding_digest(a),
                    "_sealed_memento_head": encode_catalog_head(m.head)}

        m.conversation = SimpleNamespace(threads=SimpleNamespace(find_one=canonical))
        args = dict(tenant_id="tenant", owner_id="owner", thread_id="thread",
                    binding_digest=_binding_digest(a))
        m.fail_purge = True
        with pytest.raises(MementoWitnessIndeterminate):
            await guard.retire_bound_thread(**args)
        retired = w.positions[_binding_digest(a)]
        assert retired.retired
        # A prepared operation committed in the race before the Mongo fence.
        ciphertext, successor = a.seal(
            MementoRecord(2, "llm", b"late concurrent reply"), previous=m.head,
        )
        m.rows.append(("llm", ciphertext, MementoRecord(2, "llm", b"late concurrent reply")))
        m.head = successor
        m.fail_purge = False
        assert await guard.retire_bound_thread(**args) == 2
        assert not m.rows and m.retired
        assert w.positions[_binding_digest(a)] == retired

    asyncio.run(scenario())


def test_unretired_mismatch_still_denies_physical_deletion():
    from skeleton.context.sealed_memento import encode_catalog_head

    async def scenario():
        a, m, w, guard = setup()
        await add(a, guard)
        ciphertext, successor = a.seal(
            MementoRecord(2, "user", b"unwitnessed"), previous=m.head,
        )
        m.rows.append(("user", ciphertext, MementoRecord(2, "user", b"unwitnessed")))
        m.head = successor

        async def canonical(query):
            return {"_sealed_memento_binding": _binding_digest(a),
                    "_sealed_memento_head": encode_catalog_head(m.head)}

        m.conversation = SimpleNamespace(threads=SimpleNamespace(find_one=canonical))
        with pytest.raises(MementoWitnessDivergence):
            await guard.retire_bound_thread(
                tenant_id="tenant", owner_id="owner", thread_id="thread",
                binding_digest=_binding_digest(a),
            )
        assert not w.positions[_binding_digest(a)].retired
        assert len(m.rows) == 2

    asyncio.run(scenario())
