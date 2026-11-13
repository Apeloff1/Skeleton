"""Authenticated, serial-aware retrieval across bounded encrypted archive pages.

Reads ONLY from a canonical owner-backed page verifier. Retrieved language
remains lower-trust evidence and must be admitted through ContextCompiler;
recovery does not manufacture a privileged system/user instruction, prove a
model used all facts, or expand a native context window.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import re
from typing import Any, Callable

from skeleton.context.sealed_memento import (
    ARCHIVE_WINDOW_MESSAGES, MementoCatalogHead, MementoRecord,
)
from skeleton.context.sealed_sandwich import SealedContextLimitError, SealedContextReplayError

_WORD = re.compile(r"\w+", re.UNICODE)
_MAX_PAGES = 32


@dataclass(frozen=True, slots=True)
class CorrelatedRetrievalReceipt:
    """Pinned catalog evidence; no retrieved plaintext in audit metadata."""

    records: tuple[MementoRecord, ...]
    trusted_head: MementoCatalogHead
    source_version: int
    pages_scanned: int
    records_scanned: int
    query_sha256: str


def _search_terms(query: str) -> frozenset[str]:
    if not isinstance(query, str) or not 1 <= len(query) <= 2048:
        raise ValueError("retrieval query requires bounded nonempty text")
    return frozenset(word.casefold() for word in _WORD.findall(query))


class VerifiedMementoRetriever:
    """Deterministic lexical RAG over a verified multi-page archive.

    A repository read_window must pin checkpoint/tail heads independently of
    caller-provided values. The scan checks *every* page against one global
    trusted head and one canonical thread version. Candidate anchors are
    bounded and causal relatives are fetched by verified point reads.
    """

    def __init__(self, read_window: Callable[..., Any]) -> None:
        if not callable(read_window):
            raise TypeError("authoritative read_window callback required")
        self._read = read_window

    def search(
        self, *, archive: Any, query: str, serial: int | None = None,
        limit: int = 24, anchors: int = 6, max_pages: int = 16,
    ) -> CorrelatedRetrievalReceipt:
        terms = _search_terms(query)
        if type(serial) is not int and serial is not None:
            raise ValueError("serial must be a positive integer")
        if serial is not None and serial < 1:
            raise ValueError("serial must be a positive integer")
        if type(limit) is not int or not 1 <= limit <= 100:
            raise SealedContextLimitError("invalid retrieval result limit")
        if type(anchors) is not int or not 1 <= anchors <= min(limit, 32):
            raise SealedContextLimitError("invalid retrieval anchor limit")
        if type(max_pages) is not int or not 1 <= max_pages <= _MAX_PAGES:
            raise SealedContextLimitError("invalid verified scan budget")
        head = None
        version = None
        pages = 0
        visited = 0
        cursor = 0
        scored: list[tuple[int, int, MementoRecord]] = []
        # Never maintain more than anchor_limit candidate records between pages.
        while True:
            if pages >= max_pages:
                raise SealedContextLimitError("verified archive scan budget exceeded")
            page = self._read(
                archive=archive, after_serial=cursor, limit=ARCHIVE_WINDOW_MESSAGES,
                expected_starting_head=(preceding if cursor else MementoCatalogHead()),
            )
            if head is None:
                head = page.authoritative_head
                version = page.source_thread_version
            if page.authoritative_head != head or page.source_thread_version != version:
                raise SealedContextReplayError("canonical archive changed during retrieval")
            if page.starting_head.serial != cursor or (
                cursor and page.starting_head != preceding
            ):
                raise SealedContextReplayError("archive page cursor/continuity mismatch")
            if (page.verified_head.serial != cursor + len(page.records)
                    or page.has_more != (page.verified_head.serial < head.serial)):
                raise SealedContextReplayError("archive page count or tail flag is inconsistent")
            pages += 1
            for record in page.records:
                visited += 1
                words = {word.casefold() for word in _WORD.findall(
                    record.payload[:32768].decode("utf-8", errors="replace")
                )}
                relevance = len(words & terms)
                if serial is not None and (
                    record.serial == serial or record.causal_serial == serial
                ):
                    relevance += 1000
                if relevance:
                    scored.append((-relevance, record.serial, record))
            scored.sort(key=lambda row: (row[0], row[1]))
            del scored[anchors:]
            cursor = page.verified_head.serial
            preceding = page.verified_head
            if cursor > head.serial:
                raise SealedContextReplayError("verified archive exceeded independent trusted head")
            if not page.has_more:
                if page.verified_head != head:
                    raise SealedContextReplayError("archive missing terminal committed head")
                break
            if not page.records:
                raise SealedContextReplayError("verified archive made no progress")
        assert head is not None and version is not None
        found: dict[int, MementoRecord] = {}

        def point_fetch(index: int) -> MementoRecord:
            if index < 1 or index > head.serial:
                raise SealedContextReplayError("causal reference outside pinned archive")
            # One-record verified range: the starting checkpoint is drawn by
            # the repository from independently persisted canonical state.
            page = self._read(archive=archive, after_serial=index - 1, limit=1)
            if (page.authoritative_head != head or page.source_thread_version != version
                or page.starting_head.serial != index - 1
                or page.verified_head.serial != index
                or page.has_more != (index < head.serial)
                or len(page.records) != 1 or page.records[0].serial != index):
                raise SealedContextReplayError("causal point read lost canonical consistency")
            return page.records[0]

        def add_ancestors(item: MementoRecord) -> None:
            current = item
            visited_chain: set[int] = set()
            while current.serial not in found:
                if current.serial in visited_chain or len(found) >= limit:
                    raise SealedContextLimitError("causal closure exceeds strict result budget")
                visited_chain.add(current.serial)
                found[current.serial] = current
                if current.causal_serial is None:
                    break
                current = point_fetch(current.causal_serial)

        for _, _, item in scored:
            add_ancestors(item)
        if serial is not None:
            add_ancestors(point_fetch(serial))
        # Collect direct descendant answers/work receipts from the selected
        # anchors even if the child has no lexical overlap with the query.
        # Descendant scan never trusts model-generated evidence on its own.
        cursor = 0
        preceding = MementoCatalogHead()
        while cursor < head.serial and found:
            page = self._read(archive=archive, after_serial=cursor,
                              limit=ARCHIVE_WINDOW_MESSAGES,
                              expected_starting_head=preceding)
            if (page.authoritative_head != head or page.source_thread_version != version
                    or page.starting_head != preceding
                    or page.verified_head.serial != cursor + len(page.records)
                    or page.has_more != (page.verified_head.serial < head.serial)):
                raise SealedContextReplayError("archive changed during causal expansion")
            for item in page.records:
                if item.causal_serial in found and item.serial not in found:
                    add_ancestors(item)
            if page.verified_head.serial <= cursor:
                raise SealedContextReplayError("causal scan stalled")
            cursor = page.verified_head.serial
            preceding = page.verified_head
        return CorrelatedRetrievalReceipt(
            tuple(found[key] for key in sorted(found)), head, version,
            pages, visited, sha256(query.encode("utf-8")).hexdigest(),
        )
