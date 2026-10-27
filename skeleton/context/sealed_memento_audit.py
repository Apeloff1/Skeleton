"""Bounded complete-chain audit of canonical encrypted memento archives.

An audit never upgrades retrieved language into instructions and never treats
an archive candidate head as authoritative. The reader and independent head
resolver must be supplied by the existing conversation owner. This module is
an integrity consumer, not another archive authority.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any, Callable

from skeleton.context.sealed_memento import ARCHIVE_WINDOW_MESSAGES, MementoCatalogHead
from skeleton.context.sealed_sandwich import (
    SealedContextBoundaryError, SealedContextLimitError, SealedContextReplayError,
)

_DOMAIN = b"skeleton.memento.full_audit.v1\x00"
_MAX_AUDIT_PAGES = 512


@dataclass(frozen=True, slots=True)
class MementoAuditReceipt:
    """Deterministic audit result, not a signature or a durable checkpoint."""

    head: MementoCatalogHead
    thread_version: int
    pages: int
    verified_records: int
    user_records: int
    llm_records: int
    work_records: int
    transcript_digest: str


def _record_bytes(record: Any) -> bytes:
    """Commit exact decrypted bytes and causal metadata without logging them."""
    payload = getattr(record, "payload", None)
    serial = getattr(record, "serial", None)
    stream = getattr(record, "stream", None)
    causal = getattr(record, "causal_serial", None)
    evidence_digest = getattr(record, "evidence_digest", None)
    evidence_ref = getattr(record, "evidence_ref", None)
    if (type(serial) is not int or serial < 1 or stream not in {"user", "llm", "work"}
            or type(payload) is not bytes or (causal is not None and
            (type(causal) is not int or not 1 <= causal < serial))):
        raise SealedContextReplayError("archive read returned malformed verified record")
    record_header = json.dumps(
        {"serial": serial, "stream": stream, "causal": causal,
         "evidence_digest": evidence_digest, "evidence_ref": evidence_ref,
         "payload_length": len(payload)},
        sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False,
    ).encode("utf-8")
    return (len(record_header).to_bytes(4, "big") + record_header
            + len(payload).to_bytes(8, "big") + payload)


def audit_memento_chain(
    *, archive: Any, read_window: Callable[..., Any],
    trusted_head: Callable[..., MementoCatalogHead],
    max_pages: int = _MAX_AUDIT_PAGES,
) -> MementoAuditReceipt:
    """Pin a full two-thousand-record-window scan against independent end reads.

    Each page must authenticate its frames and report its canonical version.
    The reader must check expected_starting_head against its own checkpoint.
    No accumulated plaintext or unbounded result list is retained.
    """
    if not callable(read_window) or not callable(trusted_head):
        raise SealedContextBoundaryError("canonical archive read and head authority required")
    if type(max_pages) is not int or not 1 <= max_pages <= _MAX_AUDIT_PAGES:
        raise SealedContextLimitError("audit page limit is invalid")
    before = trusted_head(archive=archive)
    if not isinstance(before, MementoCatalogHead):
        raise SealedContextBoundaryError("independent trusted audit head is missing")
    current = MementoCatalogHead()
    version: int | None = None
    totals = {"user": 0, "llm": 0, "work": 0}
    digest = hashlib.sha256(_DOMAIN)
    pages = 0
    while True:
        if pages >= max_pages:
            raise SealedContextLimitError("complete archive audit exceeded bounded page budget")
        page = read_window(
            archive=archive, after_serial=current.serial, limit=ARCHIVE_WINDOW_MESSAGES,
            expected_starting_head=current,
        )
        pages += 1
        if (not isinstance(page.starting_head, MementoCatalogHead)
                or not isinstance(page.verified_head, MementoCatalogHead)
                or page.starting_head != current or page.authoritative_head != before):
            raise SealedContextReplayError("archive audit checkpoint or trusted head changed")
        if type(page.source_thread_version) is not int or page.source_thread_version < 1:
            raise SealedContextReplayError("archive audit source version is invalid")
        if version is None:
            version = page.source_thread_version
        elif version != page.source_thread_version:
            raise SealedContextReplayError("canonical conversation changed during archive audit")
        records = page.records
        if not isinstance(records, tuple) or len(records) > ARCHIVE_WINDOW_MESSAGES:
            raise SealedContextLimitError("archive page exceeds verified record limit")
        for expected, record in enumerate(records, start=current.serial + 1):
            if record.serial != expected:
                raise SealedContextReplayError("archive audit detected a sequence gap")
            digest.update(_record_bytes(record))
            totals[record.stream] += 1
        if page.verified_head.serial != current.serial + len(records):
            raise SealedContextReplayError("archive page count disagrees with authenticated head")
        if page.verified_head.serial > before.serial:
            raise SealedContextReplayError("archive checkpoint exceeds canonical head")
        if sum(totals.values()) != page.verified_head.serial:
            raise SealedContextReplayError("archive stream totals disagree with global serial")
        current = page.verified_head
        if not page.has_more:
            if current != before:
                raise SealedContextReplayError("archive audit cannot reach its trusted tail")
            break
        if not records or current == before:
            raise SealedContextReplayError("archive audit reader claimed impossible progress")
    after = trusted_head(archive=archive)
    if after != before:
        raise SealedContextReplayError("archive changed before final audit attestation")
    return MementoAuditReceipt(
        before, version, pages, current.serial, totals["user"], totals["llm"],
        totals["work"], digest.hexdigest(),
    )
