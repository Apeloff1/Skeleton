"""Independent policy for externally witnessed deployment checkpoint publications.

Deployment checkpoint witness policy is intentionally separate from epistemic
transparency finality. Operators may use the same witness identities, but deployment
release approval must not silently inherit or mutate epistemic policy.
"""
from __future__ import annotations

from dataclasses import dataclass
import os

from core.transparency_witness import TrustedWitness
from core.transparency_witness_config import load_witness_policy


@dataclass(frozen=True, slots=True)
class DeploymentCheckpointPinPolicy:
    witnesses: tuple[TrustedWitness, ...]
    required_groups: int
    max_age_seconds: int
    required: bool
    continuity_required: bool = False


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    if raw not in {"0", "1", "false", "true", "no", "yes", "off", "on"}:
        raise ValueError(f"{name} must be a canonical boolean string")
    return raw in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int, *, minimum: int, maximum: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    if not raw or raw != raw.strip() or not raw.isascii() or not raw.isdigit():
        raise ValueError(f"{name} must be a canonical positive integer")
    value = int(raw)
    if str(value) != raw:
        raise ValueError(f"{name} must not contain leading zeros")
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return value


def load_deployment_checkpoint_pin_policy(
    *,
    raw_json: str | None = None,
    required_groups: int | None = None,
    max_age_seconds: int | None = None,
    required: bool | None = None,
    continuity_required: bool | None = None,
) -> DeploymentCheckpointPinPolicy:
    raw = (
        raw_json
        if raw_json is not None
        else os.environ.get("DEPLOYMENT_CHECKPOINT_TRUSTED_WITNESSES_JSON", "[]")
    )
    if not isinstance(raw, str):
        raise ValueError("deployment checkpoint witness configuration must be JSON text")
    if required_groups is None:
        required_groups = _env_int(
            "DEPLOYMENT_CHECKPOINT_WITNESS_QUORUM", 3, minimum=1, maximum=64,
        )
    elif type(required_groups) is not int or not 1 <= required_groups <= 64:
        raise ValueError("deployment checkpoint witness quorum must be an integer between 1 and 64")
    if max_age_seconds is None:
        max_age_seconds = _env_int(
            "DEPLOYMENT_CHECKPOINT_WITNESS_MAX_AGE_SECONDS", 3600,
            minimum=1, maximum=604800,
        )
    elif type(max_age_seconds) is not int or not 1 <= max_age_seconds <= 604800:
        raise ValueError("deployment checkpoint witness max age must be an integer between 1 and 604800")

    required_explicit = required is not None
    if required is None:
        required = _env_bool("DEPLOYMENT_CHECKPOINT_SIGNED_PINS_REQUIRED", False)
    elif type(required) is not bool:
        raise ValueError("deployment checkpoint signed pin requirement must be boolean")

    if continuity_required is None:
        continuity_required = _env_bool("DEPLOYMENT_CHECKPOINT_CONTINUITY_REQUIRED", False)
    elif type(continuity_required) is not bool:
        raise ValueError("deployment checkpoint continuity requirement must be boolean")
    if continuity_required and required_explicit and required is False:
        raise ValueError("deployment checkpoint continuity requires signed pins")
    if continuity_required:
        required = True

    # Reuse the strict witness schema/key validation, but keep finality semantics local
    # to this policy. Any required witness mode proves configured signed groups can meet
    # the requested deployment quorum.
    parsed = load_witness_policy(
        raw_json=raw,
        required_groups=required_groups,
        max_age_seconds=max_age_seconds,
        finality_required=False,
        signed_finality_required=required,
    )
    return DeploymentCheckpointPinPolicy(
        witnesses=parsed.witnesses,
        required_groups=required_groups,
        max_age_seconds=max_age_seconds,
        required=required,
        continuity_required=continuity_required,
    )
