"""Operator policy state for thresholds and repair toggles."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

from skeleton.organism.paths import organism_dir


def policy_path(root: Optional[Path] = None) -> Path:
    return organism_dir(root) / "policy.json"


def default_policy() -> Dict[str, Any]:
    return {
        "quality_thresholds": {
            "forge": 0.7,
            "plan": 0.7,
            "game_logic": 0.7,
            "npc": 0.7,
            "dialogue": 0.7,
        },
        "repair_enabled": {
            "forge": True,
            "plan": True,
            "game_logic": True,
            "npc": True,
            "dialogue": True,
        },
        "repair_classes": {
            "script_patch": True,
            "project_closure": True,
            "scene_stub": True,
            "plan_fill": True,
            "pipeline_seed": True,
        },
    }



def _validate(policy: Dict[str, Any]) -> None:
    for surface, value in policy["quality_thresholds"].items():
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 < float(value) <= 1 or float(value) != float(value):
            raise ValueError(f"threshold for {surface} must be in (0, 1]")
    for name, table in (("repair_enabled", policy["repair_enabled"]), ("repair_classes", policy["repair_classes"])):
        for key, value in table.items():
            if not isinstance(value, bool):
                raise ValueError(f"{name} {key} must be boolean")


def load_policy(*, root: Optional[Path] = None) -> Dict[str, Any]:
    path = policy_path(root)
    if not path.exists():
        return default_policy()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError("policy is not JSON") from exc
    if not isinstance(data, dict):
        raise ValueError("policy must be an object")
    base = default_policy()
    for key, value in base.items():
        incoming = data.get(key, {})
        if not isinstance(incoming, dict):
            raise ValueError(f"{key} must be an object")
        value.update(incoming)
    _validate(base)
    return base


def save_policy(policy: Dict[str, Any], *, root: Optional[Path] = None) -> Dict[str, Any]:
    path = policy_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(policy, indent=2, sort_keys=True), encoding="utf-8")
    return {"path": str(path), "saved": 1}


def set_threshold(surface: str, value: float, *, root: Optional[Path] = None) -> Dict[str, Any]:
    policy = load_policy(root=root)
    if not isinstance(surface, str) or not surface.strip():
        raise ValueError("surface is required")
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 < float(value) <= 1 or float(value) != float(value):
        raise ValueError("threshold must be in (0, 1]")
    policy.setdefault("quality_thresholds", {})[surface] = float(value)
    save_policy(policy, root=root)
    return policy


def set_repair_enabled(surface: str, enabled: bool, *, root: Optional[Path] = None) -> Dict[str, Any]:
    policy = load_policy(root=root)
    if not isinstance(enabled, bool):
        raise ValueError("enabled must be boolean")
    policy.setdefault("repair_enabled", {})[surface] = enabled
    save_policy(policy, root=root)
    return policy


def set_repair_class(name: str, enabled: bool, *, root: Optional[Path] = None) -> Dict[str, Any]:
    policy = load_policy(root=root)
    if not isinstance(enabled, bool):
        raise ValueError("enabled must be boolean")
    policy.setdefault("repair_classes", {})[name] = enabled
    save_policy(policy, root=root)
    return policy
