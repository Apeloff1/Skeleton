"""Strict environment-backed policy for transparency witnesses.

Witness independence, signing keys and quorum policy are configured out of band.
Callers cannot self-assign trust. Empty configuration is allowed for development and
is reported as provisional rather than silently pretending witness finality exists.
"""
from __future__ import annotations

from dataclasses import dataclass
import base64
import json
import os

from core.transparency_witness import TrustedWitness


@dataclass(frozen=True, slots=True)
class WitnessPolicyConfig:
    # Preserve the original positional contract.
    witnesses: tuple[TrustedWitness, ...]
    required_groups: int
    finality_required: bool = False
    max_age_seconds: int = 3600
    signed_finality_required: bool = False


def _bool(value: str | None, default: bool = False) -> bool:
    if value is None: return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _validate_public_key(value: str) -> str:
    value = str(value or "").strip()
    if not value: return ""
    try: raw = base64.b64decode(value, validate=True)
    except Exception as exc: raise ValueError("witness public_key_b64 must be valid base64") from exc
    if len(raw) != 32: raise ValueError("Ed25519 witness public key must decode to 32 bytes")
    return value


def load_witness_policy(*, raw_json: str | None = None, required_groups: int | None = None,
                        max_age_seconds: int | None = None,
                        finality_required: bool | None = None,
                        signed_finality_required: bool | None = None) -> WitnessPolicyConfig:
    raw = raw_json if raw_json is not None else os.environ.get("TRANSPARENCY_TRUSTED_WITNESSES_JSON", "[]")
    try: parsed = json.loads(raw or "[]")
    except json.JSONDecodeError as exc: raise ValueError("TRANSPARENCY_TRUSTED_WITNESSES_JSON must be valid JSON") from exc
    if not isinstance(parsed, list): raise ValueError("trusted witness configuration must be a JSON array")
    if len(parsed) > 64: raise ValueError("at most 64 trusted witnesses are supported")
    witnesses: list[TrustedWitness] = []; ids: set[str] = set()
    for row in parsed:
        if not isinstance(row, dict): raise ValueError("each trusted witness must be an object")
        witness_id = str(row.get("id") or "").strip(); group = str(row.get("independence_group") or "").strip()
        if not witness_id or not group: raise ValueError("trusted witness id and independence_group are required")
        if witness_id in ids: raise ValueError(f"duplicate trusted witness id: {witness_id}")
        ids.add(witness_id)
        witnesses.append(TrustedWitness(
            witness_id, group, bool(row.get("enabled", True)), _validate_public_key(str(row.get("public_key_b64") or "")),
        ))
    configured_groups = len({w.independence_group for w in witnesses if w.enabled})
    signed_groups = len({w.independence_group for w in witnesses if w.enabled and w.public_key_b64})
    if required_groups is None: required_groups = int(os.environ.get("TRANSPARENCY_WITNESS_QUORUM", "3"))
    required_groups = int(required_groups)
    if required_groups < 1 or required_groups > 64: raise ValueError("TRANSPARENCY_WITNESS_QUORUM must be between 1 and 64")
    if max_age_seconds is None: max_age_seconds = int(os.environ.get("TRANSPARENCY_WITNESS_MAX_AGE_SECONDS", "3600"))
    max_age_seconds = int(max_age_seconds)
    if max_age_seconds < 1 or max_age_seconds > 604800:
        raise ValueError("TRANSPARENCY_WITNESS_MAX_AGE_SECONDS must be between 1 and 604800")
    required = _bool(os.environ.get("TRANSPARENCY_FINALITY_REQUIRED"), False) if finality_required is None else bool(finality_required)
    signed_required = _bool(os.environ.get("TRANSPARENCY_SIGNED_FINALITY_REQUIRED"), False) if signed_finality_required is None else bool(signed_finality_required)
    if required and configured_groups < required_groups:
        raise ValueError("finality is required but configured independent witness groups cannot satisfy quorum")
    if signed_required and signed_groups < required_groups:
        raise ValueError("signed finality is required but pinned Ed25519 witness groups cannot satisfy quorum")
    return WitnessPolicyConfig(tuple(witnesses), required_groups, required, max_age_seconds, signed_required)
