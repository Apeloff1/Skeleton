"""Strict environment-backed policy for transparency witnesses.

Witness independence, signing keys and quorum policy are configured out of band.
Trust policy is exact-type and canonical: duplicate JSON keys, unknown fields,
whitespace-normalized identities, string booleans inside JSON, bool-as-int arguments,
and malformed numeric environment values are rejected instead of coerced.
"""
from __future__ import annotations

from dataclasses import dataclass
import base64
import json
import os
from typing import Any

from core.transparency_witness import TrustedWitness

_WITNESS_KEYS = {"id", "independence_group", "enabled", "public_key_b64"}


@dataclass(frozen=True, slots=True)
class WitnessPolicyConfig:
    # Preserve the original positional contract.
    witnesses: tuple[TrustedWitness, ...]
    required_groups: int
    finality_required: bool = False
    max_age_seconds: int = 3600
    signed_finality_required: bool = False


def _strict_json_loads(text: str) -> Any:
    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key}")
            result[key] = value
        return result

    return json.loads(text, object_pairs_hook=reject_duplicates)


def _canonical_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"{field} must be canonical non-empty text")
    return value


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    if value not in {"0", "1", "false", "true", "no", "yes", "off", "on"}:
        raise ValueError(f"{name} must be a canonical boolean string")
    return value in {"1", "true", "yes", "on"}


def _exact_bool(value: Any, field: str) -> bool:
    if type(value) is not bool:
        raise ValueError(f"{field} must be boolean")
    return value


def _parse_env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    if not raw or raw != raw.strip() or not raw.isascii() or not raw.isdigit():
        raise ValueError(f"{name} must be a canonical positive integer")
    value = int(raw)
    if str(value) != raw:
        raise ValueError(f"{name} must not contain leading zeros")
    return value


def _exact_int(value: Any, field: str) -> int:
    if type(value) is not int:
        raise ValueError(f"{field} must be an integer")
    return value


def _validate_public_key(value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError("witness public_key_b64 must be a string")
    if not value:
        return ""
    if value != value.strip():
        raise ValueError("witness public_key_b64 must be canonical base64 text")
    try:
        raw = base64.b64decode(value, validate=True)
    except Exception as exc:
        raise ValueError("witness public_key_b64 must be valid base64") from exc
    if len(raw) != 32:
        raise ValueError("Ed25519 witness public key must decode to 32 bytes")
    if base64.b64encode(raw).decode("ascii") != value:
        raise ValueError("witness public_key_b64 must use canonical base64 encoding")
    return value


def load_witness_policy(
    *,
    raw_json: str | None = None,
    required_groups: int | None = None,
    max_age_seconds: int | None = None,
    finality_required: bool | None = None,
    signed_finality_required: bool | None = None,
) -> WitnessPolicyConfig:
    raw = raw_json if raw_json is not None else os.environ.get("TRANSPARENCY_TRUSTED_WITNESSES_JSON", "[]")
    if not isinstance(raw, str):
        raise ValueError("trusted witness configuration must be JSON text")
    try:
        parsed = _strict_json_loads(raw)
    except (json.JSONDecodeError, ValueError) as exc:
        raise ValueError("TRANSPARENCY_TRUSTED_WITNESSES_JSON must be strict valid JSON") from exc
    if not isinstance(parsed, list):
        raise ValueError("trusted witness configuration must be a JSON array")
    if len(parsed) > 64:
        raise ValueError("at most 64 trusted witnesses are supported")

    witnesses: list[TrustedWitness] = []
    ids: set[str] = set()
    for row in parsed:
        if not isinstance(row, dict):
            raise ValueError("each trusted witness must be an object")
        if not {"id", "independence_group"}.issubset(row) or not set(row).issubset(_WITNESS_KEYS):
            raise ValueError("trusted witness schema mismatch")
        witness_id = _canonical_text(row["id"], "trusted witness id")
        group = _canonical_text(row["independence_group"], "trusted witness independence_group")
        if witness_id in ids:
            raise ValueError(f"duplicate trusted witness id: {witness_id}")
        ids.add(witness_id)
        enabled = _exact_bool(row.get("enabled", True), "trusted witness enabled")
        public_key = _validate_public_key(row.get("public_key_b64", ""))
        witnesses.append(TrustedWitness(witness_id, group, enabled, public_key))

    configured_groups = len({w.independence_group for w in witnesses if w.enabled})
    signed_groups = len({w.independence_group for w in witnesses if w.enabled and w.public_key_b64})

    if required_groups is None:
        required_groups = _parse_env_int("TRANSPARENCY_WITNESS_QUORUM", 3)
    else:
        required_groups = _exact_int(required_groups, "required_groups")
    if not 1 <= required_groups <= 64:
        raise ValueError("TRANSPARENCY_WITNESS_QUORUM must be between 1 and 64")

    if max_age_seconds is None:
        max_age_seconds = _parse_env_int("TRANSPARENCY_WITNESS_MAX_AGE_SECONDS", 3600)
    else:
        max_age_seconds = _exact_int(max_age_seconds, "max_age_seconds")
    if not 1 <= max_age_seconds <= 604800:
        raise ValueError("TRANSPARENCY_WITNESS_MAX_AGE_SECONDS must be between 1 and 604800")

    required = (
        _env_bool("TRANSPARENCY_FINALITY_REQUIRED", False)
        if finality_required is None
        else _exact_bool(finality_required, "finality_required")
    )
    signed_required = (
        _env_bool("TRANSPARENCY_SIGNED_FINALITY_REQUIRED", False)
        if signed_finality_required is None
        else _exact_bool(signed_finality_required, "signed_finality_required")
    )

    if required and configured_groups < required_groups:
        raise ValueError("finality is required but configured independent witness groups cannot satisfy quorum")
    if signed_required and signed_groups < required_groups:
        raise ValueError("signed finality is required but pinned Ed25519 witness groups cannot satisfy quorum")
    return WitnessPolicyConfig(tuple(witnesses), required_groups, required, max_age_seconds, signed_required)
