"""ArchiveX temporal change signals and evidence drift detection.

Signals distinguish unchanged snapshots, additions, removals, and rewrites.
These are provenance observations, not factual truth assessments.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from difflib import SequenceMatcher

from .archivex import ArchiveX, ArchiveXSnapshot


class ArchiveSignalKind(str, Enum):
    FIRST_SEEN = "first_seen"
    UNCHANGED = "unchanged"
    REVISED = "revised"
    REMOVED = "removed"
    EXPANDED = "expanded"


@dataclass(frozen=True)
class ArchiveSignal:
    source_url: str
    earlier_id: str | None
    later_id: str
    kind: ArchiveSignalKind
    similarity: float
    added_chars: int
    removed_chars: int
    earlier_digest: str | None
    later_digest: str


@dataclass(frozen=True)
class ArchiveDriftPolicy:
    max_text_chars: int = 200000
    unchanged_similarity: float = 0.999
    expansion_threshold: float = 0.2
    max_comparison_units: int = 512


def _text(body: bytes, policy: ArchiveDriftPolicy) -> str:
    if len(body) > policy.max_text_chars * 4:
        raise ValueError("snapshot exceeds drift comparison budget")
    try:
        decoded = body.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("drift analysis requires UTF-8 text") from exc
    if len(decoded) > policy.max_text_chars:
        raise ValueError("snapshot text budget exceeded")
    return " ".join(decoded.casefold().split())


def compare_snapshots(
    earlier: tuple[ArchiveXSnapshot, bytes] | None,
    later: tuple[ArchiveXSnapshot, bytes],
    *,
    policy: ArchiveDriftPolicy = ArchiveDriftPolicy(),
) -> ArchiveSignal:
    if not 1 <= policy.max_text_chars <= 1000000:
        raise ValueError("invalid drift budget")
    if not 0.9 <= policy.unchanged_similarity <= 1:
        raise ValueError("invalid unchanged threshold")
    if not 0 <= policy.expansion_threshold <= 1:
        raise ValueError("invalid expansion threshold")
    if not 16 <= policy.max_comparison_units <= 2048:
        raise ValueError("invalid comparison complexity budget")
    later_meta, later_body = later
    later_text = _text(later_body, policy)
    if earlier is None:
        return ArchiveSignal(
            later_meta.source_url, None, later_meta.snapshot_id,
            ArchiveSignalKind.FIRST_SEEN, 0, len(later_text), 0,
            None, later_meta.content_digest,
        )
    earlier_meta, earlier_body = earlier
    if earlier_meta.source_url != later_meta.source_url:
        raise ValueError("cannot compare unrelated sources")
    if earlier_meta.observed_at > later_meta.observed_at:
        raise ValueError("snapshot order is reversed")
    earlier_text = _text(earlier_body, policy)
    if earlier_meta.content_digest == later_meta.content_digest:
        kind, similarity = ArchiveSignalKind.UNCHANGED, 1.0
        added = removed = 0
    else:
        # Bound quadratic matching to at most max_comparison_units units.
        # Large inputs use fixed-size chunks, not arbitrary-length characters.
        longest = max(len(earlier_text), len(later_text))
        chunk = max(1, (longest + policy.max_comparison_units - 1)
                    // policy.max_comparison_units)
        a = [earlier_text[i:i + chunk] for i in range(0, len(earlier_text), chunk)]
        b = [later_text[i:i + chunk] for i in range(0, len(later_text), chunk)]
        matcher = SequenceMatcher(None, a, b, autojunk=True)
        similarity = round(matcher.ratio(), 6)
        added = removed = 0
        for op, i1, i2, j1, j2 in matcher.get_opcodes():
            if op in ("replace", "delete"):
                removed += sum(len(unit) for unit in a[i1:i2])
            if op in ("replace", "insert"):
                added += sum(len(unit) for unit in b[j1:j2])
        if similarity >= policy.unchanged_similarity and earlier_text == later_text:
            kind = ArchiveSignalKind.UNCHANGED
        elif removed > 0 and added == 0:
            kind = ArchiveSignalKind.REMOVED
        elif added > 0 and removed == 0:
            kind = ArchiveSignalKind.EXPANDED
        elif added > removed * (1 + policy.expansion_threshold):
            kind = ArchiveSignalKind.EXPANDED
        else:
            kind = ArchiveSignalKind.REVISED
    return ArchiveSignal(
        later_meta.source_url, earlier_meta.snapshot_id,
        later_meta.snapshot_id, kind, similarity, added, removed,
        earlier_meta.content_digest, later_meta.content_digest,
    )


def source_drift_timeline(
    archive: ArchiveX, owner: str, source_url: str, *,
    authorized: bool, limit: int = 100,
    policy: ArchiveDriftPolicy = ArchiveDriftPolicy(),
) -> tuple[ArchiveSignal, ...]:
    snapshots = archive.timeline(
        owner, source_url, authorized=authorized, limit=limit,
    )
    ordered = tuple(reversed(snapshots))
    signals = []
    previous = None
    for meta in ordered:
        current = archive.read(owner, meta.snapshot_id, authorized=authorized)
        signals.append(compare_snapshots(previous, current, policy=policy))
        previous = current
    return tuple(signals)
