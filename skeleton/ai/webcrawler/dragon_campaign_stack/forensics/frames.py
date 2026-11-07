"""Exact selected-source anchor custody for the Dragon Atlas forensic extension.

Source bodies are only present in short-lived private Frame objects. Receipts
from other modules must never serialize Frame.text or source page bodies.
Canonical CrawlRun, current Mongo source policy and selected retrieval remain
the sole source of authority. No I/O, network, model or persistent write.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from urllib.parse import urlsplit

from ...operations import CrawlRun
from ..contracts import CampaignMandate, digest, ensure_snapshot_scope, integer
from ..policy_matrix import SourcePolicyProjection
from ..retrieval_fusion import RetrievalFusion


@dataclass(frozen=True)
class Anchor:
    source_id: str
    source_hash: str
    passage_hash: str
    host: str
    start: int
    end: int
    objective_ids: tuple[str, ...]
    chars: int
    anchor_digest: str


@dataclass(frozen=True)
class Frame:
    """Private exact text window; never embed in serializable review receipts."""
    anchor: Anchor
    text: str


@dataclass(frozen=True)
class FrameSet:
    mandate_digest: str
    snapshot_digest: str
    policy_digest: str
    retrieval_digest: str
    allowed_source_count: int
    excluded_source_count: int
    frames: tuple[Frame, ...]
    frame_set_digest: str

    @property
    def anchors(self) -> tuple[Anchor, ...]:
        return tuple(frame.anchor for frame in self.frames)


def bind_selected_frames(
    mandate: CampaignMandate,
    snapshot: dict[str, object],
    policy: SourcePolicyProjection,
    retrieval: RetrievalFusion,
    *,
    now: float,
    authorized: bool,
    max_frames: int = 64,
    max_sources: int = 32,
    max_total_chars: int = 48_000,
) -> FrameSet:
    """Fail closed on every stale/foreign/withheld or re-anchored passage."""
    mandate.admit(now=now, authorized=authorized)
    ensure_snapshot_scope(snapshot, mandate)
    integer(max_frames, "forensic frame cap", 1, 64)
    integer(max_sources, "forensic source cap", 1, 32)
    integer(max_total_chars, "forensic context cap", 1, 48_000)
    if not isinstance(policy, SourcePolicyProjection) or not isinstance(retrieval, RetrievalFusion):
        raise TypeError("typed current policy and retrieval required")
    run = CrawlRun.from_snapshot(snapshot).snapshot()
    snapshot_digest = run["snapshot_digest"]
    if policy.mandate_digest != mandate.fingerprint or retrieval.mandate_digest != mandate.fingerprint:
        raise PermissionError("cross-campaign forensic source inspection")
    if policy.source_snapshot_digest != snapshot_digest or retrieval.source_snapshot_digest != snapshot_digest:
        raise PermissionError("stale source or policy forensic inspection")
    if policy.training_authorized or policy.publication_authorized or retrieval.publication_authorized:
        raise PermissionError("forensic source inspection cannot grant knowledge rights")
    allowed = set(policy.allowed_source_ids)
    excluded = set(policy.excluded_source_ids)
    if allowed & excluded or allowed | excluded != set(run["sources"]):
        raise PermissionError("incomplete current source policy")
    if tuple(sorted(excluded)) != retrieval.excluded_sources:
        raise PermissionError("withdrawal set changed since retrieval")
    if len(retrieval.results) > max_frames:
        raise ValueError("too many selected forensic passages")
    frames: list[Frame] = []
    identities: set[tuple[str, int, int, str]] = set()
    source_ids: set[str] = set()
    chars = 0
    for row in retrieval.results:
        if row.source_id not in allowed:
            raise PermissionError("revoked source in forensic evidence")
        source = run["sources"][row.source_id]
        if not isinstance(source, dict):
            raise PermissionError("missing canonical source")
        content = source.get("text")
        if not isinstance(content, str):
            raise PermissionError("missing retained source text")
        host = urlsplit(source["canonical_url"]).hostname
        if (not host or host not in mandate.scope.allowed_hosts
                or row.canonical_url != source["canonical_url"]
                or row.host != host or row.source_hash != source["content_hash"]
                or row.trust != "unreviewed_external_content" or row.knowledge_verified
                or type(row.start) is not int or type(row.end) is not int
                or row.start < 0 or row.end <= row.start or row.end > len(content)):
            raise PermissionError("selected source anchor has invalid authority or range")
        text = content[row.start:row.end]
        if text != row.text or sha256(text.encode("utf-8")).hexdigest() != row.passage_hash:
            raise PermissionError("selected passage hash or span mismatch")
        if not row.matched_objective_ids or len(row.matched_objective_ids) > 32:
            raise PermissionError("source passage lacks bounded operator objective")
        if any(not isinstance(x, str) or not x or len(x) > 128 for x in row.matched_objective_ids):
            raise PermissionError("invalid operator objective identity")
        key = (row.source_id, row.start, row.end, row.passage_hash)
        if key in identities:
            raise ValueError("same anchored passage repeated")
        identities.add(key)
        source_ids.add(row.source_id)
        chars += len(text)
        if len(source_ids) > max_sources or chars > max_total_chars:
            raise ValueError("forensic selected text exceeds resource bounds")
        identity = {
            "source": row.source_id, "source_hash": row.source_hash,
            "passage": row.passage_hash, "start": row.start, "end": row.end,
            "host": host, "objectives": tuple(sorted(row.matched_objective_ids)),
        }
        frames.append(Frame(Anchor(
            row.source_id, row.source_hash, row.passage_hash, host,
            row.start, row.end, tuple(sorted(row.matched_objective_ids)),
            len(text), digest(identity),
        ), text))
    identity = {
        "mandate": mandate.fingerprint, "snapshot": snapshot_digest,
        "policy": policy.policy_digest, "retrieval": retrieval.fusion_digest,
        "anchors": [f.anchor.anchor_digest for f in frames],
        "capacity": (max_frames, max_sources, max_total_chars),
    }
    return FrameSet(
        mandate.fingerprint, snapshot_digest, policy.policy_digest,
        retrieval.fusion_digest, len(allowed), len(excluded),
        tuple(frames), digest(identity),
    )
