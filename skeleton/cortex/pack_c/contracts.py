"""Pack C contracts / constraint locks."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Tuple


@dataclass(frozen=True)
class ConstraintLock:
    pfc_attn: bool = False
    unfitted_kind: str = "own"
    error_lattice_importable: bool = True

    def validate(self) -> None:
        assert self.pfc_attn is False
        assert self.unfitted_kind == "own"
        assert self.error_lattice_importable is True


@dataclass
class PackCManifest:
    name: str = "pack_c"
    version: str = "2026.09.20"
    locks: ConstraintLock = field(default_factory=ConstraintLock)
    modules: Tuple[str, ...] = (
        "amalgam_policy",
        "hybrid_router",
        "ledger_hybrid",
        "telemetry",
        "moe_bridge",
        "persistence",
        "scenarios",
        "depth_matrix",
        "queue_lattice",
        "sigil_survival",
        "contracts",
        "operations",
        "evidence",
    )

    def as_dict(self) -> Dict[str, Any]:
        self.locks.validate()
        return {
            "name": self.name,
            "version": self.version,
            "locks": {
                "pfc_attn": self.locks.pfc_attn,
                "unfitted_kind": self.locks.unfitted_kind,
                "error_lattice_importable": self.locks.error_lattice_importable,
            },
            "modules": list(self.modules),
        }
