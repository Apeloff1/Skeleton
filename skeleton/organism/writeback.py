"""Dual-layer write-back — mark high-value atoms internalized.

High-value: principle, or confidence ≥ 0.80. Those topics suppress
later `new` writes (router skip). Mouth parameters are touched only
if neo exposes ingest_residual; otherwise the mark is the whole act.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, Set

from skeleton.galaxy.atoms import token_set


def high_value(atom) -> bool:
    return (atom.kind == "principle" or float(atom.confidence) >= 0.80) and not atom.superseded_by


def into_mouth(neo, topics_n: int) -> Dict[str, Any]:
    """Parametric path. Fail-closed. No HF. No teacher prose."""
    if neo is None:
        return {"mouth": 0, "lora": 0, "merged": 0, "residual": 0}
    out = {"mouth": 1, "lora": 0, "merged": 0, "residual": 0}
    try:
        if hasattr(neo, "attach_lora"):
            info = neo.attach_lora(rank=2)
            out["lora"] = 1 if info else 0
        if hasattr(neo, "ingest_residual"):
            neo.ingest_residual("writeback internalized %s" % topics_n)
            out["residual"] = 1
        if hasattr(neo, "merge_lora"):
            neo.merge_lora()
            out["merged"] = 1
    except Exception as exc:
        out["error"] = type(exc).__name__
    return out


def absorb(mesh, *, neo=None) -> Dict[str, Any]:
    marked = []
    for lib in (*mesh.brains.values(), mesh.wiki):
        for atom in lib.all():
            if not high_value(atom):
                continue
            if "internalized" in (atom.tags or ()):
                continue
            atom.tags = tuple(set(atom.tags or ()) | {"internalized"})
            marked.append(atom.id)
    mouth = into_mouth(neo, len(marked))
    return {"kind": "write-back", "marked": len(marked), "stored_prose": 0, **mouth}


def topics(mesh) -> Set[str]:
    out: Set[str] = set()
    for lib in (*mesh.brains.values(), mesh.wiki):
        for atom in lib.all():
            if "internalized" in (atom.tags or ()):
                out.add(atom.topic)
    return out


def should_suppress(stimulus: str, internalized: Iterable[str]) -> bool:
    src = set(token_set(stimulus))
    if not src:
        return False
    for topic in internalized:
        tok = set(token_set(topic))
        if tok and len(src & tok) / len(src | tok) >= 0.72:
            return True
    return False
