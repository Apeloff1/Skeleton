"""Full audited memento recovery: exact heads, boundaries, and fault injection."""

from dataclasses import replace
from hashlib import sha256

import pytest

from skeleton.context.sealed_memento import MementoCatalogHead, MementoRecord, SealedMementoArchive
from skeleton.context.sealed_memento_audit import audit_memento_chain
from skeleton.context.sealed_sandwich import (
    ContextBinding, ContextSandwichCodec, SealedContextBoundaryError,
    SealedContextLimitError, SealedContextReplayError,
)
from skeleton.persistence.mongo_memento_repository import MongoMementoPage


class History:
    def __init__(self, count=0):
        archive = SealedMementoArchive(
            ContextSandwichCodec({"key": b"0" * 32}, active_key_id="key"),
            ContextBinding("tenant", "owner", "thread", "model", "policy"),
        )
        self.archive = archive
        self.events = []
        current = MementoCatalogHead()
        for serial in range(1, count + 1):
            record = MementoRecord(serial, ("user" if serial % 2 else "llm"),
                                   f"exact {serial} 🐉".encode("utf-8"))
            wire, next_head = archive.seal(record, previous=current)
            self.events.append((record.stream, wire, current, next_head))
            current = next_head
        self.head = current
        self.tamper = None
        self.version = 4

    def trusted_head(self, *, archive):
        assert archive is self.archive
        return self.head

    def read_window(self, *, archive, after_serial=0, limit=2000, expected_starting_head=None):
        assert archive is self.archive
        beginning = self.events[after_serial - 1][3] if after_serial else MementoCatalogHead()
        assert beginning == expected_starting_head
        selected = self.events[after_serial:after_serial + limit]
        end = selected[-1][3] if selected else beginning
        records = archive.replay(((kind, wire) for kind, wire, _, _ in selected),
                                 starting_head=beginning, trusted_head=end,
                                 max_messages=limit) if selected else ()
        if self.tamper == "gap" and after_serial == 2000:
            records = records[1:]
        return MongoMementoPage(records, beginning, end, self.head, self.version)


def audited(history, **kwargs):
    return audit_memento_chain(archive=history.archive,
                               read_window=history.read_window,
                               trusted_head=history.trusted_head, **kwargs)


def test_empty_archive_has_valid_genesis_receipt():
    history = History()
    receipt = audited(history)
    assert receipt.verified_records == 0
    assert receipt.pages == 1 and receipt.head == MementoCatalogHead()
    assert receipt.transcript_digest == sha256(b"skeleton.memento.full_audit.v1\x00").hexdigest()


def test_complete_2000_window_recovery_is_lossless_and_bounded():
    history = History(2005)
    receipt = audited(history)
    assert receipt.pages == 2 and receipt.verified_records == 2005
    assert receipt.user_records == 1003 and receipt.llm_records == 1002
    assert receipt.work_records == 0 and receipt.head == history.head
    assert receipt.transcript_digest == audited(history).transcript_digest


def test_fails_closed_when_page_budget_truncates_tail():
    history = History(2001)
    with pytest.raises(SealedContextLimitError):
        audited(history, max_pages=1)


def test_gap_in_verified_pages_detected_even_if_reader_claims_head():
    history = History(2001)
    history.tamper = "gap"
    with pytest.raises(SealedContextReplayError):
        audited(history)


def test_source_version_drift_and_after_scan_head_drift_rejected():
    history = History(2001)
    native = history.read_window

    def drift(**kwargs):
        page = native(**kwargs)
        if kwargs["after_serial"]:
            return replace(page, source_thread_version=page.source_thread_version + 1)
        return page

    with pytest.raises(SealedContextReplayError):
        audit_memento_chain(archive=history.archive, read_window=drift,
                            trusted_head=history.trusted_head)
    count = 0

    def changed_head(*, archive):
        nonlocal count
        count += 1
        return MementoCatalogHead() if count > 1 else history.head

    with pytest.raises(SealedContextReplayError):
        audit_memento_chain(archive=history.archive, read_window=native,
                            trusted_head=changed_head)


def test_checkpoint_replacement_and_missing_independent_reader_are_denied():
    history = History(2001)

    def replaced(**kwargs):
        page = history.read_window(**kwargs)
        if kwargs["after_serial"] == 2000:
            return replace(page, starting_head=MementoCatalogHead())
        return page

    with pytest.raises(SealedContextReplayError):
        audit_memento_chain(archive=history.archive, read_window=replaced,
                            trusted_head=history.trusted_head)
    with pytest.raises(SealedContextBoundaryError):
        audit_memento_chain(archive=history.archive, read_window=None,
                            trusted_head=history.trusted_head)


def test_async_production_style_audit_is_exactly_equivalent_to_reference():
    import asyncio
    from skeleton.context.sealed_memento_audit import audit_memento_chain_async
    history = History(2001)

    async def head(**kwargs):
        return history.trusted_head(**kwargs)

    async def read(**kwargs):
        return history.read_window(**kwargs)

    receipt = asyncio.run(audit_memento_chain_async(
        archive=history.archive, read_window=read, trusted_head=head,
    ))
    assert receipt == audit_memento_chain(
        archive=history.archive, read_window=history.read_window,
        trusted_head=history.trusted_head,
    )


def test_async_audit_denies_midscan_authority_replacement_and_budget():
    import asyncio
    from skeleton.context.sealed_memento_audit import audit_memento_chain_async
    history = History(2001)

    async def changed(**kwargs):
        page = history.read_window(**kwargs)
        if kwargs["after_serial"] == 2000:
            return replace(page, authoritative_head=MementoCatalogHead())
        return page

    async def head(**kwargs):
        return history.trusted_head(**kwargs)

    with pytest.raises(SealedContextReplayError):
        asyncio.run(audit_memento_chain_async(
            archive=history.archive, read_window=changed, trusted_head=head,
        ))
    with pytest.raises(SealedContextLimitError):
        asyncio.run(audit_memento_chain_async(
            archive=history.archive, read_window=changed, trusted_head=head,
            max_pages=1,
        ))
