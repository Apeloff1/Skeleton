"""Seal campus + labyrinth cards. Digest only. No secrets."""
from __future__ import annotations
import hashlib, json
from typing import Any

class SealError(ValueError):
    pass

def dumps(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)

def digest(payload: dict[str, Any]) -> str:
    return hashlib.sha256(dumps({k: v for k, v in payload.items() if k != "digest"}).encode("utf-8")).hexdigest()

def seal(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise SealError("card")
    body = dict(payload)
    body["stored_prose"] = 0
    body["sota_ready"] = False
    body["digest"] = digest(body)
    body["ok"] = True
    return body
