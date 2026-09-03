"""Pull unused in-tree kernels onto the bank as cards."""
from __future__ import annotations

from typing import Any, Dict


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
                __import__(name)
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
