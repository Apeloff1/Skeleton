"""Canonical dispatch/failure accounting and recovery-first risk projections.

Read-only incident archaeology over the bounded CrawlRun event journal.
Request and uncertain-byte counters stay owned by the canonical runtime:
a dispatch_reserved event is proof of a *local recorded intent*, not proof of
remote completion or a successfully committed Mongo checkpoint.

The ledger groups events by host and phase, detects unmatched current
in-flight reservations and usage counter regressions, and issues a
non-executable recovery queue. It never fabricates a physical worker join,
rewrites a checkpoint, reuses a credential or reduces retained uncertain bytes.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from urllib.parse import urlsplit

from ..operations import CrawlRun
from .budget import BudgetProjection, verify_projected_budget
from .contracts import CampaignMandate, digest, ensure_snapshot_scope, integer


_PHASES = {
    "dispatch_reserved": "pre_network_reservation",
    "robots": "robots_policy_observation",
    "retry": "bounded_remote_retry",
    "redirect": "redirect_policy_observation",
    "error": "transport_failure",
    "rejected": "source_policy_or_content_rejection",
    "interrupted_dispatch": "unknown_remote_effect",
    "stopped": "terminal_budget_hold",
    "completed": "terminal_frontier_drain",
    "pause": "operator_paused",
    "resume": "operator_resumed",
    "cancel": "operator_cancelled",
    "captured": "captured_unreviewed_source",
    "duplicate": "content_duplicate_detected",
}


@dataclass(frozen=True)
class DispatchEventReceipt:
    sequence: int
    kind: str
    phase: str
    host: str | None
    url: str | None
    recorded_at: float
    accounted_requests: int
    accounted_bytes: int
    uncertain_bytes: int
    event_digest: str
    local_record_only: bool = True
    remote_outcome_confirmed: bool = False


@dataclass(frozen=True)
class HostFaultPressure:
    host: str
    dispatch_intents: int
    retries: int
    transport_failures: int
    robots_observations: int
    redirected: int
    rejected: int
    interrupted: int
    observed_event_count: int
    max_accounted_request_count: int
    max_accounted_uncertain_bytes: int
    active_cooldown_until: float
    fault_grade: str
    requires_source_review: bool


@dataclass(frozen=True)
class RecoveryStep:
    ordinal: int
    code: str
    severity: str
    supporting_event_sequences: tuple[int, ...]
    blocked_until_operator_resolution: bool
    operation: str = "human_diagnostic_only"
    auto_execute: bool = False


@dataclass(frozen=True)
class DispatchFaultLedger:
    mandate_digest: str
    source_snapshot_digest: str
    run_id: str
    source_sequence: int
    events_retained: int
    history_incomplete: bool
    phases: tuple[DispatchEventReceipt, ...]
    hosts: tuple[HostFaultPressure, ...]
    recovery_queue: tuple[RecoveryStep, ...]
    current_pending_dispatch: bool
    retained_uncertain_bytes: int
    ledger_digest: str
    worker_join_confirmed: bool = False
    mongo_commit_confirmed: bool = False
    budget_refunded: bool = False
    external_network_observed: bool = False


def analyze_dispatch_faults(
    mandate: CampaignMandate,
    snapshot: dict[str, object],
    budget: BudgetProjection,
    *,
    now: float,
    authorized: bool,
    max_events: int = 64,
) -> DispatchFaultLedger:
    mandate.admit(now=now, authorized=authorized)
    ensure_snapshot_scope(snapshot, mandate)
    integer(max_events, "fault ledger event capacity", 1, 64)
    if not isinstance(budget, BudgetProjection):
        raise TypeError("canonical budget projection required")
    canonical = CrawlRun.from_snapshot(snapshot).snapshot()
    verify_projected_budget(canonical, mandate, budget)
    events = tuple(canonical["events"])
    if len(events) > max_events:
        raise ValueError("bounded event history exceeds inspection capacity")
    if budget.requests_used != canonical["usage"]["requests"] or (
        budget.bytes_measured != canonical["usage"]["bytes"]
        or budget.bytes_uncertain != canonical["usage"]["reserved_bytes"]
        or budget.pending_dispatch != (canonical["pending_dispatch"] is not None)
    ):
        raise PermissionError("fault ledger did not receive matching usage counters")
    if events and events[-1]["sequence"] > canonical["sequence"]:
        raise ValueError("event log exceeds source sequence")
    if canonical["pending_dispatch"] is not None and budget.bytes_uncertain == 0:
        raise PermissionError("inflight reservation cannot have no charge")
    observed = []
    by_host: dict[str, list[DispatchEventReceipt]] = defaultdict(list)
    previous_requests = 0
    previous_bytes = 0
    previous_uncertain = 0
    for event in events:
        kind = event["kind"]
        values = event["usage"]
        requests, used, uncertain = (
            values["requests"], values["bytes"], values["reserved_bytes"],
        )
        # A bounded tail may begin after historical requests, so compare
        # against zero only for nonnegative monotonic aggregate counters.
        if requests < previous_requests or used < previous_bytes:
            raise PermissionError("canonical event usage regressed")
        previous_requests, previous_bytes, previous_uncertain = (
            requests, used, uncertain,
        )
        url = event.get("url")
        host = urlsplit(url).hostname if isinstance(url, str) else None
        if host and host not in mandate.scope.allowed_hosts:
            raise PermissionError("event URL escaped immutable host grant")
        item = DispatchEventReceipt(
            sequence=event["sequence"], kind=kind,
            phase=_PHASES.get(kind, "unclassified_canonical_event"),
            host=host, url=url, recorded_at=event["at"],
            accounted_requests=requests, accounted_bytes=used,
            uncertain_bytes=uncertain,
            event_digest=event["event_digest"],
        )
        observed.append(item)
        if host:
            by_host[host].append(item)
    host_summaries = []
    for host, entries in sorted(by_host.items()):
        count = Counter(x.kind for x in entries)
        failures = (count["error"] + count["interrupted_dispatch"]
                    + count["retry"])
        severe = count["interrupted_dispatch"] > 0 or failures >= 5
        elevated = failures > 0 or count["rejected"] >= 2
        host_summaries.append(HostFaultPressure(
            host=host,
            dispatch_intents=count["dispatch_reserved"],
            retries=count["retry"], transport_failures=count["error"],
            robots_observations=count["robots"], redirected=count["redirect"],
            rejected=count["rejected"], interrupted=count["interrupted_dispatch"],
            observed_event_count=len(entries),
            max_accounted_request_count=max(x.accounted_requests for x in entries),
            max_accounted_uncertain_bytes=max(x.uncertain_bytes for x in entries),
            active_cooldown_until=canonical["host_ready"].get(host, 0),
            fault_grade="critical" if severe else
                        "degraded" if elevated else "observed_nominal",
            requires_source_review=bool(failures or count["rejected"]),
        ))
    recoveries = []
    def step(code, severity, support, blocked=True):
        recoveries.append(RecoveryStep(
            ordinal=len(recoveries), code=code, severity=severity,
            supporting_event_sequences=tuple(sorted(set(support))),
            blocked_until_operator_resolution=blocked,
        ))
    if canonical["pending_dispatch"] is not None:
        step(
            "fence_prior_worker_and_reconcile_uncertain_network_effect",
            "critical",
            [canonical["pending_dispatch"]["sequence"]],
        )
        step(
            "retain_pending_bytes_until_authoritative_recovery",
            "critical",
            [canonical["pending_dispatch"]["sequence"]],
        )
    if any(x.kind == "interrupted_dispatch" for x in observed):
        step(
            "inspect_interrupted_network_effect_without_unmetered_retry",
            "critical",
            [x.sequence for x in observed
             if x.kind == "interrupted_dispatch"],
        )
    if any(x.kind == "error" for x in observed):
        step(
            "diagnose_transient_dns_socket_and_transport_failures",
            "high", [x.sequence for x in observed if x.kind == "error"],
        )
    if any(x.kind == "retry" for x in observed):
        step(
            "respect_retry_after_host_cooldown_and_cumulative_request_caps",
            "medium", [x.sequence for x in observed if x.kind == "retry"],
        )
    if any(x.kind == "redirect" for x in observed):
        step(
            "verify_redirected_host_authorization_and_robots_origin",
            "medium", [x.sequence for x in observed if x.kind == "redirect"],
        )
    if any(x.kind == "rejected" for x in observed):
        step(
            "review_content_and_destination_policy_rejections",
            "medium", [x.sequence for x in observed if x.kind == "rejected"],
        )
    if canonical["state"] not in ("ready", "running"):
        step(
            "require_explicit_canonical_state_transition_if_applicable",
            "high", (), True,
        )
    if not recoveries and not observed:
        step("no_retained_fault_evidence_not_a_healthy_device_claim",
             "informational", (), False)
    payload = {
        "mandate": mandate.fingerprint,
        "snapshot": canonical["snapshot_digest"],
        "run": canonical["run_id"],
        "phases": [asdict(x) for x in observed],
        "hosts": [asdict(x) for x in host_summaries],
        "steps": [asdict(x) for x in recoveries],
        "uncertain": budget.bytes_uncertain,
        "inflight": budget.pending_dispatch,
    }
    return DispatchFaultLedger(
        mandate_digest=mandate.fingerprint,
        source_snapshot_digest=canonical["snapshot_digest"],
        run_id=canonical["run_id"],
        source_sequence=canonical["sequence"],
        events_retained=len(observed),
        history_incomplete=bool(
            observed and observed[0].sequence > 1
        ),
        phases=tuple(observed), hosts=tuple(host_summaries),
        recovery_queue=tuple(recoveries),
        current_pending_dispatch=budget.pending_dispatch,
        retained_uncertain_bytes=budget.bytes_uncertain,
        ledger_digest=digest(payload),
    )
