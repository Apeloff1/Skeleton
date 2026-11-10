"""Deterministic, host-fair mission ranking bound to live canonical budgets.

This module makes *advisory* decisions. The existing CrawlRun / SafeHttpFetcher
still enforce robots, destination, DNS pinning, consent and pre-I/O reserves.
"""
from __future__ import annotations

from dataclasses import asdict
from typing import Iterable

from ..dragon_mission_scheduler import (
    AcquisitionCandidate, allocate_host_dispatches, rank_acquisition_candidates,
)
from .budget import BudgetProjection, reserve_advisory
from .contracts import (
    CampaignMandate, CampaignPlan, ResearchCandidate, ResearchDispatch,
    digest, finite, validate_public_url,
)


def build_campaign_plan(
    mandate: CampaignMandate,
    candidates: Iterable[ResearchCandidate],
    projection: BudgetProjection, *,
    now: float,
    host_ready_at: dict[str, float] | None = None,
    authorized: bool,
) -> CampaignPlan:
    mandate.admit(now=now, authorized=authorized)
    if not isinstance(projection, BudgetProjection):
        raise ValueError("canonical budget projection required")
    rows = tuple(candidates)
    if len(rows) > mandate.limits.max_candidates:
        raise ValueError("candidate budget exceeded")
    filtered: dict[str, ResearchCandidate] = {}
    rejected: list[tuple[str, str]] = []
    for candidate in rows:
        if not isinstance(candidate, ResearchCandidate):
            raise TypeError("typed candidates are required")
        try:
            identity = validate_public_url(candidate.url, mandate)
            if candidate.depth > mandate.request.max_depth:
                raise PermissionError("depth_exceeds_mandate")
            if candidate.expected_bytes > mandate.request.max_response_bytes:
                raise PermissionError("response_cap_exceeds_mandate")
            if candidate.parent_url is not None:
                validate_public_url(candidate.parent_url, mandate)
            if identity in filtered:
                previous = filtered[identity]
                # The more restrictive byte estimate wins for an identical URL;
                # duplicate untrusted hints cannot amplify authorization.
                winner = min(
                    (previous, candidate),
                    key=lambda x: (x.expected_bytes, -x.information_gain, x.reason),
                )
                filtered[identity] = winner
                rejected.append((identity, "duplicate_candidate"))
            else:
                filtered[identity] = candidate
        except (ValueError, PermissionError) as exc:
            rejected.append((candidate.url, type(exc).__name__ + ":" + str(exc)))
    if projection.exhausted or not filtered:
        payload = {
            "mandate": mandate.fingerprint,
            "rejected": rejected,
            "blockers": projection.blockers,
        }
        return CampaignPlan(
            mandate.fingerprint, len(rows), tuple(rejected), (), 0, 0, digest(payload),
        )
    policy = mandate.scope.policy(
        max_response_bytes=mandate.request.max_response_bytes
    )
    ranked = rank_acquisition_candidates(
        (
            AcquisitionCandidate(
                row.url, row.relevance, row.information_gain,
                row.quality, row.expected_bytes,
            )
            for row in filtered.values()
        ),
        policy=policy, max_candidates=mandate.limits.max_candidates,
    )
    times = {} if host_ready_at is None else dict(host_ready_at)
    for host, ready in times.items():
        if host not in mandate.scope.allowed_hosts:
            raise PermissionError("foreign host cooldown")
        finite(ready, "host-ready time")
    candidates_by_url = {row.url: row for row in filtered.values()}
    ranked_by_url = {row.url: row for row in ranked if row.admitted}
    ordered = allocate_host_dispatches(
        ranked, now=now, host_ready_at=times,
        max_dispatch=min(mandate.limits.max_dispatches, projection.requests_remaining),
        max_per_host=mandate.limits.max_per_host,
        host_delay=max(mandate.limits.min_host_delay_seconds,
                       mandate.request.min_host_delay_seconds),
        policy=policy,
    ) if projection.requests_remaining > 0 else ()
    dispatches: list[ResearchDispatch] = []
    remaining = projection.bytes_remaining
    for item in ordered:
        original = candidates_by_url[item.url]
        rank = ranked_by_url[item.url]
        if item.ready_at >= mandate.scope.expires_at:
            rejected.append((item.url, "consent_expires_before_dispatch"))
            continue
        if original.expected_bytes > remaining:
            rejected.append((item.url, "insufficient_conservative_byte_reserve"))
            continue
        if len(dispatches) >= projection.documents_remaining:
            # Document count can be reached in the worst case when each fetch
            # yields a new document, even before the planned request cap.
            rejected.append((item.url, "document_capacity_reached"))
            continue
        remaining -= original.expected_bytes
        dispatches.append(ResearchDispatch(
            url=item.url, host=item.host, ready_at=item.ready_at,
            rank=len(dispatches) + 1, score=rank.score,
            expected_bytes=original.expected_bytes,
            parent_url=original.parent_url, depth=original.depth,
        ))
    reservation = reserve_advisory(
        projection, allocations=tuple((x.url, x.expected_bytes) for x in dispatches),
    )
    payload = {
        "schema": "skeleton.ai.dragon.campaign_plan.v1",
        "mandate": mandate.fingerprint,
        "considered": len(rows),
        "rejected": rejected,
        "dispatches": [asdict(x) for x in dispatches],
        "reservation": asdict(reservation),
    }
    return CampaignPlan(
        mandate_digest=mandate.fingerprint,
        candidates_considered=len(rows),
        rejected=tuple(rejected),
        dispatches=tuple(dispatches),
        bytes_reserved=reservation.projected_bytes,
        requests_reserved=reservation.requests,
        plan_digest=digest(payload),
    )
