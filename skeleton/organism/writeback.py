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


def absorb(mesh) -> Dict[str, Any]:
    marked = []
    for lib in (*mesh.brains.values(), mesh.wiki):
        for atom in lib.all():
            if not high_value(atom):
                continue
            if "internalized" in (atom.tags or ()):
                continue
            atom.tags = tuple(set(atom.tags or ()) | {"internalized"})
            marked.append(atom.id)
    return {"kind": "write-back", "marked": len(marked), "stored_prose": 0}


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
