"""Merge a model proposal into the compiled spec; the compiler keeps authority."""
from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

from .plan_schema import FIELD_LIMITS, MUTABLE_FIELDS
from skeleton.forge.game_design_spec import GameplayValidationError, gameplay_constraints, validate_gameplay


def _seal(body: Mapping[str, Any]) -> dict[str, Any]:
    # Same sealing as compile_brief: sha256 over the canonical body sans spec_id.
    sealed = {k: v for k, v in body.items() if k != "spec_id"}
    encoded = json.dumps(sealed, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    sealed["spec_id"] = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    return sealed


def guard_proposal(compiled: Mapping[str, Any], proposal: Mapping[str, Any]) -> tuple[dict[str, Any], tuple[str, ...]]:
    """Return ``(spec, violations)``.

    Only :data:`MUTABLE_FIELDS` are taken; text is bounded; ``systems`` may only
    reorder or drop the compiler's systems (never invent one, never empty).
    Any other key is a violation and is ignored.
    """
    spec = dict(compiled)
    violations: list[str] = []
    for key in proposal:
        if key not in MUTABLE_FIELDS:
            violations.append(f"locked:{key}")
    for key, limit in FIELD_LIMITS.items():
        if key not in proposal:
            continue
        value = proposal[key]
        if not isinstance(value, str) or not value.strip():
            violations.append(f"invalid:{key}")
        elif len(value.strip()) > limit:
            violations.append(f"too_long:{key}")
        else:
            spec[key] = " ".join(value.split())
    if "systems" in proposal:
        systems = proposal["systems"]
        known = list(compiled.get("systems") or [])
        if not isinstance(systems, list) or not systems or not all(isinstance(s, str) for s in systems):
            violations.append("invalid:systems")
        elif any(s not in known for s in systems) or len(set(systems)) != len(systems):
            violations.append("unknown:systems")
        else:
            spec["systems"] = list(systems)
    if "gameplay" in proposal:
        try:
            gameplay = validate_gameplay(
                proposal["gameplay"], genre=str(compiled.get("genre") or "top_down_shooter"),
            )
            locked = gameplay_constraints(str(compiled.get("brief") or ""))
            conflicts = tuple("constraints:gameplay." + key for key, value in locked.items()
                              if gameplay[key] != value)
            if conflicts:
                violations.extend(conflicts)
            else:
                spec["gameplay"] = gameplay
        except GameplayValidationError as exc:
            violations.extend(exc.violations)
    return _seal(spec), tuple(violations)
