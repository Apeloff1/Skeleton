"""Fail-closed admit for wave-4 volume organs."""
from __future__ import annotations

import hashlib
import json
from typing import Any

from .catalog import BIND, contract

_SHA = __import__("re").compile(r"^[0-9a-f]{64}$")


class VolumeReject(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def volume_ids() -> tuple[str, ...]:
    return tuple(sorted(BIND))


def reject_reason(volume_id: str, card: dict[str, Any]) -> str | None:
    try:
        admit(volume_id, card)
    except VolumeReject as exc:
        return exc.reason
    return None


def admit(volume_id: str, card: dict[str, Any]) -> dict[str, Any]:
    if volume_id not in BIND:
        raise VolumeReject("unknown volume")
    if not isinstance(card, dict):
        raise VolumeReject("card must be object")
    spec = contract(volume_id)
    if card.get("volume") != volume_id:
        raise VolumeReject("cross-volume card")
    missing = [field for field in spec["required"] if card.get(field) in (None, "", [], {})]
    if missing:
        raise VolumeReject("missing:" + ",".join(missing))
    items = card.get("items")
    if items is not None:
        if not isinstance(items, list):
            raise VolumeReject("items must be list")
        if len(items) > spec["max_items"]:
            raise VolumeReject("bound exceeded")
    family = spec["family"]
    _family_gate(family, card)
    body = {k: card[k] for k in ("volume", *spec["required"])}
    digest = hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    if card.get("receipt_digest") not in (None, digest):
        raise VolumeReject("digest mismatch")
    return {"volume": volume_id, "family": family, "digest": digest, "admitted": True, "stored_prose": 0}


def _family_gate(family: str, card: dict[str, Any]) -> None:
    if family == "jvm":
        if card.get("signed") is not True:
            raise VolumeReject("unsigned bytecode")
        if not _SHA.fullmatch(str(card.get("bytecode_sha256"))):
            raise VolumeReject("bytecode digest")
    elif family == "import" and card.get("cycle_free") is not True:
        raise VolumeReject("import cycle")
    elif family == "security" and card.get("decision") != "deny":
        if card.get("allow_reason") in (None, ""):
            raise VolumeReject("deny by default")
    elif family == "privacy" and card.get("erasure_proof") is not True:
        raise VolumeReject("erasure proof required")
    elif family == "slo":
        if not isinstance(card.get("objective"), (int, float)) or card["objective"] <= 0:
            raise VolumeReject("objective bound")
        if not isinstance(card.get("burn"), (int, float)) or card["burn"] > card["objective"]:
            raise VolumeReject("burn exceeds objective")
    elif family == "obs":
        if not isinstance(card.get("cardinality"), int) or card["cardinality"] < 0:
            raise VolumeReject("cardinality")
        if card["cardinality"] > int(card.get("budget") or 0):
            raise VolumeReject("cardinality budget")
    elif family == "cost":
        if not isinstance(card.get("units"), (int, float)) or card["units"] < 0 or card["units"] > card.get("cap", -1):
            raise VolumeReject("cost cap")
    elif family == "research" and card.get("contaminated") is not False:
        raise VolumeReject("contamination")
    elif family == "eval" and not isinstance(card.get("score"), (int, float)):
        raise VolumeReject("score")
    elif family == "nfr" and not isinstance(card.get("bound"), (int, float)):
        raise VolumeReject("nfr bound")
    elif family == "taxonomy" and not isinstance(card.get("maturity"), int):
        raise VolumeReject("maturity")
    elif family == "outbox" and not isinstance(card.get("idempotency_key"), str):
        raise VolumeReject("idempotency")
    elif family == "workflow" and not isinstance(card.get("steps"), list):
        raise VolumeReject("steps")
    elif family == "workflow" and len(card.get("steps") or []) == 0:
        raise VolumeReject("empty workflow")
    elif family == "artifact" and not _SHA.fullmatch(str(card.get("digest") or "")) and card.get("digest") not in (None,):
        raise VolumeReject("artifact digest")
    elif family == "gpu" and (not isinstance(card.get("bytes"), int) or card["bytes"] < 0):
        raise VolumeReject("gpu bytes")
    elif family == "cache" and card.get("bound") is not True:
        raise VolumeReject("cache unbound")
    elif family == "farm" and not isinstance(card.get("quota"), int):
        raise VolumeReject("quota")
    elif family == "rights" and card.get("allowed") is not True:
        raise VolumeReject("rights denied")
    elif family == "lifecycle" and card.get("deprecated") is True and card.get("stage") == "serve":
        raise VolumeReject("deprecated serve")
    elif family == "sandbox" and card.get("isolated") is not True:
        raise VolumeReject("sandbox escape")
    elif family == "state" and card.get("terminal") not in (True, False):
        raise VolumeReject("terminal flag")
    elif family == "human" and card.get("approval") not in ("granted", "denied", "expired"):
        raise VolumeReject("approval")
    elif family == "claim" and not isinstance(card.get("expires"), str):
        raise VolumeReject("expiry")
    elif family == "data" and card.get("fresh") is not True:
        raise VolumeReject("stale")
    elif family == "plan" and card.get("static_ok") is not True:
        raise VolumeReject("static analysis")
    elif family == "tool" and card.get("health") not in ("ok", "degraded", "down"):
        raise VolumeReject("tool health")
    elif family == "saga" and not isinstance(card.get("compensation"), str):
        raise VolumeReject("compensation")
    elif family == "change" and card.get("risk") not in ("low", "medium", "high"):
        raise VolumeReject("risk")
    elif family == "schedule" and card.get("critical") not in (True, False):
        raise VolumeReject("critical path")
