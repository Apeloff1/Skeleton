"""Adversarial correlated archival / provenance tests."""

from dataclasses import replace
import hashlib
from uuid import uuid4

import pytest

from skeleton.context.sealed_memento import (
    ARCHIVE_WINDOW_MESSAGES, MementoCatalogHead, MementoRecord,
    SealedMementoArchive, lexical_correlate,
)
from skeleton.context.sealed_sandwich import (
    ContextBinding, ContextSandwichCodec, SealedContextBoundaryError,
    SealedContextError, SealedContextLimitError, SealedContextReplayError,
)


@pytest.fixture
def fixture():
    binding = ContextBinding("tenant", "owner", str(uuid4()), "model", "policy")
    codec = ContextSandwichCodec({"key1": bytes(range(32))}, active_key_id="key1")
    def verifier(ref, digest, payload):
        return ref == "run:1" and digest == hashlib.sha256(b"verified artifact").hexdigest()
    return binding, SealedMementoArchive(codec, binding, work_verifier=verifier)


def _trail(archive):
    proof = hashlib.sha256(b"verified artifact").hexdigest()
    records = (
        MementoRecord(1, "user", b"Implement the game mapper"),
        MementoRecord(2, "llm", b"I implemented the mapper", causal_serial=1),
        MementoRecord(3, "work", b"verified artifact", causal_serial=1,
                      evidence_ref="run:1", evidence_digest=proof),
        MementoRecord(4, "user", "Next: harden Unicode 🐉".encode(), causal_serial=3),
        MementoRecord(5, "llm", b"Working", causal_serial=4),
    )
    head = MementoCatalogHead()
    entries = []
    for record in records:
        wire, head = archive.seal(record, previous=head)
        entries.append((record.stream, wire))
    return records, entries, head


def test_three_correlated_streams_seal_and_restore_exact_bytes(fixture):
    _, archive = fixture
    records, entries, head = _trail(archive)
    assert archive.replay(entries, trusted_head=head) == records
    assert (head.user.sequence, head.llm.sequence, head.work.sequence) == (2, 2, 1)
    assert [r.serial for r in lexical_correlate(records, query="mapper", serial=1)] == [1, 2, 3]


def test_memento_replay_detects_cross_stream_cut_reorder_or_wrong_head(fixture):
    _, archive = fixture
    _, entries, head = _trail(archive)
    for corrupted in (entries[:-1], entries[1:], entries[::-1], entries[:2] + entries[:1] + entries[2:]):
        with pytest.raises((SealedContextReplayError, SealedContextError)):
            archive.replay(corrupted, trusted_head=head)
    with pytest.raises(SealedContextReplayError):
        archive.replay(entries, trusted_head=replace(head, commitment="a" * 64))
    with pytest.raises((SealedContextBoundaryError, SealedContextReplayError)):
        archive.replay([("work", entries[0][1]), *entries[1:]], trusted_head=head)


def test_work_requires_independent_delivery_attestation(fixture):
    binding, archive = fixture
    digest = "a" * 64
    forged = MementoRecord(1, "work", b"just a promise", evidence_ref="run:1", evidence_digest=digest)
    with pytest.raises(SealedContextBoundaryError):
        archive.seal(forged, previous=MementoCatalogHead())
    no_proof = SealedMementoArchive(archive.codec, binding)
    with pytest.raises(SealedContextBoundaryError):
        no_proof.seal(
            replace(forged, evidence_digest=hashlib.sha256(b"verified artifact").hexdigest()),
            previous=MementoCatalogHead(),
        )
    with pytest.raises(SealedContextError):
        MementoRecord(1, "work", b"claimed work")


def test_multi_page_source_is_bounded_at_two_thousand(fixture):
    _, archive = fixture
    head = MementoCatalogHead()
    wires = []
    for i in range(1, ARCHIVE_WINDOW_MESSAGES + 1):
        wire, head = archive.seal(MementoRecord(i, "user", f"message {i}".encode()), previous=head)
        wires.append(("user", wire))
    recovered = archive.replay(wires, trusted_head=head)
    assert len(recovered) == 2000 and recovered[-1].serial == 2000
    with pytest.raises(SealedContextLimitError):
        archive.replay(wires, trusted_head=head, max_messages=1999)
    wire, larger = archive.seal(MementoRecord(2001, "user", b"message 2001"), previous=head)
    with pytest.raises(SealedContextLimitError):
        archive.replay(wires + [("user", wire)], trusted_head=larger)
    assert archive.replay([("user", wire)], trusted_head=larger, starting_head=head) == (
        MementoRecord(2001, "user", b"message 2001"),
    )


def test_cross_tenant_cannot_decrypt_and_untrusted_reference_is_not_auth(fixture):
    binding, archive = fixture
    _, entries, head = _trail(archive)
    intruder = SealedMementoArchive(archive.codec, replace(binding, tenant_id="other"))
    with pytest.raises(SealedContextBoundaryError):
        intruder.replay(entries, trusted_head=head)
    with pytest.raises(ValueError):
        lexical_correlate([], query="secret", limit=101)
