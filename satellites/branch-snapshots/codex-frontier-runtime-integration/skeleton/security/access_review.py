"""Access review — periodic certification of RBAC grants.

Schedules and tracks access certification campaigns: reviewers
confirm or revoke each actor's grants, stale grants (unused in N
days) are flagged automatically, and completed campaigns produce a
compliance report. Integrates with RBAC and the audit log.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class GrantReview:
    actor: str
    role: str
    decision: Optional[str] = None
    reviewer: Optional[str] = None
    decided_ns: int = 0
    last_used_ns: Optional[int] = None


@dataclass
class Campaign:
    campaign_id: str
    started_ns: int
    deadline_ns: int
    reviews: List[GrantReview] = field(default_factory=list)
    closed: bool = False


class AccessReview:
    """Access certification campaigns with stale-grant detection."""

    def __init__(self, rbac: Any = None, stale_days: float = 90.0):
        self._rbac = rbac
        self.stale_days = stale_days
        self._campaigns: Dict[str, Campaign] = {}
        self._counter = 0
        self._usage: Dict[str, int] = {}

    def record_usage(self, actor: str, role: str) -> None:
        self._usage[f"{actor}:{role}"] = time.time_ns()

    def start_campaign(self, actors_roles: Dict[str, List[str]],
                       duration_s: float = 604800.0) -> Campaign:
        self._counter += 1
        campaign = Campaign(
            campaign_id=f"cert-{self._counter:04d}",
            started_ns=time.time_ns(),
            deadline_ns=time.time_ns() + int(duration_s * 1e9),
        )
        for actor, roles in actors_roles.items():
            for role in roles:
                campaign.reviews.append(GrantReview(
                    actor=actor, role=role,
                    last_used_ns=self._usage.get(f"{actor}:{role}"),
                ))
        self._campaigns[campaign.campaign_id] = campaign
        return campaign

    def decide(self, campaign_id: str, actor: str, role: str,
               decision: str, reviewer: str) -> bool:
        campaign = self._campaigns.get(campaign_id)
        if not campaign or campaign.closed:
            return False
        for review in campaign.reviews:
            if review.actor == actor and review.role == role and review.decision is None:
                review.decision = decision
                review.reviewer = reviewer
                review.decided_ns = time.time_ns()
                if decision == "revoked" and self._rbac:
                    self._rbac.revoke(actor, role)
                return True
        return False

    def stale_grants(self, campaign_id: str) -> List[Dict[str, Any]]:
        campaign = self._campaigns.get(campaign_id)
        if not campaign:
            return []
        cutoff = time.time_ns() - int(self.stale_days * 86400 * 1e9)
        stale = []
        for r in campaign.reviews:
            if r.last_used_ns is None or r.last_used_ns < cutoff:
                stale.append({"actor": r.actor, "role": r.role,
                              "last_used_ns": r.last_used_ns, "never_used": r.last_used_ns is None})
        return stale

    def close(self, campaign_id: str) -> Dict[str, Any]:
        campaign = self._campaigns.get(campaign_id)
        if not campaign:
            return {"closed": False, "reason": "not found"}
        campaign.closed = True
        return self.report(campaign_id)

    def report(self, campaign_id: str) -> Dict[str, Any]:
        campaign = self._campaigns.get(campaign_id)
        if not campaign:
            return {"error": "not found"}
        certified = [r for r in campaign.reviews if r.decision == "certified"]
        revoked = [r for r in campaign.reviews if r.decision == "revoked"]
        pending = [r for r in campaign.reviews if r.decision is None]
        return {
            "campaign_id": campaign_id,
            "closed": campaign.closed,
            "total": len(campaign.reviews),
            "certified": len(certified),
            "revoked": len(revoked),
            "pending": len(pending),
            "pending_items": [{"actor": r.actor, "role": r.role} for r in pending],
            "stale": self.stale_grants(campaign_id),
            "completion": round((len(certified) + len(revoked)) / len(campaign.reviews), 3) if campaign.reviews else 1.0,
        }

    def card(self) -> Dict[str, Any]:
        return {
            "kind": "access-review-card",
            "campaigns": {cid: {"closed": c.closed, "reviews": len(c.reviews)} for cid, c in self._campaigns.items()},
            "open_campaigns": len([c for c in self._campaigns.values() if not c.closed]),
        }
