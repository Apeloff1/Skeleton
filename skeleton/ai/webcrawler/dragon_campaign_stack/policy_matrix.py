"""Conservative per-source policy projection tied to the authoritative run.

Source use and withdrawal authority belongs to the application's protected
Mongo policy documents. An operator must supply a complete, current,
authenticated policy snapshot. These receipts *do not authenticate* that
snapshot: they refuse missing, stale, extra, duplicated and mismatched rows.
A review-allowed entry never licenses training, republication or acquisition.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable

from ..operations import CrawlRun
from .contracts import (
    CampaignMandate, bounded_text, digest, ensure_snapshot_scope,
    exact_digest, finite, integer,
)


@dataclass(frozen=True)
class SourcePolicyDecision:
    source_id: str
    source_hash: str
    consent_id: str
    policy_revision: int
    effective_at: float
    expires_at: float
    status: str
    authority_reference: str
    purpose: str
    can_train: bool = False
    can_publish: bool = False

    def __post_init__(self) -> None:
        exact_digest(self.source_id, "policy source")
        exact_digest(self.source_hash, "policy content")
        bounded_text(self.consent_id, "source consent")
        bounded_text(self.authority_reference, "policy authority reference", 512)
        bounded_text(self.purpose, "source policy purpose", 1024)
        integer(self.policy_revision, "policy revision", 0, 2**31-1)
        finite(self.effective_at, "source policy effective clock")
        finite(self.expires_at, "source policy expiry clock")
        if self.expires_at <= self.effective_at:
            raise ValueError("invalid source policy lifetime")
        if self.status not in ("review_scoped", "withdrawn", "embargoed", "rights_unknown"):
            raise ValueError("unknown protected source policy state")
        if self.can_train is not False or self.can_publish is not False:
            raise PermissionError("research inspection cannot authorize publication or training")


@dataclass(frozen=True)
class SourcePolicyFinding:
    source_id: str
    status: str
    policy_revision: int
    eligible_for_inspection: bool
    reason: str


@dataclass(frozen=True)
class SourcePolicyProjection:
    mandate_digest: str
    source_snapshot_digest: str
    source_count: int
    allowed_source_ids: tuple[str, ...]
    excluded_source_ids: tuple[str, ...]
    decisions: tuple[SourcePolicyFinding, ...]
    policy_digest: str
    asserted_policy_source: str = "authenticated_application_caller_required"
    authentication_proven_by_receipt: bool = False
    training_authorized: bool = False
    publication_authorized: bool = False


def project_source_policy(
    mandate: CampaignMandate,
    snapshot: dict[str, object],
    decisions: Iterable[SourcePolicyDecision],
    *,
    now: float,
    authorized: bool,
    policy_snapshot_authenticated: bool,
    max_decisions: int = 128,
) -> SourcePolicyProjection:
    mandate.admit(now=now, authorized=authorized)
    ensure_snapshot_scope(snapshot, mandate)
    integer(max_decisions, "policy row cap", 1, 512)
    if policy_snapshot_authenticated is not True:
        raise PermissionError("current application source-policy authority required")
    canonical = CrawlRun.from_snapshot(snapshot).snapshot()
    rows = tuple(decisions)
    if len(rows) != len(canonical["sources"]) or len(rows) > max_decisions:
        raise PermissionError("incomplete or excessive source-policy universe")
    by_id = {}
    for decision in rows:
        if not isinstance(decision, SourcePolicyDecision):
            raise TypeError("typed protected policy decision required")
        if decision.source_id in by_id:
            raise ValueError("duplicate protected source-policy row")
        source = canonical["sources"].get(decision.source_id)
        if source is None:
            raise PermissionError("policy references an unknown captured source")
        if source["content_hash"] != decision.source_hash:
            raise PermissionError("policy bound to a different source revision")
        if decision.consent_id != mandate.scope.consent_id:
            raise PermissionError("protected policy uses different consent")
        if decision.purpose != mandate.scope.purpose:
            raise PermissionError("policy purpose differs from approved mandate")
        by_id[decision.source_id] = decision
    if set(by_id) != set(canonical["sources"]):
        raise PermissionError("some captured sources lack current policy")
    observed, allowed, excluded = [], [], []
    for source_id, decision in sorted(by_id.items()):
        current = decision.effective_at <= now < decision.expires_at
        eligible = current and decision.status == "review_scoped"
        reason = ("source_review_only_untrusted" if eligible else
                  "source_policy_not_yet_effective" if now < decision.effective_at else
                  "source_policy_expired" if now >= decision.expires_at else
                  "source_policy_" + decision.status)
        observed.append(SourcePolicyFinding(
            source_id, decision.status, decision.policy_revision, eligible, reason,
        ))
        (allowed if eligible else excluded).append(source_id)
    payload = {
        "mandate": mandate.fingerprint,
        "snapshot": canonical["snapshot_digest"],
        "policy": [asdict(x) for x in sorted(rows, key=lambda x: x.source_id)],
        "observed": [asdict(x) for x in observed],
        "clock": now,
    }
    return SourcePolicyProjection(
        mandate_digest=mandate.fingerprint,
        source_snapshot_digest=canonical["snapshot_digest"],
        source_count=len(rows),
        allowed_source_ids=tuple(allowed),
        excluded_source_ids=tuple(excluded),
        decisions=tuple(observed), policy_digest=digest(payload),
    )
