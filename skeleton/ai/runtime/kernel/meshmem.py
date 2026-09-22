"""Place mesh atom ids into the RAM arena.

Librarian still owns the atom. Arena owns the frame. Under pressure
the balloon drops frames; the atom stays until cap-trim.
"""
from __future__ import annotations

from typing import Any, Dict


def place(mesh, arena) -> Dict[str, Any]:
    if mesh is None or arena is None:
        return {"kind": "meshmem", "placed": 0, "stored_prose": 0}
    n = 0
    for lib in (*getattr(mesh, "brains", {}).values(), getattr(mesh, "wiki", None)):
        if lib is None:
            continue
        for atom in list(lib.all())[:48]:
            if atom.superseded_by:
                continue
            arena.put(str(atom.id), need=16)
            n += 1
    return {"kind": "meshmem", "placed": n, "ram": arena.card(), "stored_prose": 0}
