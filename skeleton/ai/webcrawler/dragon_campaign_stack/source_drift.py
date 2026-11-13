"""Cross-checkpoint drift of authoritative Dragon crawl capture snapshots.

A drift report is an offline risk register, not a remote change detector.
Two snapshots must belong to the same immutable campaign mandate. Withdrawn
identities are supplied by the current source-policy authority rather than
derived from text or previous inferred consent.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable

from ..operations import CrawlRun
from .contracts import CampaignMandate, digest, ensure_snapshot_scope, exact_digest, integer


@dataclass(frozen=True)
class DriftEntry:
    canonical_url: str
    before_source_id: str | None
    after_source_id: str | None
    before_hash: str | None
    after_hash: str | None
    disposition: str
    requires_citation_revalidation: bool
    requires_independent_review: bool
    reason: str


@dataclass(frozen=True)
class SnapshotDrift:
    mandate_digest: str
    earlier_snapshot_digest: str
    current_snapshot_digest: str
    earlier_sequence: int
    current_sequence: int
    changed_urls: tuple[str, ...]
    withdrawn_sources: tuple[str, ...]
    rows: tuple[DriftEntry, ...]
    invalidated_source_ids: tuple[str, ...]
    drift_digest: str
    inferred_remote_freshness: bool = False
    can_auto_publish: bool = False


def analyze_snapshot_drift(
    mandate: CampaignMandate,
    earlier: dict[str, object],
    current: dict[str, object],
    *,
    now: float,
    authorized: bool,
    revoked_source_ids: Iterable[str] = (),
    max_source_rows: int = 256,
) -> SnapshotDrift:
    mandate.admit(now=now, authorized=authorized)
    ensure_snapshot_scope(earlier, mandate)
    ensure_snapshot_scope(current, mandate)
    integer(max_source_rows, "drift capacity", 1, 512)
    old = CrawlRun.from_snapshot(earlier).snapshot()
    new = CrawlRun.from_snapshot(current).snapshot()
    if old["run_id"] != new["run_id"]:
        raise PermissionError("drift compares unrelated crawler runs")
    old_seq, new_seq = old["sequence"], new["sequence"]
    integer(old_seq, "old crawl sequence", 0, 2**63-1)
    integer(new_seq, "new crawl sequence", 0, 2**63-1)
    if new_seq < old_seq:
        raise ValueError("nonmonotonic crawl checkpoint sequence")
    if new_seq == old_seq and old["snapshot_digest"] != new["snapshot_digest"]:
        raise ValueError("equivocated same-sequence snapshot")
    if len(old["sources"]) + len(new["sources"]) > max_source_rows:
        raise ValueError("source drift capacity exceeded")
    revoked = tuple(revoked_source_ids)
    if len(revoked) != len(set(revoked)):
        raise ValueError("duplicate withdrawal identities")
    for source_id in revoked:
        exact_digest(source_id, "withdrawn source")
    if not set(revoked).issubset(set(old["sources"]) | set(new["sources"])):
        raise PermissionError("source withdrawal outside compared checkpoints")
    def group(snapshot):
        grouped = {}
        for source in snapshot["sources"].values():
            url = source["canonical_url"]
            grouped.setdefault(url, []).append(source)
        return grouped
    previous, latest = group(old), group(new)
    changes = []
    invalidated = set(revoked)
    for url in sorted(set(previous) | set(latest)):
        before_versions = sorted(previous.get(url, ()), key=lambda x: (x["fetched_at"], x["source_id"]))
        after_versions = sorted(latest.get(url, ()), key=lambda x: (x["fetched_at"], x["source_id"]))
        before = before_versions[-1] if before_versions else None
        after = after_versions[-1] if after_versions else None
        if not before and not after:
            continue
        a = before["source_id"] if before else None
        b = after["source_id"] if after else None
        # Withdrawal of even an earlier revision makes the URL unsafe for
        # unreviewed synthesis, because provenance may be derived from it.
        retired = any(x["source_id"] in revoked for x in before_versions + after_versions)
        if retired:
            status = "policy_withdrawn"
        elif before is None:
            status = "new_canonical_url"
        elif after is None:
            status = "missing_from_current_snapshot"
        elif a != b:
            status = "source_revision_changed"
        elif before.get("preserved_text_hash") != after.get("preserved_text_hash"):
            status = "retained_text_hash_mismatch"
        elif before.get("text_truncated") or after.get("text_truncated"):
            status = "incomplete_retained_text"
        else:
            status = "same_retained_revision"
        stale = status != "same_retained_revision"
        if stale:
            invalidated.update(x["source_id"] for x in before_versions)
            invalidated.update(x["source_id"] for x in after_versions)
        changes.append(DriftEntry(
            canonical_url=url, before_source_id=a, after_source_id=b,
            before_hash=before["content_hash"] if before else None,
            after_hash=after["content_hash"] if after else None,
            disposition=status,
            requires_citation_revalidation=stale,
            requires_independent_review=stale,
            reason="current_policy_or_revision_requires_review" if stale else
                   "unchanged_retained_revision_not_remote_freshness",
        ))
    payload = {
        "mandate": mandate.fingerprint,
        "old": old["snapshot_digest"], "new": new["snapshot_digest"],
        "revisions": [asdict(x) for x in changes],
        "withdrawn": sorted(revoked), "invalidated": sorted(invalidated),
    }
    return SnapshotDrift(
        mandate_digest=mandate.fingerprint,
        earlier_snapshot_digest=old["snapshot_digest"],
        current_snapshot_digest=new["snapshot_digest"],
        earlier_sequence=old_seq, current_sequence=new_seq,
        changed_urls=tuple(x.canonical_url for x in changes
                           if x.disposition != "same_retained_revision"),
        withdrawn_sources=tuple(sorted(revoked)),
        rows=tuple(changes),
        invalidated_source_ids=tuple(sorted(invalidated)),
        drift_digest=digest(payload),
    )
