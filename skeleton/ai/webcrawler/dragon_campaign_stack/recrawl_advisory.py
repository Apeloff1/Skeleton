"""Source-bound adaptive recrawl suggestions without extending consent.

An elapsed freshness interval does not create acquisition authorization.
Future time windows beyond the consent expiry require a new user grant.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable

from ..dragon_mission_scheduler import RecrawlSource, plan_adaptive_recrawls
from .contracts import CampaignMandate, digest, exact_digest, finite, integer, validate_public_url
from .evidence import SourceInspection


@dataclass(frozen=True)
class RefreshObservation:
    source_id: str
    last_changed: float
    volatility: float
    importance: float
    consecutive_unchanged: int = 0

    def __post_init__(self):
        exact_digest(self.source_id, "refresh source")
        finite(self.last_changed, "last changed")
        finite(self.volatility, "volatility", 0, 1)
        finite(self.importance, "importance", 0, 1)
        integer(self.consecutive_unchanged, "unchanged count", 0, 100000)


@dataclass(frozen=True)
class RefreshProposal:
    source_id: str
    url: str
    next_due: float
    due: bool
    urgency: float
    interval: float
    permitted_under_current_consent: bool
    reason: str


@dataclass(frozen=True)
class RefreshPortfolio:
    proposals: tuple[RefreshProposal, ...]
    due_now: int
    new_consent_required: int
    fingerprint: str
    network_executed: bool = False


def propose_adaptive_refresh(
    mandate: CampaignMandate,
    retained: Iterable[SourceInspection],
    observations: Iterable[RefreshObservation], *,
    now: float,
    authorized: bool,
    minimum_interval: float = 3600,
    maximum_interval: float = 30 * 86400,
) -> RefreshPortfolio:
    mandate.admit(now=now, authorized=authorized)
    sources = tuple(retained)
    obs = tuple(observations)
    if len(sources) > mandate.request.max_documents or len(obs) > len(sources):
        raise ValueError("refresh portfolio capacity exceeded")
    by_id = {}
    for item in sources:
        if not isinstance(item, SourceInspection):
            raise TypeError("typed retained source required")
        if item.source_id in by_id:
            raise ValueError("duplicate retained source")
        validate_public_url(item.canonical_url, mandate)
        by_id[item.source_id] = item
    hints = []
    seen = set()
    for hint in obs:
        if not isinstance(hint, RefreshObservation):
            raise TypeError("typed refresh observation required")
        if hint.source_id in seen:
            raise ValueError("duplicate source refresh observation")
        seen.add(hint.source_id)
        actual = by_id.get(hint.source_id)
        if actual is None:
            raise PermissionError("unretained recrawl target")
        if not 0 <= hint.last_changed <= actual.fetched_at <= now:
            raise ValueError("impossible source chronology")
        hints.append(RecrawlSource(
            source_id=hint.source_id,
            canonical_url=actual.canonical_url,
            last_fetched=actual.fetched_at,
            last_changed=hint.last_changed,
            volatility=hint.volatility,
            importance=hint.importance,
            consecutive_unchanged=hint.consecutive_unchanged,
        ))
    planned = plan_adaptive_recrawls(
        hints, now=now, minimum_interval=minimum_interval,
        maximum_interval=maximum_interval, max_sources=mandate.request.max_documents,
    )
    output = []
    for due in planned:
        original = by_id[due.source_id]
        future_expired = due.next_due >= mandate.scope.expires_at
        permission = due.due and not future_expired
        # Any actual fetch still requires a separate fresh, versioned consent
        # check and the canonical runner's existing network/budget admission.
        if not original.inspectable:
            reason = "original_source_under_review"
        elif future_expired:
            reason = "fresh_capture_consent_required"
        elif not due.due:
            reason = "not_yet_due"
        else:
            reason = "due_candidate_requires_canonical_admission"
        output.append(RefreshProposal(
            source_id=due.source_id, url=original.canonical_url,
            next_due=due.next_due, due=due.due, urgency=due.urgency,
            interval=due.revisit_interval,
            permitted_under_current_consent=permission and original.inspectable,
            reason=reason,
        ))
    payload = {
        "mandate": mandate.fingerprint,
        "at": now,
        "portfolio": [asdict(x) for x in output],
        "network": False,
    }
    return RefreshPortfolio(
        proposals=tuple(output),
        due_now=sum(x.due for x in output),
        new_consent_required=sum(x.reason == "fresh_capture_consent_required" for x in output),
        fingerprint=digest(payload),
    )
