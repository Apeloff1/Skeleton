"""Process-wide product-control runtime ownership.

HTTP surfaces share this factory so public readiness and secured operations
cannot accidentally instantiate independent control planes over the same
durable state.
"""
from __future__ import annotations

import os
from pathlib import Path
import threading
from typing import Any

from core.product_control_plane import ProductControlPlane

_LOCK = threading.RLock()
_CONTROL_PLANE: ProductControlPlane | None = None


def _outbox_cap() -> int:
    raw = os.environ.get("PRODUCT_CONTROL_OUTBOX_CAP", "4096").strip()
    try:
        value = int(raw)
    except (TypeError, ValueError, OverflowError) as exc:
        raise RuntimeError("PRODUCT_CONTROL_OUTBOX_CAP must be an integer") from exc
    if value < 1 or value > 1_000_000:
        raise RuntimeError("PRODUCT_CONTROL_OUTBOX_CAP must be between 1 and 1000000")
    return value


def _bootstrap_policy() -> bool:
    raw = os.environ.get("PRODUCT_CONTROL_BOOTSTRAP_POLICY", "1").strip().lower()
    if raw in {"0", "false", "no", "off"}:
        return False
    if raw in {"1", "true", "yes", "on", ""}:
        return True
    raise RuntimeError(
        "PRODUCT_CONTROL_BOOTSTRAP_POLICY must be a boolean value"
    )


def get_product_control_plane() -> ProductControlPlane:
    global _CONTROL_PLANE
    if _CONTROL_PLANE is not None:
        return _CONTROL_PLANE

    with _LOCK:
        if _CONTROL_PLANE is None:
            root = Path(
                os.environ.get("PRODUCT_CONTROL_ROOT", "data/product-control")
            )
            _CONTROL_PLANE = ProductControlPlane(
                root,
                outbox_cap=_outbox_cap(),
                bootstrap_policy=_bootstrap_policy(),
            )
        return _CONTROL_PLANE


def public_readiness(plane: ProductControlPlane | None = None) -> dict[str, Any]:
    """Return the minimum non-secret readiness projection for product clients."""

    active = plane or get_product_control_plane()
    report = active.readiness_report()
    actions = []
    for item in report.get("actions", ()):
        actions.append(
            {
                "capability_id": item["capability_id"],
                "action": item["action"],
                "state": item["state"],
                "replay_safe": bool(item.get("replay_safe", False)),
                "effect_class": item.get("effect_class"),
                "blockers": list(item.get("blockers") or ()),
            }
        )
    return {
        "canonical_actions": int(report.get("canonical_actions", 0)),
        "ready_actions": int(report.get("ready_actions", 0)),
        "ready_pct": float(report.get("ready_pct", 0.0)),
        "governed_unbound": int(report.get("governed_unbound", 0)),
        "unsafe_actions": int(report.get("unsafe_actions", 0)),
        "policy_gaps": int(report.get("policy_gaps", 0)),
        "actions": actions,
        "attestation_sha256": str(report.get("attestation_sha256", "")),
    }
