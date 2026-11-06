"""Read-only robots/cache and origin cooldown diagnostics for canonical CrawlRun.

A cache text or HTTP 404 does not grant authority to fetch. Every real request
must use the canonical runner's fresh robots policy, pinned DNS and pre-I/O
reservation. This audit only explains current retained state.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
from urllib.parse import urlsplit

from ..operations import CrawlRun
from .contracts import CampaignMandate, digest, ensure_snapshot_scope, finite


@dataclass(frozen=True)
class OriginRobots:
    origin: str
    host: str
    fetch_status: int
    observed_at: float
    cache_age_seconds: float | None
    raw_robots_body_hash: str | None
    rules_present: bool
    pending_redirect_count: int
    cache_expired: bool
    applicable_to_frontier_count: int
    review_reason: str
    policy_is_current_authority: bool = False


@dataclass(frozen=True)
class RobotsAudit:
    snapshot_digest: str
    origin_count: int
    never_fetched_origins: tuple[str, ...]
    stale_origins: tuple[str, ...]
    unresolved_origins: tuple[str, ...]
    records: tuple[OriginRobots, ...]
    audit_digest: str
    network_robots_admission_granted: bool = False


def audit_robots_state(
    snapshot: dict[str, object], mandate: CampaignMandate, *,
    now: float, authorized: bool,
) -> RobotsAudit:
    mandate.admit(now=now, authorized=authorized)
    ensure_snapshot_scope(snapshot, mandate)
    run = CrawlRun.from_snapshot(snapshot)
    actual = run.snapshot()
    rows = actual["robots"]
    origins = set(rows)
    for entry in actual["frontier"]:
        p = urlsplit(entry["url"])
        origins.add(p.scheme + "://" + p.netloc)
    if len(origins) > 64:
        raise ValueError("robots diagnostic origins over capacity")
    records = []
    never = []
    stale = []
    unresolved = []
    for origin in sorted(origins):
        p = urlsplit(origin)
        if p.scheme not in ("https", "http") or p.hostname not in mandate.scope.allowed_hosts:
            raise PermissionError("foreign robots origin")
        row = rows.get(origin)
        entries = sum(
            urlsplit(entry["url"]).netloc == p.netloc and
            urlsplit(entry["url"]).scheme == p.scheme
            for entry in actual["frontier"]
        )
        if row is None:
            never.append(origin)
            records.append(OriginRobots(
                origin=origin, host=p.hostname, fetch_status=0,
                observed_at=0.0, cache_age_seconds=None,
                raw_robots_body_hash=None, rules_present=False,
                pending_redirect_count=0, cache_expired=True,
                applicable_to_frontier_count=entries,
                review_reason="robots_not_yet_checked",
            ))
            continue
        at = finite(row.get("fetched_at"), "robots observation time")
        if at > now + 300:
            raise ValueError("future robots receipt")
        age = max(0.0, now - at) if at else None
        expired = age is None or age >= mandate.scope.policy().robots_ttl_seconds
        if expired:
            stale.append(origin)
        if row["text"] is None:
            unresolved.append(origin)
        state = (
            "robots_unresolved_or_redirect_pending" if row["text"] is None
            else "robots_ttl_expired" if expired
            else "robots_policy_available_requires_runner_recheck"
        )
        raw_hash = row.get("raw_body_hash")
        if raw_hash is not None and (
            not isinstance(raw_hash, str) or len(raw_hash) != 64
            or any(x not in "0123456789abcdef" for x in raw_hash)
        ):
            raise ValueError("invalid robots raw body hash")
        records.append(OriginRobots(
            origin=origin, host=p.hostname,
            fetch_status=row["status"], observed_at=at,
            cache_age_seconds=age,
            raw_robots_body_hash=raw_hash,
            rules_present=row["text"] is not None,
            pending_redirect_count=len(row["redirects"]),
            cache_expired=expired,
            applicable_to_frontier_count=entries,
            review_reason=state,
        ))
    payload = {
        "mandate": mandate.fingerprint,
        "snapshot": actual["snapshot_digest"],
        "records": [asdict(x) for x in records],
    }
    return RobotsAudit(
        snapshot_digest=actual["snapshot_digest"],
        origin_count=len(origins),
        never_fetched_origins=tuple(never),
        stale_origins=tuple(stale),
        unresolved_origins=tuple(unresolved),
        records=tuple(records), audit_digest=digest(payload),
    )
