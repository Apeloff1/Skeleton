"""Deterministic bundle joining a recovery checkpoint and its chain."""

from __future__ import annotations

import hashlib
import json
from typing import Any


class SpineBindBundleError(RuntimeError):
    """Bind bundle rejected its inputs. Not a maturity signal."""


def _digest(payload: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


class SpineBindBundle:
    """Bundle checkpoint evidence without granting activation authority."""

    def card(
        self,
        *,
        checkpoint: dict[str, Any],
        replay: dict[str, Any],
        tenant: dict[str, Any],
        chain: dict[str, Any],
    ) -> dict[str, Any]:
        cards = (checkpoint, replay, tenant, chain)
        if not all(isinstance(card, dict) for card in cards):
            raise SpineBindBundleError("bundle inputs must be cards")
        if checkpoint.get("kind") != "spine_bind_checkpoint":
            raise SpineBindBundleError("checkpoint kind mismatch")
        if replay.get("kind") != "spine_bind_checkpoint_replay":
            raise SpineBindBundleError("replay kind mismatch")
        if tenant.get("kind") != "spine_bind_checkpoint_tenant":
            raise SpineBindBundleError("tenant kind mismatch")
        if chain.get("kind") != "spine_bind_checkpoint_chain":
            raise SpineBindBundleError("chain kind mismatch")

        tenant_id = checkpoint.get("tenant_id")
        if not isinstance(tenant_id, str) or not tenant_id.strip():
            raise SpineBindBundleError("checkpoint tenant missing")
        if any(card.get("tenant_id") != tenant_id for card in cards[1:]):
            raise SpineBindBundleError("bundle tenant mismatch")
        digest = checkpoint.get("recovery_digest")
        if replay.get("recovery_digest") != digest:
            raise SpineBindBundleError("replay digest mismatch")
        if digest not in tenant.get("digests", []):
            raise SpineBindBundleError("tenant view does not contain checkpoint")
        if tenant.get("foreign") != 0:
            raise SpineBindBundleError("foreign checkpoint visible")
        if replay.get("inserted") is not False or replay.get("rewritten") is not False:
            raise SpineBindBundleError("replay mutated checkpoint")
        if chain.get("rewritten") is not False:
            raise SpineBindBundleError("checkpoint chain rewritten")
        for card in cards:
            if card.get("activated") is not False:
                raise SpineBindBundleError("bundle input activated")

        body = {
            "kind": "spine_bind_bundle",
            "hit": False,
            "law": "checkpoint-bundle-is-not-activation",
            "citation": "VOL-134",
            "tenant_id": tenant_id,
            "recovery_digest": digest,
            "checkpoint_chain_digest": chain.get("digest"),
            "checkpoint_rows": chain.get("rows"),
            "foreign": 0,
            "inserted_on_replay": False,
            "rewritten": False,
            "activated": False,
            "apply_landed": False,
            "live_motor": False,
            "dispatcher_running": False,
            "ci_green": False,
            "merged": False,
            "stored_prose": 0,
            "completion_checkbox": False,
            "implementation_signature": False,
            "verification_signature": False,
        }
        body["digest"] = _digest(body)
        return body
