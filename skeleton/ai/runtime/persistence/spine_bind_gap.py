"""Join a bind card to an unread sequence gap.

Missing sequence numbers stay missing. A foreign gap fails closed. The join
does not fill the gap, does not advance the fence, and does not claim a
surface.
"""

from __future__ import annotations

from typing import Any


class SpineBindGapError(RuntimeError):
    """Bind gap rejected its inputs. Not a maturity signal."""


class SpineBindGap:
    """Prove a gap beside a bind card was not filled."""

    def card(self, *, bind: dict[str, Any], gap: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(bind, dict) or bind.get("kind") != "spine_bind_card":
            raise SpineBindGapError("bind must be a spine_bind_card")
        if not isinstance(gap, dict) or gap.get("kind") != "spine_unread_gap":
            raise SpineBindGapError("gap must be a spine_unread_gap card")
        tenant_id = bind.get("tenant_id")
        if not isinstance(tenant_id, str) or not tenant_id.strip():
            raise SpineBindGapError("bind tenant missing")
        if gap.get("tenant_id") != tenant_id:
            raise SpineBindGapError("gap tenant does not match")
        if bind.get("moved") is not False or bind.get("epoch_before") != bind.get("epoch_after"):
            raise SpineBindGapError("bind card moved the fence")
        if gap.get("green") is True:
            raise SpineBindGapError("gap card is not unread")
        missing = gap.get("missing")
        seen = gap.get("seen")
        if not isinstance(missing, list) or not isinstance(seen, list):
            raise SpineBindGapError("gap sequences missing")
        if any(not isinstance(item, int) or item < 1 for item in missing):
            raise SpineBindGapError("gap sequence is not a positive int")
        if any(item in seen for item in missing):
            raise SpineBindGapError("gap overlaps a seen sequence")
        epoch = bind.get("epoch_before")
        if not isinstance(epoch, int) or epoch < 0:
            raise SpineBindGapError("bind epoch missing")
        return {
            "kind": "spine_bind_gap",
            "hit": False,
            "law": "bind-gap-not-filled",
            "citation": "VOL-134",
            "tenant_id": tenant_id,
            "table": gap.get("table"),
            "missing": list(missing),
            "seen": list(seen),
            "filled": False,
            "epoch_before": epoch,
            "epoch_after": epoch,
            "moved": False,
            "green": False,
            "apply_landed": False,
            "stored_prose": 0,
            "completion_checkbox": False,
            "implementation_signature": False,
            "verification_signature": False,
        }
