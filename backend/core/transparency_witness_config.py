"""Strict environment-backed policy for transparency witnesses.

The application never derives witness independence from caller input. Operators
configure trusted witness identities and groups out of band; service/API layers only
consume this validated policy. Empty configuration is allowed for development and is
reported as unfinalized rather than silently pretending quorum exists.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import os

from core.transparency_witness import TrustedWitness


@dataclass(frozen=True, slots=True)
class WitnessPolicyConfig:
    # Preserve the original positional contract: witnesses, required_groups,
    # finality_required. Freshness is appended as an optional policy dimension.
    witnesses: tuple[TrustedWitness, ...]
    required_groups: int
    finality_required: bool = False
    max_age_seconds: int = 3600


def _bool(value: str | None, default: bool = False) -> bool:
    if value is None: return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def load_witness_policy(*, raw_json: str | None = None, required_groups: int | None = None,
                        max_age_seconds: int | None = None,
                        finality_required: bool | None = None) -> WitnessPolicyConfig:
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
        ids.add(witness_id); witnesses.append(TrustedWitness(witness_id, group, bool(row.get("enabled", True))))
    configured_groups = len({w.independence_group for w in witnesses if w.enabled})
    if required_groups is None:
        required_groups = int(os.environ.get("TRANSPARENCY_WITNESS_QUORUM", "3"))
    required_groups = int(required_groups)
    if required_groups < 1 or required_groups > 64: raise ValueError("TRANSPARENCY_WITNESS_QUORUM must be between 1 and 64")
    if max_age_seconds is None:
        max_age_seconds = int(os.environ.get("TRANSPARENCY_WITNESS_MAX_AGE_SECONDS", "3600"))
    max_age_seconds = int(max_age_seconds)
    if max_age_seconds < 1 or max_age_seconds > 604800:
        raise ValueError("TRANSPARENCY_WITNESS_MAX_AGE_SECONDS must be between 1 and 604800")
    required = _bool(os.environ.get("TRANSPARENCY_FINALITY_REQUIRED"), False) if finality_required is None else bool(finality_required)
    if required and configured_groups < required_groups:
        raise ValueError("finality is required but configured independent witness groups cannot satisfy quorum")
    return WitnessPolicyConfig(tuple(witnesses), required_groups, required, max_age_seconds)
