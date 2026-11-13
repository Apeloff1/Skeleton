"""Strict byte transport for canonical offline scene save envelopes.

Transport is untrusted: bound bytes before parsing, reject duplicate JSON keys,
and delegate semantic replay and checksum validation to the canonical engine.
No filesystem or network I/O occurs in this module.
"""
from __future__ import annotations

import json
import math
from typing import Any

from skeleton.game.gameplay.offline_portable import (
    MAX_PORTABLE_BYTES, PortableGameError,
)
from skeleton.game.gameplay.scene_portable import (
    export_scene_bundle, import_scene_bundle,
)


def _unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise PortableGameError("duplicate portable gameplay JSON key")
        result[key] = value
    return result



def _finite_json_float(token: str) -> float:
    """Reject exponent overflow before untrusted replay-schema decoding."""
    try:
        number = float(token)
    except (OverflowError, ValueError) as exc:
        raise PortableGameError("nonfinite portable gameplay number") from exc
    if not math.isfinite(number):
        raise PortableGameError("nonfinite portable gameplay number")
    return number


def encode_scene_bytes(session: Any) -> bytes:
    """Export a replay-verified session as deterministic bounded UTF-8 JSON."""
    envelope = export_scene_bundle(session)
    try:
        payload = json.dumps(
            envelope, sort_keys=True, separators=(",", ":"),
            ensure_ascii=False, allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise PortableGameError("invalid portable gameplay encoding") from exc
    if len(payload) > MAX_PORTABLE_BYTES:
        raise PortableGameError("portable gameplay size budget exceeded")
    return payload


def decode_scene_bytes(payload: bytes) -> dict[str, Any]:
    """Decode only strict UTF-8, unique-key JSON with canonical replay proof."""
    if type(payload) is not bytes:
        raise PortableGameError("portable gameplay requires bytes")
    if len(payload) > MAX_PORTABLE_BYTES:
        raise PortableGameError("portable gameplay size budget exceeded")
    try:
        text = payload.decode("utf-8", errors="strict")
        value = json.loads(
            text, object_pairs_hook=_unique_pairs,
            parse_float=_finite_json_float,
            parse_constant=lambda _: (_ for _ in ()).throw(
                PortableGameError("nonfinite portable gameplay number")
            ),
        )
    except PortableGameError:
        # Preserve fail-closed parser diagnostics from duplicate-key, NaN and
        # overflow admission instead of masking them as generic JSON failure.
        raise
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise PortableGameError("invalid portable gameplay JSON bytes") from exc
    return import_scene_bundle(value)
