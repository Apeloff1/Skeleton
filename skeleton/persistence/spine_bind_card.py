"""Join quiet, dark, and epoch into one unread bind card.

The card is a read. It does not start the dispatcher, does not import Motor,
and does not advance a fence. A green flag on any input fails closed.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any


class SpineBindCardError(RuntimeError):
    """Bind card rejected its inputs. Not a maturity signal."""


_QUIET_KIND = "spine_quiet_witness"
_DARK_KIND = "spine_dark"
_EPOCH_KIND = "spine_epoch_witness"
_LAW = "bind-card-stays-dark"
_CITATION = "VOL-134"

_DARK_FLAGS = (
    "live_motor",
    "dispatcher_running",
    "ci_green",
    "merged",
    "apply_landed",
)
_QUIET_FLAGS = ("live_motor", "merged")


def _canon(card: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(card, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


class SpineBindCard:
    """Seal three dark proofs. hit stays false."""

    def card(
        self,
        *,
        tenant_id: str,
        quiet: dict[str, Any],
        dark: dict[str, Any],
        epoch: dict[str, Any],
    ) -> dict[str, Any]:
        if not isinstance(tenant_id, str) or not tenant_id.strip():
            raise SpineBindCardError("tenant_id must be non-empty text")
        self._require_quiet(tenant_id, quiet)
        self._require_dark(dark)
        epoch_before, epoch_after = self._require_epoch(epoch)
        body = {
            "kind": "spine_bind_card",
            "hit": False,
            "law": _LAW,
            "citation": _CITATION,
            "tenant_id": tenant_id,
            "quiet_digest": quiet.get("digest"),
            "dark_kind": dark.get("kind"),
            "epoch_before": epoch_before,
            "epoch_after": epoch_after,
            "moved": False,
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
        body["digest"] = _canon(
            {key: value for key, value in body.items() if key != "digest"}
        )
        return body

    def _require_quiet(self, tenant_id: str, quiet: dict[str, Any]) -> None:
        if not isinstance(quiet, dict) or quiet.get("kind") != _QUIET_KIND:
            raise SpineBindCardError("quiet must be a spine_quiet_witness card")
        if quiet.get("tenant_id") != tenant_id:
            raise SpineBindCardError("quiet tenant does not match")
        if quiet.get("seen") is not True:
            raise SpineBindCardError("quiet row was not seen")
        if quiet.get("law") != "quiet-row-stays-dark":
            raise SpineBindCardError("quiet law mismatch")
        for flag in _QUIET_FLAGS:
            if quiet.get(flag) is not False:
                raise SpineBindCardError("quiet row is not dark")
        digest = quiet.get("digest")
        if not isinstance(digest, str) or len(digest) != 64:
            raise SpineBindCardError("quiet digest missing")

    def _require_dark(self, dark: dict[str, Any]) -> None:
        if not isinstance(dark, dict) or dark.get("kind") != _DARK_KIND:
            raise SpineBindCardError("dark must be a spine_dark card")
        if dark.get("law") != "unwired-surfaces-stay-dark":
            raise SpineBindCardError("dark law mismatch")
        if dark.get("hit") is not False:
            raise SpineBindCardError("dark hit must stay false")
        for flag in _DARK_FLAGS:
            if dark.get(flag) is not False:
                raise SpineBindCardError("dark card is not dark")

    def _require_epoch(self, epoch: dict[str, Any]) -> tuple[int, int]:
        if not isinstance(epoch, dict) or epoch.get("kind") != _EPOCH_KIND:
            raise SpineBindCardError("epoch must be a spine_epoch_witness card")
        if epoch.get("moved") is not False:
            raise SpineBindCardError("epoch witness moved")
        before = epoch.get("epoch_before")
        after = epoch.get("epoch_after")
        if not isinstance(before, int) or not isinstance(after, int):
            raise SpineBindCardError("epochs must be ints")
        if before < 0 or after < 0 or before != after:
            raise SpineBindCardError("side card moved the fence")
        return before, after
