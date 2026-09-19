"""Pull unused in-tree kernels onto the bank as cards."""
from __future__ import annotations

from importlib import import_module
from typing import Any, Dict

_STOCK_IMPORTERS = {
    "skeleton.kernel.checkpoint": lambda: import_module("skeleton.kernel.checkpoint"),
    "skeleton.kernel.crdt": lambda: import_module("skeleton.kernel.crdt"),
    "skeleton.kernel.dedup": lambda: import_module("skeleton.kernel.dedup"),
    "skeleton.kernel.entropy": lambda: import_module("skeleton.kernel.entropy"),
    "skeleton.kernel.health": lambda: import_module("skeleton.kernel.health"),
    "skeleton.kernel.invariants": lambda: import_module("skeleton.kernel.invariants"),
    "skeleton.kernel.telemetry": lambda: import_module("skeleton.kernel.telemetry"),
    "skeleton.kernel.trace": lambda: import_module("skeleton.kernel.trace"),
}

class Stock:
    """checkpoint, crdt, dedup, entropy, telemetry — import-probed."""

    NAMES = (
        "skeleton.kernel.checkpoint",
        "skeleton.kernel.crdt",
        "skeleton.kernel.dedup",
        "skeleton.kernel.entropy",
        "skeleton.kernel.telemetry",
        "skeleton.kernel.trace",
        "skeleton.kernel.health",
        "skeleton.kernel.invariants",
    )

    def __init__(self) -> None:
        self.present = []
        self.missing = []
        for name in self.NAMES:
            try:
                _STOCK_IMPORTERS[name]()
                self.present.append(name.rsplit(".", 1)[-1])
            except Exception:
                self.missing.append(name.rsplit(".", 1)[-1])

    def card(self) -> Dict[str, Any]:
        return {
            "kind": "kernel-stock",
            "present": list(self.present),
            "missing": list(self.missing),
            "n": len(self.present),
            "stored_prose": 0,
        }
