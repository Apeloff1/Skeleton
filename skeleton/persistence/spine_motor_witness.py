"""Witness that the spine package does not import Motor.

Scans the persistence modules named by the caller. A motor or pymongo import
fails closed. This witness does not import Motor and does not call create_index.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any


class SpineMotorWitnessError(RuntimeError):
    """Motor witness rejected its inputs. Not a maturity signal."""


class SpineMotorWitness:
    """Read import names. Do not bootstrap a driver."""

    def card(self, root: str | Path) -> dict[str, Any]:
        base = Path(root)
        if not base.is_dir():
            raise SpineMotorWitnessError("root must be a directory")
        hits: list[str] = []
        scanned = 0
        for path in sorted(base.glob("spine_*.py")):
            scanned += 1
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                names: list[str] = []
                if isinstance(node, ast.Import):
                    names = [alias.name.split(".")[0] for alias in node.names]
                elif isinstance(node, ast.ImportFrom) and node.module:
                    names = [node.module.split(".")[0]]
                for name in names:
                    if name in {"motor", "pymongo"}:
                        hits.append(f"{path.name}:{name}")
        if hits:
            raise SpineMotorWitnessError("spine module imports a live driver")
        return {
            "kind": "spine_motor_witness",
            "hit": False,
            "law": "motor-not-imported",
            "citation": "VOL-134",
            "scanned": scanned,
            "driver_imports": 0,
            "live_motor": False,
            "stored_prose": 0,
            "completion_checkbox": False,
            "implementation_signature": False,
            "verification_signature": False,
        }
