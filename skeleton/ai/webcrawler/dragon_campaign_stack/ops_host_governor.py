"""Per-origin safety posture over committed frontier and current robots cache.

The result is a conservative workload/robots review signal. Cache presence
does NOT grant live robots permission, make a DNS answer public, authorize a
request, or override the canonical request owner. In particular HTTP 404
is never inferred from an absent robots row.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass
from urllib.parse import urlsplit

from ..operations import CrawlRun
from .contracts import CampaignMandate, digest, ensure_snapshot_scope, finite
from .ops_timeline import OperationalTimeline


@dataclass(frozen=True)
class OriginGuard:
    host: str
    origin: str
    pending_urls: int
    ready_at: float
    past_attempts: int
    robots_observation: str
    robots_observation_age_seconds: float | None
    robot_rules_need_fresh_confirmation: bool
    retry_or_transport_faults: int
    queued_ready_now: int
    held_reasons: tuple[str, ...]
    candidate_for_live_backend_preflight: bool
    physical_dns_validated: bool = False
    live_robots_permission_granted: bool = False


@dataclass(frozen=True)
class HostGovernor:
    mandate_digest: str
    source_snapshot_digest: str
    timeline_digest: str
    inspected_at: float
    origins: tuple[OriginGuard, ...]
    hosts_with_review_holds: tuple[str, ...]
    cold_robots_origins: int
    stale_robots_origins: int
    ready_frontier_items: int
    governor_digest: str
    network_request_admission_granted: bool = False


def govern_canonical_origins(
    mandate: CampaignMandate, snapshot: dict[str, object],
    timeline: OperationalTimeline, *, now: float, authorized: bool,
) -> HostGovernor:
    mandate.admit(now=now, authorized=authorized)
    ensure_snapshot_scope(snapshot, mandate)
    if not isinstance(timeline, OperationalTimeline):
        raise TypeError("canonical operational timeline required")
    canonical = CrawlRun.from_snapshot(snapshot).snapshot()
    if (timeline.mandate_digest != mandate.fingerprint
            or timeline.source_snapshot_digest != canonical["snapshot_digest"]
            or timeline.run_id != canonical["run_id"]
            or timeline.run_sequence != canonical["sequence"]):
        raise PermissionError("host governor detached from exact timeline")
    by_origin = defaultdict(list)
    for row in canonical["frontier"]:
        url = urlsplit(row["url"])
        if url.hostname not in mandate.scope.allowed_hosts:
            raise PermissionError("frontier host escaped consent")
        by_origin[url.scheme + "://" + url.netloc].append(row)
    if len(by_origin) > 32:
        raise ValueError("operational origin capacity exceeded")
    fault_counts = defaultdict(int)
    for row in timeline.events:
        if row.host and row.kind in (
            "retry", "error", "interrupted_dispatch", "rejected",
        ):
            fault_counts[row.host] += 1
    entries = []
    held_hosts = set()
    stale = cold = ready_count = 0
    for origin, rows in sorted(by_origin.items()):
        parsed = urlsplit(origin)
        host = parsed.hostname
        cool = finite(canonical["host_ready"].get(host, 0),
                      "canonical host cooldown")
        threshold = min(max(cool, float(r["ready_at"])) for r in rows)
        ready_now = sum(max(cool, float(row["ready_at"])) <= now for row in rows)
        ready_count += ready_now
        robots = canonical["robots"].get(origin)
        reasons = []
        age = None
        if robots is None or robots["text"] is None:
            cold += 1
            robots_state = "not_observed_or_unresolved"
            reasons.append("fresh_live_robots_resolution_required")
        else:
            age = max(0.0, now - finite(robots["fetched_at"], "robots timestamp"))
            if robots["fetched_at"] > now + 300:
                reasons.append("future_robots_observation")
            if age >= mandate.scope.policy().robots_ttl_seconds:
                stale += 1
                robots_state = "cache_age_exceeded"
                reasons.append("robots_cache_expired")
            else:
                robots_state = "retained_robots_observation_only"
            reasons.append("current_live_robots_policy_must_be_rechecked")
        if ready_now == 0:
            reasons.append("host_cooldown_or_item_retry_not_elapsed")
        if timeline.pending_dispatch_unresolved:
            reasons.append("previous_remote_outcome_unsettled")
        if timeline.clock_regression_detected or timeline.future_clock_receipts:
            reasons.append("event_clock_integrity_review")
        if canonical["state"] not in ("ready", "running"):
            reasons.append("canonical_state_not_runnable")
        # Missing robots state warrants an explicit robots-only preflight,
        # not a blanket ban on a hypothetical robots request. Hard failures
        # (unsettled worker, time integrity or non-runnable state) do prevent
        # advisory work from being proposed.
        if set(reasons) & {
            "previous_remote_outcome_unsettled",
            "event_clock_integrity_review",
            "canonical_state_not_runnable",
            "future_robots_observation",
        }:
            held_hosts.add(host)
        entries.append(OriginGuard(
            host, origin, len(rows), threshold,
            sum(row["attempts"] for row in rows),
            robots_state, age, True, fault_counts[host],
            ready_now, tuple(sorted(set(reasons))),
            ready_now > 0 and canonical["state"] in ("ready", "running")
                and not timeline.pending_dispatch_unresolved,
        ))
    payload = {
        "mandate": mandate.fingerprint,
        "snapshot": canonical["snapshot_digest"],
        "timeline": timeline.timeline_digest,
        "origins": [asdict(x) for x in entries],
        "now": now,
    }
    return HostGovernor(
        mandate.fingerprint, canonical["snapshot_digest"],
        timeline.timeline_digest, now, tuple(entries),
        tuple(sorted(held_hosts)), cold, stale, ready_count,
        digest(payload),
    )
