"""Pinned serial-based retrieval with cross-page causality and drift rejection."""

from dataclasses import replace
import hashlib

import pytest

from skeleton.context.sealed_memento import (
    MementoCatalogHead, MementoRecord, SealedMementoArchive,
)
from skeleton.context.sealed_memento_retrieval import VerifiedMementoRetriever
from skeleton.context.sealed_sandwich import (
    ContextBinding, ContextSandwichCodec, SealedContextLimitError, SealedContextReplayError,
)
from skeleton.persistence.mongo_memento_repository import MongoMementoPage


class Window:
    def __init__(self, archive, records):
        head = MementoCatalogHead()
        self.entries = []
        for record in records:
            ciphertext, nxt = archive.seal(record, previous=head)
            self.entries.append((record.stream, ciphertext, head, nxt))
            head = nxt
        self.head = head
        self.archive = archive
        self.mutate = False

    def read(self, *, archive, after_serial=0, limit=2000,
             expected_starting_head=None):
        assert archive is self.archive
        selected = self.entries[after_serial:after_serial + limit]
        start = self.entries[after_serial - 1][3] if after_serial else MementoCatalogHead()
        if expected_starting_head is not None and start != expected_starting_head:
            raise SealedContextReplayError("pinned cursor changed")
        ending = selected[-1][3] if selected else start
        restored = archive.replay(((a,b) for a,b,_,_ in selected),
                                  starting_head=start, trusted_head=ending,
                                  max_messages=limit) if selected else ()
        head = replace(self.head, commitment="e" * 64) if self.mutate else self.head
        return MongoMementoPage(restored, start, ending, head, 5)


@pytest.fixture
def history():
    binding = ContextBinding("tenant", "owner", "thread", "model", "policy")
    archive = SealedMementoArchive(
        ContextSandwichCodec({"key": b"z" * 32}, active_key_id="key"), binding,
        work_verifier=lambda ref, digest, data:
            ref == "build:1" and hashlib.sha256(data).hexdigest() == digest,
    )
    records = [MementoRecord(n, "user", f"filler {n}".encode()) for n in range(1, 2001)]
    records.append(MementoRecord(2001, "user", b"skeleton dragon design", causal_serial=12))
    records.append(MementoRecord(2002, "llm", b"confirmed", causal_serial=2001))
    records.append(MementoRecord(2003, "work", b"real implementation", causal_serial=2001,
                                 evidence_ref="build:1",
                                 evidence_digest=hashlib.sha256(b"real implementation").hexdigest()))
    return archive, Window(archive, records)


def test_retrieve_query_crosses_window_and_reconstructs_causal_ancestors(history):
    archive, window = history
    r = VerifiedMementoRetriever(window.read).search(
        archive=archive, query="dragon design", limit=12, anchors=2,
    )
    assert [x.serial for x in r.records] == [12, 2001, 2002, 2003]
    assert r.pages_scanned == 2 and r.records_scanned == 2003
    assert r.trusted_head == window.head


def test_scanned_window_bound_rejects_incomplete_relevance(history):
    archive, window = history
    with pytest.raises(SealedContextLimitError):
        VerifiedMementoRetriever(window.read).search(
            archive=archive, query="dragon", max_pages=1,
        )


def test_drift_and_unknown_causal_serial_fail_closed(history):
    archive, window = history
    window.mutate = True
    with pytest.raises(SealedContextReplayError):
        VerifiedMementoRetriever(window.read).search(archive=archive, query="dragon")
    window.mutate = False
    with pytest.raises(SealedContextReplayError):
        VerifiedMementoRetriever(window.read).search(
            archive=archive, query="dragon", serial=9999,
        )


def test_retrieval_result_budget_is_hard_limit(history):
    archive, window = history
    with pytest.raises(SealedContextLimitError):
        VerifiedMementoRetriever(window.read).search(
            archive=archive, query="dragon", limit=2, anchors=1,
        )

def test_verified_retrieval_rejects_changed_page_checkpoint(history):
    archive, window = history
    original = window.read

    def corrupted(*, archive, after_serial=0, limit=2000,
                  expected_starting_head=None):
        if after_serial == 2000:
            expected_starting_head = replace(expected_starting_head, commitment="f" * 64)
        return original(archive=archive, after_serial=after_serial, limit=limit,
                        expected_starting_head=expected_starting_head)

    with pytest.raises(SealedContextReplayError):
        VerifiedMementoRetriever(corrupted).search(
            archive=archive, query="dragon", limit=12,
        )
