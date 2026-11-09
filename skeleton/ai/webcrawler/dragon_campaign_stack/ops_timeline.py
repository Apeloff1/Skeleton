"""Finite operational timeline derived from the canonical crawl checkpoint.

Canonical CrawlRun validation checks event digests and sequence membership.
This secondary audit adds explicit history-completeness, future-clock,
monotonicity and pending-intent triage. External page text, event URLs,
reason strings and raw request bodies are never returned.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass

from ..operations import CrawlRun
from .contracts import CampaignMandate, digest, ensure_snapshot_scope, finite, integer


_KINDS = frozenset({
    "dispatch_reserved", "robots", "retry", "error", "rejected",
    "redirect", "captured", "stopped", "completed", "pause", "resume",
    "cancel", "interrupted_dispatch", "redirected", "queued",
    "skipped", "failed", "created",
})


@dataclass(frozen=True)
class TimelineEvent:
    sequence: int
    kind: str
    at: float
    host: str | None
    request_count: int
    measured_bytes: int
    uncertain_bytes: int
    event_digest: str
    network_outcome_independently_verified: bool = False


@dataclass(frozen=True)
class OperationalTimeline:
    mandate_digest: str
    source_snapshot_digest: str
    run_id: str
    run_sequence: int
    oldest_retained_sequence: int | None
    newest_retained_sequence: int | None
    events: tuple[TimelineEvent, ...]
    kind_counts: tuple[tuple[str, int], ...]
    retained_history_incomplete: bool
    interior_sequence_gap: bool
    clock_regression_detected: bool
    future_clock_receipts: int
    pending_dispatch_unresolved: bool
    uncertain_bytes: int
    review_holds: tuple[str, ...]
    timeline_digest: str
    historical_remote_effects_attested: bool = False


def inspect_operational_timeline(
    mandate: CampaignMandate, snapshot: dict[str, object],
    *, now: float, authorized: bool, max_events: int = 64,
    max_clock_skew_seconds: float = 300,
) -> OperationalTimeline:
    mandate.admit(now=now, authorized=authorized)
    ensure_snapshot_scope(snapshot, mandate)
    integer(max_events, "timeline event retention limit", 1, 64)
    finite(max_clock_skew_seconds, "timeline future skew", 0, 3600)
    canonical = CrawlRun.from_snapshot(snapshot).snapshot()
    rows = canonical["events"]
    if len(rows) > max_events:
        raise ValueError("retained timeline exceeds inspection capacity")
    from urllib.parse import urlsplit
    events = []
    old_sequence, old_time = None, None
    interior_gap = regression = False
    future = 0
    for row in rows:
        seq = integer(row["sequence"], "event sequence", 1, 2**63 - 1)
        at = finite(row["at"], "event observation time")
        if old_sequence is not None and seq != old_sequence + 1:
            interior_gap = True
        if old_time is not None and at < old_time:
            regression = True
        if at > now + max_clock_skew_seconds:
            future += 1
        usage = row["usage"]
        for key in ("requests", "bytes", "reserved_bytes"):
            integer(usage[key], "event usage: " + key, 0, 2**63 - 1)
        url = row.get("url")
        host = urlsplit(url).hostname if isinstance(url, str) else None
        if host is not None and host not in mandate.scope.allowed_hosts:
            raise PermissionError("event host is outside immutable mandate")
        kind = row["kind"]
        # Unknown event names should not silently become control signals.
        # They remain counted in a bounded opaque bucket.
        safe_kind = kind if kind in _KINDS else "other_canonical_event"
        events.append(TimelineEvent(
            seq, safe_kind, at, host, usage["requests"], usage["bytes"],
            usage["reserved_bytes"], row["event_digest"],
        ))
        old_sequence, old_time = seq, at
    oldest = events[0].sequence if events else None
    latest = events[-1].sequence if events else None
    incomplete = bool(oldest is not None and oldest > 1)
    if latest is not None and latest != canonical["sequence"]:
        # The canonical run may have more historical state transitions than
        # the events ring retains. A missing tail is never an all-clear.
        interior_gap = True
    pending = canonical["pending_dispatch"] is not None
    uncertain = canonical["usage"]["reserved_bytes"]
    holds = []
    if incomplete:
        holds.append("earlier_crawl_events_not_retained")
    if interior_gap:
        holds.append("missing_sequence_within_observed_history")
    if regression:
        holds.append("event_clock_regression")
    if future:
        holds.append("future_event_clock_receipt")
    if pending:
        holds.append("unsettled_network_dispatch")
    if uncertain:
        holds.append("uncertain_bytes_must_remain_reserved")
    counts = tuple(sorted(Counter(x.kind for x in events).items()))
    payload = {
        "mandate": mandate.fingerprint,
        "snapshot": canonical["snapshot_digest"],
        "run": canonical["run_id"],
        "sequence": canonical["sequence"],
        "events": [asdict(x) for x in events],
        "holds": holds,
        "counts": counts,
        "max_clock_skew_seconds": max_clock_skew_seconds,
    }
    return OperationalTimeline(
        mandate.fingerprint, canonical["snapshot_digest"],
        canonical["run_id"], canonical["sequence"], oldest, latest,
        tuple(events), counts, incomplete, interior_gap,
        regression, future, pending, uncertain, tuple(holds),
        digest(payload),
    )
