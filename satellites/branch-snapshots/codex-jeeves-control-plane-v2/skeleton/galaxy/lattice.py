"""Command-deck lattice — Hoag rings + mouth satellites as a data card.

Not a GUI. Nodes and an ASCII ring so the deck can render later
without inventing pixels. Counts come from the live mesh.
"""
from __future__ import annotations

from typing import Any, Dict, List

from skeleton.galaxy.hoag import BRAINS, GAP, NUCLEUS, galaxy_card
from skeleton.galaxy.mirrors import mouth_mirrors


def _bar(n: int, width: int = 12) -> str:
    fill = min(width, max(0, n))
    return "#" * fill + "." * (width - fill)


def card(mesh=None, *, neo=None) -> Dict[str, Any]:
    nodes: List[Dict[str, Any]] = [
        {"id": NUCLEUS["id"], "role": NUCLEUS["role"], "color": NUCLEUS["color"],
         "ring": NUCLEUS["ring"], "size": len(getattr(getattr(mesh, "wiki", None), "topics", {}) or {})},
    ]
    ascii_rows = [f"nucleus wiki topics={nodes[0]['size']}"]
    if mesh is not None:
        for row in BRAINS:
            lib = mesh.brains.get(row["id"])
            size = len(lib.shelf) if lib is not None else 0
            nodes.append({**row, "size": size})
            ascii_rows.append(f"r{row['ordinal']} {row['id']:10} {row['color']} {_bar(min(12, size))} {size}")
    mouths = mouth_mirrors()
    bound = 0
    if neo is not None:
        slots = getattr(neo, "slots", {}) or {}
        xf = getattr(neo, "transformer", None)
        bound = int(bool(xf) or bool(slots))
    ascii_rows.append(f"gap mouths={len(mouths)} bound={bound} via=jeeves color={GAP['color']}")
    profile = ""
    compact = False
    try:
        from skeleton.kernel.profiles import card as kernels_card
        k = kernels_card()
        profile = str(k.get("profile") or "")
        compact = profile in {"mobile", "tight"}
    except Exception:
        pass
    if compact:
        ascii_rows = ascii_rows[:3] + [ascii_rows[-1]]
    return {
        "kind": "lattice",
        "hoag": galaxy_card(),
        "nodes": nodes,
        "mouths": len(mouths),
        "bound": bound,
        "profile": profile,
        "compact": int(compact),
        "ascii": "\n".join(ascii_rows),
        "stored_prose": 0,
    }
