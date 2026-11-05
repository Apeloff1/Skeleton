"""Environment promotion gates (dev -> staging -> production)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping

from skeleton.build.delivery._util import DeliveryError
from skeleton.build.delivery.release_history import ReleaseHistory
from skeleton.build.delivery.version import Version

PROMOTION_ORDER = ("dev", "staging", "production")


@dataclass(frozen=True)
class PromotionRequest:
    release_id: str
    version: str
    manifest_digest: str
    source_tier: str
    target_tier: str
    approvals: tuple[str, ...] = ()
    checks: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class PromotionVerdict:
    allowed: bool
    reasons: tuple[str, ...]


def required_approvals(target_tier: str) -> int:
    return {"dev": 0, "staging": 1, "production": 2}[target_tier]


def evaluate(
    request: PromotionRequest,
    *,
    histories: Mapping[str, ReleaseHistory],
    required_checks: Iterable[str] = (),
    freeze: bool = False,
) -> PromotionVerdict:
    reasons: list[str] = []
    if request.source_tier not in PROMOTION_ORDER or request.target_tier not in PROMOTION_ORDER:
        raise DeliveryError("unknown tier")
    src = PROMOTION_ORDER.index(request.source_tier)
    dst = PROMOTION_ORDER.index(request.target_tier)
    if dst != src + 1:
        reasons.append(f"skip:{request.source_tier}->{request.target_tier}")
    history = histories.get(request.source_tier)
    current = history.current() if history else None
    if current is None or current.release_id != request.release_id:
        reasons.append("not-live-in-source")
    elif current.manifest_digest != request.manifest_digest:
        reasons.append("manifest-mismatch")
    if request.target_tier == "production" and Version.parse(request.version).is_prerelease:
        reasons.append("prerelease-to-production")
    approvers = set(request.approvals)
    if len(approvers) < required_approvals(request.target_tier):
        reasons.append(f"approvals:{len(approvers)}<{required_approvals(request.target_tier)}")
    checks = dict(request.checks)
    for name in required_checks:
        status = checks.get(name)
        if status != "success":
            reasons.append(f"check:{name}:{status or 'missing'}")
    if freeze and request.target_tier == "production":
        reasons.append("change-freeze")
    return PromotionVerdict(not reasons, tuple(reasons))
