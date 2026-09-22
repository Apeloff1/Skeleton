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


def _shape_ok(card: Any) -> bool:
    if not isinstance(card, dict):
        return False
    return all(key in card for key in REQUIRED)


def collect() -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for path in LAYERS:
        try:
            mod = import_module(path)
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
