"""Portable deterministic expedition bundle with bounded integrity validation.

This is an offline export/import container, not a cryptographic signature.
The caller must separately authorize and verify the author/source origin.
"""
from __future__ import annotations

import json
from typing import Any

from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.turn_combat import (
    CombatSessionError, MAX_CLI_BYTES, _object,
)
from skeleton.game.gameplay.arena_expedition import verify_expedition

SCHEMA = "skeleton.expedition_bundle.v1"
MAX_BUNDLE_BYTES = MAX_CLI_BYTES


def _size(payload: Any) -> int:
    try:
        encoded = json.dumps(
            payload, sort_keys=True, separators=(",", ":"),
            allow_nan=False, ensure_ascii=False,
        ).encode("utf-8")
    except (TypeError, ValueError, RecursionError, UnicodeError) as exc:
        raise CombatSessionError("invalid expedition bundle JSON") from exc
    if len(encoded) > MAX_BUNDLE_BYTES:
        raise CombatSessionError("expedition bundle exceeds portable size budget")
    return len(encoded)


def export_bundle(payload: Any) -> dict[str, Any]:
    session = verify_expedition(payload)
    record = {
        "schema_version": SCHEMA,
        "kind": "offline_expedition",
        "source_digest": session["source_digest"],
        "state_digest": session["state_digest"],
        "session": session,
    }
    record["checksum"] = dig(record)
    _size(record)
    return record


def import_bundle(payload: Any) -> dict[str, Any]:
    _size(payload)
    obj = _object(payload, {
        "schema_version", "kind", "source_digest",
        "state_digest", "session", "checksum",
    }, "expedition bundle")
    if obj["schema_version"] != SCHEMA or obj["kind"] != "offline_expedition":
        raise CombatSessionError("unsupported expedition bundle format")
    checksum = obj["checksum"]
    if type(checksum) is not str or len(checksum) != 64:
        raise CombatSessionError("invalid expedition bundle checksum")
    if dig({k: v for k, v in obj.items() if k != "checksum"}) != checksum:
        raise CombatSessionError("expedition bundle checksum mismatch")
    session = verify_expedition(obj["session"])
    if (
        session["source_digest"] != obj["source_digest"]
        or session["state_digest"] != obj["state_digest"]
    ):
        raise CombatSessionError("expedition bundle source/state mismatch")
    return session
