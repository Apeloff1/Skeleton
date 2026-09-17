"""Creator-lane approval boundary. Intent stays pending until stamped."""

from __future__ import annotations

from typing import Any, Mapping

from skeleton.game.intent import compile_intent


class ApprovalError(ValueError):
    """Approval boundary contract violation."""


def stamp(vision: str, *, actor: str = "operator", approve: bool = True) -> dict[str, Any]:
    intent = compile_intent(vision)
    name = str(actor or "").strip().lower()
    if name not in {"operator", "doctor", "factory"}:
        raise ApprovalError("unknown actor")
    if intent["conflicts"] and approve:
        raise ApprovalError("conflicts block approval")
    state = "approved" if approve else "rejected"
    return {
        "kind": "approval",
        "actor": name,
        "state": state,
        "intent": intent,
        "approval": state,
        "stored_prose": 0,
    }


def require(card: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(card, Mapping):
        raise ApprovalError("approval card required")
    if card.get("state") != "approved":
        raise ApprovalError("intent is not approved")
    if card.get("stored_prose") != 0:
        raise ApprovalError("prose on approval card")
    return dict(card)
