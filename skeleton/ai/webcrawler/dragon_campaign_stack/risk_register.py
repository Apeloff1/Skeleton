"""Operational anomaly register from verified bounded crawler event receipts.

The register is diagnostic. It cannot grant network access, reverse a
cancellation, release an uncertain worker, or override a robots decision.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
from typing import Iterable
from urllib.parse import urlsplit

from ..operations import CrawlRun
from .contracts import CampaignMandate, digest, ensure_snapshot_scope, finite, integer


@dataclass(frozen=True)
class CrawlRisk:
    code: str
    severity: str
    count: int
    host: str | None
    latest_sequence: int
    action: str


@dataclass(frozen=True)
class CrawlRiskRegister:
    run_id: str
    source_snapshot_digest: str
    events_retained: int
    events_truncated: bool
    distinct_hosts: int
    risks: tuple[CrawlRisk, ...]
    review_required: bool
    recommended_actions: tuple[str, ...]
    risk_digest: str


_KINDS = {
    "robots": "robots_observation",
    "retry": "http_retry_pressure",
    "error": "transport_fault",
    "interrupted_dispatch": "unknown_remote_effect",
    "rejected": "source_or_policy_rejection",
    "redirect": "redirect_handoff",
}


def compile_crawl_risks(
    snapshot: dict[str, object], mandate: CampaignMandate,
    *, now: float,
    authorized: bool,
    retry_alert: int = 3,
) -> CrawlRiskRegister:
    mandate.admit(now=now, authorized=authorized)
    integer(retry_alert, "retry alert threshold", 1, 32)
    ensure_snapshot_scope(snapshot, mandate)
    run = CrawlRun.from_snapshot(snapshot)
    canonical = run.snapshot()
    events = canonical["events"]
    by_key: dict[tuple[str, str | None], list[int]] = {}
    hosts = set()
    for event in events:
        kind = event["kind"]
        url = event.get("url")
        host = urlsplit(url).hostname if isinstance(url, str) else None
        if host:
            hosts.add(host)
        if kind not in _KINDS:
            continue
        if kind == "robots" and event.get("reason") == "http_200":
            continue
        code = _KINDS[kind]
        by_key.setdefault((code, host), []).append(event["sequence"])
    risks = []
    for (code, host), seqs in sorted(
        by_key.items(), key=lambda pair: (pair[0][0], pair[0][1] or "")
    ):
        quantity = len(seqs)
        severity = (
            "critical" if code == "unknown_remote_effect" else
            "high" if code == "transport_fault" else
            "medium" if quantity >= retry_alert else "low"
        )
        action = {
            "robots_observation": "confirm_origin_robots_response_and_blocked_policy",
            "http_retry_pressure": "respect_retry_after_and_host_cooldown",
            "transport_fault": "inspect_network_dns_proxy_and_trust_roots",
            "unknown_remote_effect": "reconcile_checkpoint_and_join_physical_worker",
            "source_or_policy_rejection": "check_source_permission_not_bypass",
            "redirect_handoff": "inspect_validated_redirect_chain",
        }[code]
        risks.append(CrawlRisk(
            code=code, severity=severity, count=quantity,
            host=host, latest_sequence=max(seqs), action=action,
        ))
    risks.sort(key=lambda x: (
        {"critical": 0, "high": 1, "medium": 2, "low": 3}[x.severity],
        -x.count, x.code, x.host or "",
    ))
    actions = tuple(dict.fromkeys(x.action for x in risks))
    payload = {
        "mandate": mandate.fingerprint,
        "snapshot": canonical["snapshot_digest"],
        "events": len(events),
        "truncated": bool(events and events[0]["sequence"] > 1),
        "risks": [asdict(x) for x in risks],
    }
    return CrawlRiskRegister(
        run_id=canonical["run_id"],
        source_snapshot_digest=canonical["snapshot_digest"],
        events_retained=len(events),
        events_truncated=bool(events and events[0]["sequence"] > 1),
        distinct_hosts=len(hosts),
        risks=tuple(risks),
        review_required=any(x.severity in ("high", "critical") for x in risks),
        recommended_actions=actions,
        risk_digest=digest(payload),
    )
