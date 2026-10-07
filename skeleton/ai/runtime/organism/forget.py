"""Selective forget + reversible states + reconsolidation.

House mapping, not their controllers:
  active   — default
  dormant  — low-confidence capture, not internalized
  retired  — dormant that stayed cold; superseded_by=forget-retire
  reconsolidate — token overlap with a cue raises confidence, wakes dormant

Cites 2604.20300 / 2606.15903 / 2608.18177 / 2605.08538 as the split.
No paper bodies. Retired is reversible until persist writes it.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable

from skeleton.galaxy.atoms import token_set

CITE = (
    "https://arxiv.org/abs/2604.20300",
    "https://arxiv.org/abs/2606.15903",
    "https://arxiv.org/abs/2608.18177",
    "https://arxiv.org/abs/2605.08538",
)

DORMANT_FLOOR = 0.35
RETIRE_FLOOR = 0.22


def _atoms(mesh) -> Iterable:
    for lib in (*(mesh.brains or {}).values(), getattr(mesh, "wiki", None)):
        if lib is None:
            continue
        yield from lib.all()


def decay(mesh) -> Dict[str, Any]:
    dormant = retired = 0
    for atom in _atoms(mesh):
        if atom.kind == "principle" or "internalized" in (atom.tags or ()):
            continue
        if atom.superseded_by:
            continue
        tags = set(atom.tags or ())
        if atom.confidence < RETIRE_FLOOR or "dormant" in tags:
            if atom.confidence < RETIRE_FLOOR:
                atom.superseded_by = "forget-retire"
                tags.add("retired")
                tags.discard("dormant")
                retired += 1
            elif "dormant" not in tags and atom.confidence < DORMANT_FLOOR:
                tags.add("dormant")
                dormant += 1
        elif atom.confidence < DORMANT_FLOOR:
            tags.add("dormant")
            dormant += 1
        try:
            from skeleton.memory.forgetting import MemoryTrace, retrievability
            ts = float(getattr(atom, "ts", 0) or 0)
            if ts > 1e12:
                ts = ts / 1000.0
            if ts > 0:
                r = retrievability(MemoryTrace(
                    memory_id=str(atom.id), created_at=ts, last_recalled_at=ts,
                    recalls=0, importance=float(atom.confidence), salience=0.4,
                ))
                if r < 0.12 and atom.kind != "principle":
                    tags.add("dormant")
                    atom.confidence = min(float(atom.confidence), max(0.08, r))
                    dormant += 1
        except Exception:
            pass
        atom.tags = tuple(tags)
        if "dormant" in tags and not atom.superseded_by:
            atom.confidence = max(0.05, float(atom.confidence) * 0.92)
    return {"kind": "decay", "dormant": dormant, "retired": retired, "stored_prose": 0}


def reconsolidate(mesh, cue: str) -> Dict[str, Any]:
    src = set(token_set(cue or ""))
    woke = 0
    if not src:
        return {"kind": "reconsolidate", "woke": 0, "stored_prose": 0}
    for atom in _atoms(mesh):
        tok = set(token_set(f"{atom.topic} {atom.dialect}"))
        if not tok or len(src & tok) / len(src | tok) < 0.28:
            continue
        tags = set(atom.tags or ())
        if atom.superseded_by == "forget-retire":
            atom.superseded_by = ""
            tags.discard("retired")
        tags.discard("dormant")
        tags.add("reconsolidated")
        atom.tags = tuple(tags)
        atom.confidence = min(0.95, max(float(atom.confidence), 0.62) + 0.08)
        woke += 1
    return {"kind": "reconsolidate", "woke": woke, "stored_prose": 0}


def sweep(mesh, *, cue: str = "") -> Dict[str, Any]:
    d = decay(mesh)
    r = reconsolidate(mesh, cue) if cue else {"kind": "reconsolidate", "woke": 0, "stored_prose": 0}
    return {
        "kind": "forget",
        "decay": d,
        "reconsolidate": r,
        "cite": list(CITE),
        "stored_prose": 0,
    }
