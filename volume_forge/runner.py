"""Stride runner. Requires a regenerated emit tree. Do not import emit_x100."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

def sample(emit_root: Path, stride: int = 64) -> dict[str, object]:
    sys.path.insert(0, str(emit_root.parent))
    package = emit_root.name
    rows = []
    modules = [p for p in sorted(emit_root.rglob("*.py")) if p.name != "__init__.py"][::stride]
    for path in modules:
        mod = importlib.import_module(f"{package}.{path.parent.name}.{path.stem}")
        out = mod.run(1.0)
        if int(out["stored_prose"]) != 0:
            raise RuntimeError("stored_prose")
        rows.append({"house": path.parent.name, "organ": path.stem, "mass": out["mass"]})
    return {"sampled": len(rows), "rows": rows}
