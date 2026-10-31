"""Reusable bounded, checksum-bound offline gameplay envelope.

This module validates structural integrity only; a digest is not a signature,
license attestation or proof that an untrusted author is authorized.
Consumers supply their canonical replay verifier, never dynamic code.
"""
from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from skeleton.game.gameplay.flgb_gameplay_runtime import dig

SCHEMA = "skeleton.gameplay_portable.v1"
MAX_PORTABLE_BYTES = 2 * 1024 * 1024


class PortableGameError(ValueError):
    """Malformed, oversized, tampered or incompatible offline gameplay data."""


def _canonical_size(value: Any) -> int:
    try:
        encoded = json.dumps(
            value, sort_keys=True, separators=(",", ":"),
            ensure_ascii=False, allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, RecursionError, UnicodeError) as exc:
        raise PortableGameError("invalid portable gameplay JSON") from exc
    if len(encoded) > MAX_PORTABLE_BYTES:
        raise PortableGameError("portable gameplay size budget exceeded")
    return len(encoded)


def _verified(value: Any, verifier: Callable[[Any], dict[str, Any]]) -> dict[str, Any]:
    _canonical_size(value)
    try:
        result = verifier(value)
    except (KeyError, ValueError, TypeError, RecursionError) as exc:
        raise PortableGameError("portable gameplay replay verification failed") from exc
    if type(result) is not dict:
        raise PortableGameError("portable gameplay verifier returned invalid state")
    for field in ("source_digest", "state_digest"):
        digest = result.get(field)
        if type(digest) is not str or len(digest) != 64:
            raise PortableGameError("portable gameplay missing source/state digest")
        if any(char not in "0123456789abcdef" for char in digest):
            raise PortableGameError("portable gameplay digest is malformed")
    return result


def export_verified(
    value: Any, *, kind: str,
    verifier: Callable[[Any], dict[str, Any]],
) -> dict[str, Any]:
    if type(kind) is not str or not kind or len(kind) > 64:
        raise PortableGameError("invalid portable gameplay kind")
    session = _verified(value, verifier)
    envelope = {
        "schema_version": SCHEMA, "kind": kind,
        "source_digest": session["source_digest"],
        "state_digest": session["state_digest"],
        "session": session,
    }
    envelope["checksum"] = dig(envelope)
    _canonical_size(envelope)
    return envelope


def import_verified(
    value: Any, *, kind: str,
    verifier: Callable[[Any], dict[str, Any]],
) -> dict[str, Any]:
    _canonical_size(value)
    if type(value) is not dict or set(value) != {
        "schema_version", "kind", "source_digest",
        "state_digest", "session", "checksum",
    }:
        raise PortableGameError("invalid portable gameplay envelope fields")
    if value["schema_version"] != SCHEMA or value["kind"] != kind:
        raise PortableGameError("incompatible portable gameplay format")
    checksum = value["checksum"]
    if type(checksum) is not str or len(checksum) != 64:
        raise PortableGameError("invalid portable gameplay checksum")
    if any(char not in "0123456789abcdef" for char in checksum):
        raise PortableGameError("invalid portable gameplay checksum")
    try:
        expected = dig({key: val for key, val in value.items() if key != "checksum"})
    except (TypeError, ValueError, RecursionError) as exc:
        raise PortableGameError("invalid portable gameplay checksum data") from exc
    if checksum != expected:
        raise PortableGameError("portable gameplay checksum mismatch")
    session = _verified(value["session"], verifier)
    if (
        value["source_digest"] != session["source_digest"]
        or value["state_digest"] != session["state_digest"]
    ):
        raise PortableGameError("portable gameplay source/state mismatch")
    return session
