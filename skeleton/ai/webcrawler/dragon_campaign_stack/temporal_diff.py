"""Revision deltas with exact Unicode spans and explicit incomplete-evidence holds.

The diff inspects at most two bounded retained source versions, not a live
website. A truncated copy is not proof that the original document was
unchanged, and a wall-clock fetch timestamp is not remote freshness proof.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
from typing import Iterable

from ..core import canonicalize_url
from .contracts import digest, exact_digest, finite


@dataclass(frozen=True)
class RetainedVersion:
    source_id: str
    canonical_url: str
    content_hash: str
    preserved_text_hash: str
    captured_at: float
    text: str
    truncated: bool
    source_policy_version: int = 0

    def __post_init__(self) -> None:
        exact_digest(self.source_id, "version source")
        exact_digest(self.content_hash, "full version digest")
        if self.source_id != digest({
            "url": self.canonical_url, "content_hash": self.content_hash,
        }):
            raise ValueError("source identity not bound to captured revision")
        exact_digest(self.preserved_text_hash, "retained version digest")
        if canonicalize_url(self.canonical_url) != self.canonical_url:
            raise ValueError("noncanonical version URL")
        finite(self.captured_at, "version clock")
        if not isinstance(self.text, str) or not 0 < len(self.text.encode("utf-8")) <= 24_000:
            raise ValueError("retained version text capacity exceeded")
        if sha256(self.text.encode()).hexdigest() != self.preserved_text_hash:
            raise ValueError("retained version digest mismatch")
        if type(self.truncated) is not bool:
            raise ValueError("unknown full-content retention")
        if not self.truncated and self.content_hash != self.preserved_text_hash:
            raise ValueError("nontruncated version differs from full source")
        if type(self.source_policy_version) is not int or not 0 <= self.source_policy_version < 2**31:
            raise ValueError("invalid version policy")


@dataclass(frozen=True)
class ChangeSpan:
    kind: str
    before_start: int
    before_end: int
    after_start: int
    after_end: int
    removed_hash: str
    inserted_hash: str
    removed_preview: str
    inserted_preview: str
    preview_truncated: bool


@dataclass(frozen=True)
class TemporalChangeReport:
    canonical_url: str
    earlier_source_id: str
    later_source_id: str
    earlier_capture_at: float
    later_capture_at: float
    status: str
    retained_prefix_chars: int
    retained_suffix_chars: int
    spans: tuple[ChangeSpan, ...]
    incomplete_source: bool
    requires_new_review: bool
    revision_digest: str
    remote_freshness_attested: bool = False


def compare_retained_versions(
    before: RetainedVersion,
    after: RetainedVersion,
    *,
    preview_chars: int = 256,
) -> TemporalChangeReport:
    if not isinstance(before, RetainedVersion) or not isinstance(after, RetainedVersion):
        raise TypeError("typed retained source versions required")
    if before.canonical_url != after.canonical_url:
        raise PermissionError("cross-resource temporal comparison")
    if before.captured_at > after.captured_at:
        raise ValueError("nonmonotonic source clock")
    if before.captured_at == after.captured_at and before.source_id != after.source_id:
        raise ValueError("conflicting version at one timestamp")
    if type(preview_chars) is not int or not 0 <= preview_chars <= 512:
        raise ValueError("invalid bounded preview")
    a, b = before.text, after.text
    # Linear-time exact prefix/suffix discovery avoids quadratic adversarial
    # difflib behavior on long repetitive or attacker-constructed documents.
    limit = min(len(a), len(b))
    prefix = 0
    while prefix < limit and a[prefix] == b[prefix]:
        prefix += 1
    suffix = 0
    while (suffix < len(a) - prefix and suffix < len(b) - prefix
           and a[len(a) - 1 - suffix] == b[len(b) - 1 - suffix]):
        suffix += 1
    before_end = len(a) - suffix
    after_end = len(b) - suffix
    old = a[prefix:before_end]
    new = b[prefix:after_end]
    changed = bool(old or new)
    kind = ("replace" if old and new else "delete" if old else "insert")
    incomplete = before.truncated or after.truncated
    spans = ()
    if changed:
        spans = (ChangeSpan(
            kind=kind,
            before_start=prefix,
            before_end=before_end,
            after_start=prefix,
            after_end=after_end,
            removed_hash=sha256(old.encode()).hexdigest(),
            inserted_hash=sha256(new.encode()).hexdigest(),
            removed_preview=old[:preview_chars],
            inserted_preview=new[:preview_chars],
            preview_truncated=(len(old) > preview_chars or len(new) > preview_chars),
        ),)
    if incomplete:
        status = "partial_comparison"
    elif changed:
        status = "retained_text_changed"
    else:
        status = "retained_text_unchanged"
    payload = {
        "before": asdict(before) | {"text": before.preserved_text_hash},
        "after": asdict(after) | {"text": after.preserved_text_hash},
        "status": status,
        "prefix": prefix,
        "suffix": suffix,
        "spans": [asdict(x) for x in spans],
    }
    return TemporalChangeReport(
        canonical_url=before.canonical_url,
        earlier_source_id=before.source_id,
        later_source_id=after.source_id,
        earlier_capture_at=before.captured_at,
        later_capture_at=after.captured_at,
        status=status,
        retained_prefix_chars=prefix,
        retained_suffix_chars=suffix,
        spans=spans,
        incomplete_source=incomplete,
        requires_new_review=changed or incomplete
        or before.source_policy_version != after.source_policy_version,
        revision_digest=digest(payload),
    )


@dataclass(frozen=True)
class TemporalSequence:
    canonical_url: str
    versions: int
    changes: tuple[TemporalChangeReport, ...]
    revision_boundaries: tuple[str, ...]
    sequence_digest: str


def build_temporal_sequence(
    versions: Iterable[RetainedVersion],
    *,
    maximum_versions: int = 32,
) -> TemporalSequence:
    if type(maximum_versions) is not int or not 2 <= maximum_versions <= 64:
        raise ValueError("invalid temporal history budget")
    rows = tuple(versions)
    if not 2 <= len(rows) <= maximum_versions:
        raise ValueError("temporal sequence needs bounded versions")
    if len({x.source_id for x in rows}) != len(rows):
        # Re-capturing the same digest at a later time is valid; a version
        # receipt is still unique by (source, capture-time), not source alone.
        if len({(x.source_id, x.captured_at) for x in rows}) != len(rows):
            raise ValueError("duplicate temporal version receipt")
    if any(a.captured_at > b.captured_at for a, b in zip(rows, rows[1:])):
        raise ValueError("unsorted temporal sequence")
    deltas = tuple(
        compare_retained_versions(a, b) for a, b in zip(rows, rows[1:])
    )
    payload = {
        "url": rows[0].canonical_url,
        "source_versions": [x.source_id for x in rows],
        "deltas": [x.revision_digest for x in deltas],
    }
    return TemporalSequence(
        canonical_url=rows[0].canonical_url,
        versions=len(rows),
        changes=deltas,
        revision_boundaries=tuple(x.status for x in deltas),
        sequence_digest=digest(payload),
    )
