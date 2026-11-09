"""Epoch witness beside an unread probe.

Records the fence epoch before and after a probe card. A moved epoch fails
closed. The witness does not advance the fence.
"""

from __future__ import annotations

from typing import Any


class SpineEpochWitnessError(RuntimeError):
    """Epoch witness rejected its inputs. Not a maturity signal."""


class SpineEpochWitness:
    """Prove a side card did not move the fence."""

    def card(self, *, epoch_before: int, epoch_after: int, side: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(epoch_before, int) or not isinstance(epoch_after, int):
            raise SpineEpochWitnessError("epochs must be ints")
        if epoch_before < 0 or epoch_after < 0:
            raise SpineEpochWitnessError("epochs must be non-negative")
        if not isinstance(side, dict):
            raise SpineEpochWitnessError("side must be a card")
        if epoch_before != epoch_after:
            raise SpineEpochWitnessError("side card moved the fence")
        return {
            "kind": "spine_epoch_witness",
            "hit": True,
            "law": "side-card-epoch-unchanged",
            "citation": "VOL-134",
            "epoch_before": epoch_before,
            "epoch_after": epoch_after,
            "moved": False,
            "side_kind": side.get("kind"),
            "stored_prose": 0,
            "completion_checkbox": False,
            "implementation_signature": False,
            "verification_signature": False,
        }
