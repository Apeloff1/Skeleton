"""Fail-closed envelopes for the four remaining planes. stored_prose stays 0."""
from __future__ import annotations

import hashlib
import json
from typing import Any

PLANES = ("engineering", "computer_science", "reverse_engineering", "security")
CS_STRATUM_1 = tuple(f"CS300-{i:03d}" for i in range(1, 9))


class DomainReject(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def admit(plane: str, card: dict[str, Any]) -> dict[str, Any]:
    if plane not in PLANES:
        raise DomainReject("unknown plane")
    if not isinstance(card, dict) or card.get("plane") != plane:
        raise DomainReject("identity mismatch")
    if card.get("stored_prose") not in (0, None):
        raise DomainReject("stored prose")
    if not isinstance(card.get("bound"), int) or not 1 <= card["bound"] <= 300:
        raise DomainReject("bound")
    if card.get("evidence") in (None, "", [], {}):
        raise DomainReject("missing evidence")
    _gate(plane, card)
    body = {"plane": plane, "bound": card["bound"], "evidence": card["evidence"]}
    digest = hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return {"plane": plane, "digest": digest, "admitted": True, "stored_prose": 0}


def _gate(plane: str, card: dict[str, Any]) -> None:
    if plane == "engineering":
        if card.get("map") != "p3-engineering-closed":
            raise DomainReject("engineering map")
        if card.get("self_promoting") is not False:
            raise DomainReject("self-promotion")
    elif plane == "computer_science":
        layers = card.get("layers")
        if not isinstance(layers, list) or set(layers) != set(CS_STRATUM_1):
            raise DomainReject("stratum")
        if card.get("boundary") in (None, ""):
            raise DomainReject("computability boundary")
    elif plane == "reverse_engineering":
        if card.get("provenance") in (None, ""):
            raise DomainReject("binary provenance")
        if card.get("unsigned") is not False:
            raise DomainReject("unsigned binary")
    elif plane == "security":
        if card.get("secret") not in (None, ""):
            raise DomainReject("secret leak")
        if card.get("may_self_close") is not False:
            raise DomainReject("security self-close")
