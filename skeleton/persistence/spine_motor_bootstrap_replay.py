"""Replay-equivalence proof for driver-injected async Mongo bootstrap cards."""

from __future__ import annotations

from typing import Any


class SpineMotorBootstrapReplayError(RuntimeError):
    """Bootstrap replay evidence is not equivalent."""


class SpineMotorBootstrapReplay:
    """Compare two bootstrap runs without activating a live driver."""

    def card(
        self,
        *,
        first: dict[str, Any],
        second: dict[str, Any],
    ) -> dict[str, Any]:
        for name, card in (("first", first), ("second", second)):
            if not isinstance(card, dict) or card.get("kind") != "spine_motor_bootstrap":
                raise SpineMotorBootstrapReplayError(f"{name} bootstrap kind mismatch")
            if card.get("live_motor") is not False or card.get("activated") is not False:
                raise SpineMotorBootstrapReplayError(f"{name} bootstrap gained authority")
            if card.get("failures") != 0 or card.get("missing") != 0:
                raise SpineMotorBootstrapReplayError(f"{name} bootstrap incomplete")

        if first.get("plan_digest") != second.get("plan_digest"):
            raise SpineMotorBootstrapReplayError("bootstrap replay plan changed")
        if first.get("planned") != second.get("planned"):
            raise SpineMotorBootstrapReplayError("bootstrap replay cardinality changed")
        if first.get("applied") != second.get("applied"):
            raise SpineMotorBootstrapReplayError("bootstrap replay applied count changed")
        if first.get("results") != second.get("results"):
            raise SpineMotorBootstrapReplayError("bootstrap replay result changed")

        return {
            "kind": "spine_motor_bootstrap_replay",
            "hit": True,
            "law": "bootstrap-replay-is-equivalent",
            "citation": "VOL-134",
            "plan_digest": first.get("plan_digest"),
            "applied": first.get("applied"),
            "equivalent": True,
            "live_motor": False,
            "driver_imported": False,
            "activated": False,
            "stored_prose": 0,
            "completion_checkbox": False,
            "implementation_signature": False,
            "verification_signature": False,
        }
