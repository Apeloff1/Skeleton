"""Persist the five-brain mesh. Atoms + wiki topics. No prose."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

from skeleton.cortex.laws import check
from skeleton.galaxy.atoms import Atom
from skeleton.organism.paths import galaxy_path

CAP = 400


def dump_mesh(mesh) -> Dict[str, Any]:
    seen = {}
    for lib in (*mesh.brains.values(), mesh.wiki):
        for atom in lib.all():
            seen[atom.id] = atom
    atoms = sorted(seen.values(), key=lambda a: a.ts)[-CAP:]
    return check({
        "kind": "galaxy-shelf",
        "topics": dict(mesh.wiki.topics),
        "atoms": [a.to_dict() for a in atoms],
        "n": len(atoms),
        "stored_prose": 0,
    })


def restore_mesh(mesh, data: Dict[str, Any]) -> int:
    n = 0
    for row in data.get("atoms") or []:
        try:
            atom = Atom.from_dict(row)
        except (ValueError, TypeError, KeyError):
            continue
        brain = atom.brain if atom.brain in mesh.brains else "memory"
        mesh.brains[brain].shelve(atom)
        mesh.wiki.shelf[atom.id] = atom
        n += 1
    topics = data.get("topics") or {}
    if isinstance(topics, dict):
        mesh.wiki.topics.update({str(k): str(v)[:240] for k, v in topics.items()})
    return n


def save(system, *, root: Optional[Path] = None) -> Dict[str, Any]:
    payload = dump_mesh(system.mesh)
    payload["pulses"] = int(getattr(system, "pulses", 0) or 0)
    path = galaxy_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")
    return {"path": str(path), "n": payload["n"], "topics": len(payload["topics"])}


def load(system, *, root: Optional[Path] = None) -> Dict[str, Any]:
    path = galaxy_path(root)
    if not path.exists():
        return {"loaded": 0}
    data = json.loads(path.read_text(encoding="utf-8"))
    n = restore_mesh(system.mesh, data)
    system.pulses = int(data.get("pulses") or system.pulses)
    return {"loaded": 1, "n": n, "topics": len(system.mesh.wiki.topics)}
