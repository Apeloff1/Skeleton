"""Join a release proof, a ticket proof, and a fence probe.

The three cards must name the same tenant and outbox id. A released hold, a
consumed ticket, or a moved epoch fails closed. The join does not write.
"""

from __future__ import annotations

from typing import Any


class SpineBindHoldAgreeError(RuntimeError):
    """Agree join rejected its inputs. Not a maturity signal."""


class SpineBindHoldAgree:
    """Require release, ticket, and fence to agree. Do not apply."""

    def card(
        self,
        *,
        release: dict[str, Any],
        ticket: dict[str, Any],
        fence: dict[str, Any],
    ) -> dict[str, Any]:
        self._require(release, "spine_bind_hold_release")
        self._require(ticket, "spine_bind_hold_ticket")
        self._require(fence, "spine_bind_hold_fence")
        if release.get("released") is not False or release.get("applied") != 0:
            raise SpineBindHoldAgreeError("release proof is not dark")
        if ticket.get("consumed") != 0 or ticket.get("applied") != 0:
            raise SpineBindHoldAgreeError("ticket proof is not dark")
        if fence.get("moved") is not False or fence.get("applied") != 0:
            raise SpineBindHoldAgreeError("fence probe moved")
        tenant_id = release.get("tenant_id")
        outbox_id = release.get("outbox_id")
        if ticket.get("tenant_id") != tenant_id or fence.get("tenant_id") != tenant_id:
            raise SpineBindHoldAgreeError("tenant does not agree")
        if ticket.get("outbox_id") != outbox_id or fence.get("outbox_id") != outbox_id:
            raise SpineBindHoldAgreeError("outbox id does not agree")
        epoch = fence.get("epoch_before")
        if not isinstance(epoch, int) or epoch < 0 or epoch != fence.get("epoch_after"):
            raise SpineBindHoldAgreeError("fence epoch moved")
        if release.get("epoch_before") != epoch or release.get("epoch_after") != epoch:
            raise SpineBindHoldAgreeError("release epoch does not agree")
        hold_id = release.get("hold_id")
        if not isinstance(hold_id, int) or hold_id < 1:
            raise SpineBindHoldAgreeError("hold_id must be a positive int")
        tickets = ticket.get("tickets")
        if not isinstance(tickets, int) or tickets < 0:
            raise SpineBindHoldAgreeError("ticket count missing")
        return {
            "kind": "spine_bind_hold_agree",
            "hit": False,
            "law": "release-ticket-fence-agree",
            "citation": "VOL-134",
            "tenant_id": tenant_id,
            "outbox_id": outbox_id,
            "hold_id": hold_id,
            "tickets": tickets,
            "epoch": epoch,
            "released": False,
            "consumed": 0,
            "moved": False,
            "applied": 0,
            "sealed": False,
            "stored_prose": 0,
            "completion_checkbox": False,
            "implementation_signature": False,
            "verification_signature": False,
        }

    def _require(self, card: dict[str, Any], kind: str) -> None:
        if not isinstance(card, dict) or card.get("kind") != kind:
            raise SpineBindHoldAgreeError(f"card must be a {kind}")
        if not isinstance(card.get("tenant_id"), str) or not card["tenant_id"].strip():
            raise SpineBindHoldAgreeError("tenant_id must be non-empty text")
        if not isinstance(card.get("outbox_id"), str) or not card["outbox_id"].strip():
            raise SpineBindHoldAgreeError("outbox_id must be non-empty text")
