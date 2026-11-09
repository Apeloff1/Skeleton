"""Durable operator steering for the canonical GameForge cockpit.

Only declared creator inputs persist. Runtime ledgers, inference traces and
credentials are deliberately not serialized into operator state.
"""
from __future__ import annotations

import json
import math
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

from skeleton.context.cockpit import Cockpit
from skeleton.context.tensor import AXES, ContextTensor

SCHEMA = "skeleton.context.operator_steering.v1"
MAX_BYTES = 65536


def state_path() -> Path:
    override = os.environ.get("SKELETON_COCKPIT_STATE")
    return Path(override).expanduser() if override else Path.home() / ".skeleton" / "cockpit.json"


def _validate(raw: Any) -> Dict[str, Any]:
    if not isinstance(raw, dict) or raw.get("schema") != SCHEMA:
        raise ValueError("invalid cockpit steering schema")
    if set(raw) != {"schema", "tensor", "blend", "generation", "archetype", "era_bound"}:
        raise ValueError("unknown or missing cockpit steering fields")
    tensor = raw["tensor"]
    if not isinstance(tensor, dict) or set(tensor) != {"era", "axes"}:
        raise ValueError("invalid cockpit tensor")
    if not isinstance(tensor["era"], str) or not (1 <= len(tensor["era"]) <= 128):
        raise ValueError("invalid cockpit era")
    axes = tensor["axes"]
    if not isinstance(axes, dict) or set(axes) != set(AXES):
        raise ValueError("invalid cockpit axes")
    if any(type(v) not in (float, int) or not math.isfinite(v) or not 0 <= v <= 1 for v in axes.values()):
        raise ValueError("cockpit axes must be finite values between 0 and 1")
    blend = raw["blend"]
    if blend is not None:
        if (not isinstance(blend, list) or len(blend) != 3
                or any(not isinstance(v, str) or not v or len(v) > 128 for v in blend[:2])
                or type(blend[2]) not in (int, float) or not math.isfinite(blend[2])
                or not 0 <= blend[2] <= 1):
            raise ValueError("invalid cockpit era blend")
    for name in ("generation", "archetype"):
        value = raw[name]
        if value is not None and (not isinstance(value, str) or not (1 <= len(value) <= 128)):
            raise ValueError(f"invalid cockpit {name}")
    if type(raw["era_bound"]) is not bool:
        raise ValueError("invalid cockpit era binding")
    return raw


def capture_steering(cockpit: Cockpit, *, era_bound: bool = False) -> Dict[str, Any]:
    state = {
        "schema": SCHEMA,
        "tensor": {"era": cockpit.tensor.era, "axes": cockpit.tensor.as_dict()},
        "blend": list(cockpit.blend) if cockpit.blend else None,
        "generation": cockpit.generation,
        "archetype": cockpit.archetype,
        "era_bound": bool(era_bound),
    }
    return _validate(state)


def read_steering(path: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    location = Path(path) if path is not None else state_path()
    try:
        with location.open("rb") as stream:
            raw = stream.read(MAX_BYTES + 1)
    except FileNotFoundError:
        return None
    if len(raw) > MAX_BYTES:
        raise ValueError("cockpit steering file exceeds size limit")
    try:
        parsed = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid cockpit steering JSON: {exc}") from exc
    return _validate(parsed)


def restore_cockpit(state: Mapping[str, Any]) -> Cockpit:
    data = _validate(dict(state))
    cockpit = Cockpit()
    cockpit.tensor = ContextTensor.from_mapping(
        data["tensor"]["axes"], era=data["tensor"]["era"]
    )
    cockpit.blend = tuple(data["blend"]) if data["blend"] is not None else None
    cockpit.generation = data["generation"]
    cockpit.archetype = data["archetype"]
    return cockpit


def write_steering(state: Mapping[str, Any], path: Optional[Path] = None) -> Path:
    data = _validate(dict(state))
    location = Path(path) if path is not None else state_path()
    location.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    encoded = (json.dumps(data, indent=2, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")
    if len(encoded) > MAX_BYTES:
        raise ValueError("cockpit steering file exceeds size limit")
    temp_name = None
    try:
        fd, temp_name = tempfile.mkstemp(prefix=".cockpit-", dir=str(location.parent))
        with os.fdopen(fd, "wb") as stream:
            os.fchmod(stream.fileno(), 0o600) if hasattr(os, "fchmod") else None
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_name, location)
    finally:
        if temp_name and os.path.exists(temp_name):
            os.unlink(temp_name)
    return location
