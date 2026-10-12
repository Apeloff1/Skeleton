"""Bind Dragon Family progress to existing crawler evidence, never to client claims.

The canonical source of truth remains DragonKnowledgeLedger + DragonPracticeLab:
an approved lesson's evidence digest must still equal the current fact ledger.
This bridge is instantiated by the trusted producer, not the public API.

No network, SDK, scheduler or autonomous approval is implemented here.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from math import isfinite
from typing import Iterable
import json
import sqlite3

from .core import CrawlDocument, CrawlPolicy, destination_allowed
from .dragon_crawl_custody import CapturedSource, bind_crawl_evidence
from .dragon_family import DragonFamily, SourceReceipt, SourceSeed, _digest, _epoch, _owner, _source_id, _tokens, _uri
from .dragon_knowledge_ledger import DragonKnowledgeLedger
from .video_digest import VideoKnowledgeChunk


def _canonical(data: object) -> bytes:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False).encode("utf-8")


def _safe_url(url: str) -> None:
    _uri(url)
    # The source registry is never a transport permission. Nonetheless reject
    # local / literal private addresses as early as possible.
    if not CrawlPolicy().admits(url):
        raise ValueError("source violates crawler destination policy")
    from urllib.parse import urlsplit
    host = (urlsplit(url).hostname or "").lower().rstrip(".")
    if "." not in host or host.endswith((".localhost", ".local", ".internal",
                                          ".test", ".invalid")) or not destination_allowed(host):
        raise ValueError("non-public research source")


@dataclass(frozen=True)
class ApprovedSourceSnapshot:
    """Metadata from the existing verified provider/crawler, not a new owner."""
    source_id: str
    media: str
    url: str
    topics: tuple[str, ...]
    claim_id: str
    observed_at: float
    improvement: str = ""


class DragonFamilyCustodyBridge:
    """Read-only verifier for source receipts and adapter for producer events.

    An immutable content revision must appear in a source-bound evidence pass
    AND a currently consented independently reviewed practice lesson. Recheck
    the aggregated evidence fingerprint before accepting that revision.
    A revoked lesson or modified fact ledger immediately stops future growth.
    """
    def __init__(self, db: sqlite3.Connection, owner: str):
        _owner(owner)
        self.db = db
        self.owner = owner

    def verify(self, receipt: SourceReceipt) -> bool:
        """Callback for DragonFamily(approval=bridge.verify).

        The input is untrusted until canonical ledgers corroborate it.
        """
        if not isinstance(receipt, SourceReceipt):
            return False
        try:
            _source_id(receipt.source_id)
            _digest(receipt.content_digest)
            _digest(receipt.review_digest)
            _epoch(receipt.observed_at)
        except (ValueError, TypeError):
            return False
        try:
            rows = self.db.execute("""SELECT DISTINCT l.claim_id,l.evidence_digest
                FROM dragon_practice_lessons AS l
                JOIN dragon_evidence_passes AS e
                  ON e.owner=l.owner AND e.claim_id=l.claim_id
                WHERE l.owner=? AND l.consent=1 AND l.review_digest=?
                  AND e.source_id=? AND e.source_revision=?""",
                (self.owner, receipt.review_digest, receipt.source_id,
                 receipt.content_digest)).fetchall()
        except sqlite3.OperationalError:
            # Missing authoritative ledger is a hard deny, not an opportunity
            # to create a second in-memory approval cache.
            return False
        if len(rows) > 20:
            return False
        ledger = DragonKnowledgeLedger(self.db)
        for claim_id, recorded_evidence_digest in rows:
            try:
                belief = ledger.belief(self.owner, claim_id, authorized=True)
            except (ValueError, KeyError, sqlite3.DatabaseError):
                continue
            if belief.evidence_digest == recorded_evidence_digest:
                return True
        return False

    def family(self) -> DragonFamily:
        """Same SQLite connection and authority as the canonical Dragon Lab."""
        return DragonFamily(self.db, approval=self.verify)

    def article(self, snapshot: ApprovedSourceSnapshot,
                document: CrawlDocument) -> tuple[SourceSeed, SourceReceipt]:
        """Verify true text hash, transport provenance, and claimed review."""
        if not isinstance(snapshot, ApprovedSourceSnapshot) or snapshot.media != "article":
            raise ValueError("article adapter only accepts article snapshots")
        if not isinstance(document, CrawlDocument):
            raise ValueError("canonical crawler document required")
        if document.canonical_url != snapshot.url:
            raise ValueError("article canonical URL mismatch")
        _safe_url(snapshot.url)
        if document.fetched_at > snapshot.observed_at:
            raise ValueError("observed timestamp predates article fetch")
        # This enforces the existing exact-source SHA-256 and acquisition
        # provenance contracts, not merely data-class type correctness.
        bound = bind_crawl_evidence(
            snapshot.claim_id, (CapturedSource(snapshot.source_id, document),),
            (), authorized=True,
        )
        if len(bound.sources) != 1 or bound.sources[0].content_digest != document.content_hash:
            raise ValueError("article custody mismatch")
        seed = self._seed(snapshot)
        row = self._receipt(snapshot, document.content_hash)
        return seed, row

    def video(self, snapshot: ApprovedSourceSnapshot,
              chunks: Iterable[VideoKnowledgeChunk]) -> tuple[SourceSeed, SourceReceipt]:
        """Bind already-authorized video transcript/visual evidence to its digest.

        Only approved observations enter this method. It never downloads media,
        bypasses DRM, or invents a transcription; the media adapter owns those.
        """
        if not isinstance(snapshot, ApprovedSourceSnapshot) or snapshot.media != "video":
            raise ValueError("video adapter only accepts video snapshots")
        _safe_url(snapshot.url)
        items = tuple(chunks)
        if not 1 <= len(items) <= 1000:
            raise ValueError("video evidence chunk budget exceeded")
        serialized = []
        previous = -1
        bytes_total = 0
        for chunk in items:
            if not isinstance(chunk, VideoKnowledgeChunk):
                raise ValueError("untrusted video evidence")
            if chunk.source_url != snapshot.url or chunk.start_ms < 0 or chunk.start_ms < previous:
                raise ValueError("video source or time-code mismatch")
            if not 0 <= chunk.start_ms < chunk.end_ms <= 86400000:
                raise ValueError("invalid video time span")
            if not isinstance(chunk.text, str) or not chunk.text.strip() or len(chunk.text) > 20000:
                raise ValueError("empty or oversized video observation")
            _digest(chunk.chunk_id)
            if not chunk.modalities or not chunk.observation_ids or len(chunk.observation_ids) > 100:
                raise ValueError("video observations missing provenance")
            previous = chunk.start_ms
            bytes_total += len(chunk.text.encode("utf-8"))
            if bytes_total > 4_000_000:
                raise ValueError("video memory budget exceeded")
            serialized.append(dict(chunk=chunk.chunk_id,start=chunk.start_ms,
                                   end=chunk.end_ms,text=chunk.text,
                                   modalities=tuple(chunk.modalities),
                                   observations=tuple(chunk.observation_ids)))
        revision = sha256(_canonical({"source": snapshot.url, "chunks": serialized})).hexdigest()
        return self._seed(snapshot), self._receipt(snapshot, revision)

    def _seed(self, snapshot: ApprovedSourceSnapshot) -> SourceSeed:
        _source_id(snapshot.source_id)
        _safe_url(snapshot.url)
        if not isinstance(snapshot.claim_id, str) or not 1 <= len(snapshot.claim_id) <= 256:
            raise ValueError("missing evidence claim identity")
        topics = _tokens(snapshot.topics)
        if not topics:
            raise ValueError("source requires topic tags")
        _epoch(snapshot.observed_at)
        if not isinstance(snapshot.improvement, str) or len(snapshot.improvement) > 240:
            raise ValueError("invalid improvement note")
        return SourceSeed(snapshot.source_id, snapshot.url, snapshot.media, topics)

    def _receipt(self, snapshot: ApprovedSourceSnapshot,
                 content_digest: str) -> SourceReceipt:
        _digest(content_digest)
        # Resolve review fingerprint from exact previously approved evidence.
        # Arbitrary client-submitted digests are never accepted here.
        matching = self.db.execute("""SELECT DISTINCT l.review_digest
            FROM dragon_practice_lessons l JOIN dragon_evidence_passes e
              ON e.owner=l.owner AND e.claim_id=l.claim_id
            WHERE l.owner=? AND l.claim_id=? AND l.consent=1
              AND e.source_id=? AND e.source_revision=?""",
            (self.owner, snapshot.claim_id, snapshot.source_id, content_digest)).fetchall()
        for (review_digest,) in matching:
            receipt = SourceReceipt(snapshot.source_id, content_digest,
                                    review_digest, snapshot.observed_at,
                                    snapshot.improvement)
            if self.verify(receipt):
                return receipt
        raise PermissionError("source revision has no current canonical review")
