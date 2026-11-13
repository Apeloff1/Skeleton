"""Expiry-horizon advisory for a research snapshot under explicit operator consent.

No policy snapshot exposes exact per-source expiry times in this stage, so
this uses the **mandate consent lifetime only** and clearly does not infer
individual source-use authorizations, network permissions or safety.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from math import isfinite

from ..contracts import CampaignMandate, digest, finite
from .frames import FrameSet


@dataclass(frozen=True)
class ConsentHorizon:
    mandate_digest: str
    frame_set_digest: str
    evaluated_at: float
    consent_expires_at: float
    consent_seconds_remaining: float
    chosen_warning_window_seconds: float
    warning: str
    requires_fresh_policy_for_future_use: bool
    report_digest: str
    source_policy_expiry_known: bool = False
    recrawl_authorized: bool = False
    knowledge_promotion_authorized: bool = False


def inspect_consent_horizon(
    mandate: CampaignMandate, frames: FrameSet,
    *, now: float, authorized: bool,
    warn_before_seconds: float = 300.0,
) -> ConsentHorizon:
    mandate.admit(now=now, authorized=authorized)
    if not isinstance(frames, FrameSet):
        raise TypeError("exact forensic source frames required")
    if frames.mandate_digest != mandate.fingerprint:
        raise PermissionError("consent horizon is for a different mandate")
    window = finite(warn_before_seconds, "consent warning window", 1, 86400)
    remaining = mandate.scope.expires_at - now
    if remaining <= 0:
        raise PermissionError("expired mandate cannot be analyzed")
    warning = "renewal_review_due" if remaining <= window else "current_consent_window"
    payload = {
        "mandate": mandate.fingerprint, "frames": frames.frame_set_digest,
        "now": now, "expiry": mandate.scope.expires_at,
        "window": window, "warning": warning,
    }
    return ConsentHorizon(
        mandate.fingerprint, frames.frame_set_digest,
        now, mandate.scope.expires_at, round(remaining, 6), window,
        warning, True, digest(payload),
    )
