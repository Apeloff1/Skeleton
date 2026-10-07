"""Cross-surface policy inheritance — surfaces can inherit thresholds
and toggles from parent surfaces or a global default.

This reduces duplication and makes policy management more maintainable.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from skeleton.organism.policy_state import load_policy, save_policy


# Default inheritance map: child -> parent
DEFAULT_INHERITANCE = {
    "forge": "global",
    "plan": "global",
    "game_logic": "global",
    "npc": "global",
    "dialogue": "global",
}


def _inheritance_path(root=None) -> Path:
    from skeleton.organism.paths import organism_dir
    return organism_dir(root) / "policy_inheritance.json"


def load_inheritance(root=None) -> Dict[str, str]:
    """Load the inheritance map. Returns child->parent mapping."""
    path = _inheritance_path(root)
    if not path.exists():
        return dict(DEFAULT_INHERITANCE)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
    except (json.JSONDecodeError, OSError):
        pass
    return dict(DEFAULT_INHERITANCE)


def save_inheritance(mapping: Dict[str, str], root=None) -> None:
    """Save the inheritance map."""
    path = _inheritance_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(mapping, indent=2, sort_keys=True), encoding="utf-8")


def set_parent(child: str, parent: str, *, root=None) -> Dict[str, Any]:
    """Set a parent for a surface. Use 'global' for the default policy."""
    mapping = load_inheritance(root)
    if parent != "global" and parent not in mapping and parent not in DEFAULT_INHERITANCE:
        # Check if parent is a known surface
        policy = load_policy(root=root)
        known = set((policy.get("quality_thresholds") or {}).keys())
        if parent not in known:
            return {
                "kind": "inheritance-error",
                "error": f"unknown parent surface: {parent}",
                "known": sorted(known | {"global"}),
                "stored_prose": 0,
            }
    mapping[child] = parent
    save_inheritance(mapping, root=root)
    return {
        "kind": "inheritance-set",
        "child": child,
        "parent": parent,
        "mapping": mapping,
        "stored_prose": 0,
    }


def resolve_threshold(surface: str, *, root=None, fallback: float = 0.7) -> float:
    """Resolve the effective threshold for a surface, following inheritance."""
    policy = load_policy(root=root)
    thresholds = policy.get("quality_thresholds", {})

    # Direct value
    if surface in thresholds:
        return float(thresholds[surface])

    # Follow inheritance chain
    mapping = load_inheritance(root)
    visited = set()
    current = surface
    while current in mapping and current not in visited:
        visited.add(current)
        parent = mapping[current]
        if parent in thresholds:
            return float(thresholds[parent])
        current = parent

    return fallback


def resolve_repair_enabled(surface: str, *, root=None, fallback: bool = True) -> bool:
    """Resolve the effective repair toggle for a surface, following inheritance."""
    policy = load_policy(root=root)
    enabled = policy.get("repair_enabled", {})

    if surface in enabled:
        return bool(enabled[surface])

    mapping = load_inheritance(root)
    visited = set()
    current = surface
    while current in mapping and current not in visited:
        visited.add(current)
        parent = mapping[current]
        if parent in enabled:
            return bool(enabled[parent])
        current = parent

    return fallback


def resolve_repair_class(name: str, *, root=None, fallback: bool = True) -> bool:
    """Resolve the effective repair class toggle, following inheritance.
    Repair classes don't inherit between classes — they use global default."""
    policy = load_policy(root=root)
    classes = policy.get("repair_classes", {})
    return bool(classes.get(name, fallback))


def resolve_policy(surface: str, *, root=None) -> Dict[str, Any]:
    """Resolve the full effective policy for a surface."""
    return {
        "kind": "resolved-policy",
        "surface": surface,
        "threshold": resolve_threshold(surface, root=root),
        "repair_enabled": resolve_repair_enabled(surface, root=root),
        "parent": load_inheritance(root).get(surface, "global"),
        "stored_prose": 0,
    }


def inheritance_card(*, root=None) -> Dict[str, Any]:
    """Operator card showing the inheritance tree."""
    mapping = load_inheritance(root)
    policy = load_policy(root=root)
    thresholds = policy.get("quality_thresholds", {})

    tree = {}
    for child, parent in mapping.items():
        effective = resolve_threshold(child, root=root)
        own = thresholds.get(child)
        tree[child] = {
            "parent": parent,
            "own_threshold": own,
            "effective_threshold": effective,
            "inherited": own is None,
        }

    return {
        "kind": "inheritance-card",
        "mapping": mapping,
        "tree": tree,
        "stored_prose": 0,
    }


def break_inheritance(surface: str, *, root=None) -> Dict[str, Any]:
    """Break inheritance for a surface by copying the parent's value
    into its own policy entry."""
    effective = resolve_threshold(surface, root=root)
    from skeleton.organism.policy_state import set_threshold
    set_threshold(surface, effective, root=root)

    effective_repair = resolve_repair_enabled(surface, root=root)
    from skeleton.organism.policy_state import set_repair_enabled
    set_repair_enabled(surface, effective_repair, root=root)

    return {
        "kind": "inheritance-broken",
        "surface": surface,
        "copied_threshold": effective,
        "copied_repair_enabled": effective_repair,
        "stored_prose": 0,
    }
