"""GB-36 capability registry. Empty is legal. Lazy import adapters."""

from __future__ import annotations

from importlib import import_module
from typing import Any

PACKET = "GB-36"
REQUIRED = ("owner", "contract", "failure_modes", "obs", "security")

LAYERS = (
    "skeleton.primitives",
    "skeleton.graphs",
    "skeleton.sheaf",
    "skeleton.spine",
    "skeleton.motive",
    "skeleton.viscera",
    "skeleton.circulation",
    "skeleton.hive",
    "skeleton.hoag",
    "skeleton.persist",
    "skeleton.chronicle",
)

# Explicit literal import targets keep capability discovery lazy while satisfying
# the repository's fail-closed dynamic-import policy.
_LAYER_LOADERS = (
    lambda: import_module("skeleton.primitives"),
    lambda: import_module("skeleton.graphs"),
    lambda: import_module("skeleton.sheaf"),
    lambda: import_module("skeleton.spine"),
    lambda: import_module("skeleton.motive"),
    lambda: import_module("skeleton.viscera"),
    lambda: import_module("skeleton.circulation"),
    lambda: import_module("skeleton.hive"),
    lambda: import_module("skeleton.hoag"),
    lambda: import_module("skeleton.persist"),
    lambda: import_module("skeleton.chronicle"),
)


def _shape_ok(card: Any) -> bool:
    if not isinstance(card, dict):
        return False
    return all(key in card for key in REQUIRED)


def collect() -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for load in _LAYER_LOADERS:
        try:
            mod = load()
        except Exception:
            continue
        fn = getattr(mod, "capabilities", None)
        if not callable(fn):
            continue
        try:
            card = fn()
        except Exception:
            continue
        if not _shape_ok(card):
            continue
        owner = str(card["owner"])
        out[owner] = card
    return out


def capabilities() -> dict[str, Any]:
    cards = collect()
    return {
        "owner": "frontier",
        "packet": PACKET,
        "version": "1.0",
        "contract": {
            "registry": "adapter-capabilities",
            "empty_ok": 1,
            "required": list(REQUIRED),
            "n": len(cards),
            "stored_prose": 0,
        },
        "failure_modes": [
            "shape-miss",
            "second-registry",
            "architecture-index-fork",
        ],
        "obs": ["n", "owners"],
        "security": {"network": 0, "torch": 0, "hf": 0, "ace": "fail-closed"},
        "owners": sorted(cards),
    }
