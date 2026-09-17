"""Export build report card. No secrets. Spec hash + mass + critique minima."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

from skeleton.game.critique import critique
from skeleton.game.emit_pack import default_tree, validate_emit
from skeleton.game.mass import trajectory
from skeleton.game.spec import compile_spec


class BuildReportError(ValueError):
    """Build report contract violation."""


def _hash(payload: Mapping[str, Any]) -> str:
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def report(
    *,
    vision: str = "NEXUS-EXTRACT #807",
    seed: int = 8847291,
    forges: int = 4,
) -> dict[str, Any]:
    spec = compile_spec(vision)
    mass_path = trajectory(1.0, forges)
    taste = critique({"fun": 0.62, "clarity": 0.71, "feasibility": 0.58, "originality": 0.66})
    emit = validate_emit(default_tree())
    debts = []
    if spec["conflicts"]:
        debts.append("vision-conflicts")
    if emit["valid"] != 1:
        debts.append("emit-tree")
    payload = {
        "kind": "build_report",
        "spec_hash": _hash({"fields": spec["fields"], "conflicts": spec["conflicts"]}),
        "seed": int(seed),
        "mass_trajectory": mass_path,
        "critique_min": taste["min"],
        "weakest": taste["weakest"],
        "emit_files": emit["files"],
        "debts": debts,
        "sota_ready": False,
        "stored_prose": 0,
    }
    payload["digest"] = _hash(payload)
    payload["ok"] = True
    return payload
