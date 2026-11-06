"""Conservative campaign budget projection over committed CrawlRun counters.

All numbers come from the canonical snapshot. Projected allocations never
increase request/document/byte budgets or restore uncertain in-flight bytes.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping
import json

from .contracts import CampaignMandate, integer


@dataclass(frozen=True)
class BudgetProjection:
    requests_used: int
    requests_remaining: int
    documents_used: int
    documents_remaining: int
    bytes_measured: int
    bytes_uncertain: int
    bytes_remaining: int
    snapshot_bytes: int
    pending_dispatch: bool
    state: str
    exhausted: bool
    blockers: tuple[str, ...]


def project_budget(
    snapshot: Mapping[str, object], mandate: CampaignMandate, *,
    snapshot_bytes: int,
) -> BudgetProjection:
    if not isinstance(snapshot, Mapping):
        raise ValueError("invalid crawl snapshot")
    integer(snapshot_bytes, "snapshot bytes", 0, 4 * 1024 * 1024)
    usage = snapshot.get("usage")
    if not isinstance(usage, dict):
        raise ValueError("missing canonical usage")
    for key in ("requests", "documents", "bytes", "reserved_bytes", "failures"):
        integer(usage.get(key), key, 0, 1_000_000_000)
    request = mandate.request
    used_requests = usage["requests"]
    used_documents = usage["documents"]
    spent_bytes = usage["bytes"]
    uncertain = usage["reserved_bytes"]
    if used_requests > request.max_requests or used_documents > request.max_documents:
        raise ValueError("observed usage exceeds immutable grant")
    if spent_bytes + uncertain > request.max_total_bytes:
        raise ValueError("observed bytes exceed immutable grant")
    pending = snapshot.get("pending_dispatch") is not None
    if pending:
        candidate = snapshot["pending_dispatch"]
        if not isinstance(candidate, dict):
            raise ValueError("invalid in-flight reservation")
        if uncertain <= 0:
            raise ValueError("unmetered pending dispatch")
    state = snapshot.get("state")
    if state not in ("ready", "running", "paused", "failed", "completed", "cancelled", "budget_exhausted"):
        raise ValueError("invalid crawl state")
    remaining_requests = request.max_requests - used_requests
    remaining_documents = request.max_documents - used_documents
    remaining_bytes = request.max_total_bytes - spent_bytes - uncertain
    blockers = []
    if remaining_requests <= 0:
        blockers.append("request_budget_exhausted")
    if remaining_documents <= 0:
        blockers.append("document_budget_exhausted")
    if remaining_bytes < 1024:
        blockers.append("byte_budget_exhausted")
    if snapshot_bytes >= 3 * 1024 * 1024:
        blockers.append("snapshot_near_capacity")
    if pending:
        blockers.append("in_flight_outcome_requires_recovery")
    if state not in ("ready", "running"):
        blockers.append("state_" + state)
    return BudgetProjection(
        requests_used=used_requests,
        requests_remaining=remaining_requests,
        documents_used=used_documents,
        documents_remaining=remaining_documents,
        bytes_measured=spent_bytes,
        bytes_uncertain=uncertain,
        bytes_remaining=remaining_bytes,
        snapshot_bytes=snapshot_bytes,
        pending_dispatch=pending,
        state=state,
        exhausted=bool(blockers),
        blockers=tuple(blockers),
    )


@dataclass(frozen=True)
class BudgetReservation:
    requested_urls: tuple[str, ...]
    projected_bytes: int
    requests: int
    remaining_bytes_after: int
    remaining_requests_after: int


def reserve_advisory(
    projection: BudgetProjection, *,
    allocations: tuple[tuple[str, int], ...],
) -> BudgetReservation:
    """Compute a hint; cannot be used as proof of pre-network reservation."""
    if not isinstance(projection, BudgetProjection):
        raise TypeError("budget projection required")
    if projection.exhausted:
        if allocations:
            raise PermissionError("campaign cannot dispatch while blocked")
        return BudgetReservation((), 0, 0, projection.bytes_remaining, projection.requests_remaining)
    seen: set[str] = set()
    charged = 0
    for url, byte_count in allocations:
        if not isinstance(url, str) or url in seen:
            raise ValueError("duplicate dispatch budget identity")
        integer(byte_count, "advisory byte cap", 1, 2_097_152)
        seen.add(url)
        charged += byte_count
    if charged > projection.bytes_remaining or len(allocations) > projection.requests_remaining:
        raise PermissionError("advisory dispatch exceeds retained budget")
    return BudgetReservation(
        requested_urls=tuple(url for url, _ in allocations),
        projected_bytes=charged,
        requests=len(allocations),
        remaining_bytes_after=projection.bytes_remaining - charged,
        remaining_requests_after=projection.requests_remaining - len(allocations),
    )


def verify_projected_budget(
    snapshot: Mapping[str, object],
    mandate: CampaignMandate,
    projection: BudgetProjection,
) -> None:
    """Reproduce the canonical inspection's exact UTF-8 byte-size budget.

    Equality checks *all* fields, not only used request/byte counters.
    Otherwise an advisory could accept a forged larger remaining budget,
    altered document count, missing in-flight flag, or omitted blocker.
    The verified receipt still does not authorize transport or Mongo writes.
    """
    if not isinstance(projection, BudgetProjection):
        raise TypeError("typed canonical budget projection required")
    if not isinstance(snapshot, Mapping):
        raise ValueError("canonical snapshot mapping required")
    encoded = json.dumps(
        snapshot, ensure_ascii=False, sort_keys=True,
        separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")
    actual = project_budget(
        snapshot, mandate, snapshot_bytes=len(encoded),
    )
    if actual != projection:
        raise PermissionError(
            "budget projection not bound to current canonical snapshot"
        )
