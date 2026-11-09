"""Composed dark card for the unwired spine.

Reads the motor witness, the dispatch witness, and the merge gate. A green
flag on any input fails closed. The card does not import Motor, does not
start the dispatcher, and does not merge.
"""

from __future__ import annotations

from typing import Any


class SpineDarkError(RuntimeError):
    """Dark card rejected its inputs. Not a maturity signal."""


class SpineDark:
    """Bundle the unread proofs. hit stays false."""

    def card(self, motor: dict[str, Any], dispatch: dict[str, Any], merge: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(motor, dict) or not isinstance(dispatch, dict) or not isinstance(merge, dict):
            raise SpineDarkError("motor, dispatch, and merge must be cards")
        if motor.get("live_motor") is True or motor.get("driver_imports", 0) != 0:
            raise SpineDarkError("motor witness is not dark")
        if dispatch.get("called") is True or dispatch.get("dispatcher_running") is True:
            raise SpineDarkError("dispatcher witness is not dark")
        if merge.get("merged") is True or merge.get("ci_green") is True:
            raise SpineDarkError("merge gate is not dark")
        return {
            "kind": "spine_dark",
            "hit": False,
            "law": "unwired-surfaces-stay-dark",
            "citation": "VOL-134",
            "live_motor": False,
            "dispatcher_running": False,
            "ci_green": False,
            "merged": False,
            "apply_landed": False,
            "stored_prose": 0,
            "completion_checkbox": False,
            "implementation_signature": False,
            "verification_signature": False,
        }
