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


def load_policy(*, root: Optional[Path] = None) -> Dict[str, Any]:
    path = policy_path(root)
    if not path.exists():
        return default_policy()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default_policy()
    base = default_policy()
    for key, value in base.items():
        if isinstance(value, dict):
            value.update(dict(data.get(key) or {}))
        else:
            base[key] = data.get(key, value)
    return base


def save_policy(policy: Dict[str, Any], *, root: Optional[Path] = None) -> Dict[str, Any]:
    path = policy_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(policy, indent=2, sort_keys=True), encoding="utf-8")
    return {"path": str(path), "saved": 1}


def set_threshold(surface: str, value: float, *, root: Optional[Path] = None) -> Dict[str, Any]:
    policy = load_policy(root=root)
    policy.setdefault("quality_thresholds", {})[surface] = float(value)
    save_policy(policy, root=root)
    return policy


def set_repair_enabled(surface: str, enabled: bool, *, root: Optional[Path] = None) -> Dict[str, Any]:
    policy = load_policy(root=root)
    policy.setdefault("repair_enabled", {})[surface] = bool(enabled)
    save_policy(policy, root=root)
    return policy


def set_repair_class(name: str, enabled: bool, *, root: Optional[Path] = None) -> Dict[str, Any]:
    policy = load_policy(root=root)
    policy.setdefault("repair_classes", {})[name] = bool(enabled)
    save_policy(policy, root=root)
    return policy
