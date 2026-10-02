"""Epoch probe beside a bind refusal.

The refusal card epoch and the side probe must match. A moved epoch fails
closed. The probe does not advance a fence.
"""

from __future__ import annotations

from typing import Any


class SpineBindHoldFenceError(RuntimeError):
    """Fence probe rejected its inputs. Not a maturity signal."""


class SpineBindHoldFence:
    """Prove a refusal did not move the fence."""

    def card(self, refusal: dict[str, Any], *, epoch_before: int, epoch_after: int) -> dict[str, Any]:
        if not isinstance(refusal, dict) or refusal.get("kind") != "spine_bind_hold":
            raise SpineBindHoldFenceError("refusal must be a spine_bind_hold")
        if refusal.get("moved") is not False or refusal.get("applied") != 0:
            raise SpineBindHoldFenceError("refusal is not dark")
        if isinstance(epoch_before, bool) or not isinstance(epoch_before, int):
            raise SpineBindHoldFenceError("epochs must be ints")
        if isinstance(epoch_after, bool) or not isinstance(epoch_after, int):
            raise SpineBindHoldFenceError("epochs must be ints")
        if epoch_before < 0 or epoch_after < 0 or epoch_before != epoch_after:
            raise SpineBindHoldFenceError("side probe moved the fence")
        if refusal.get("epoch_before") != epoch_before or refusal.get("epoch_after") != epoch_after:
            raise SpineBindHoldFenceError("refusal epoch does not match the probe")
        return {
            "kind": "spine_bind_hold_fence",
            "hit": True,
            "law": "refusal-epoch-unchanged",
            "citation": "VOL-134",
            "tenant_id": refusal.get("tenant_id"),
            "outbox_id": refusal.get("outbox_id"),
            "epoch_before": epoch_before,
            "epoch_after": epoch_after,
            "moved": False,
            "applied": 0,
            "stored_prose": 0,
            "completion_checkbox": False,
            "implementation_signature": False,
            "verification_signature": False,
        }
