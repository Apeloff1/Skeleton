"""CCL vault — compact on-disk codec lines under acquired/galaxy/.

One atom per line: T|kind|topic|conf|cite
No prose. Reload is parse-only; atoms are rebuilt as citation/index
handles, not as original stimuli.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from skeleton.cortex.acquire_repo import acquired_dir
from skeleton.galaxy.codec import parse_ccl, render_ccl


from skeleton.organism.caps import live as live_caps

CAP = 400


def vault_dir(root: Optional[Path] = None) -> Path:
    d = acquired_dir(root) / "galaxy"
    d.mkdir(parents=True, exist_ok=True)
    return d


def vault_path(root: Optional[Path] = None) -> Path:
    return vault_dir(root) / "vault.ccl"


def dump(mesh, *, root: Optional[Path] = None) -> Dict[str, Any]:
    seen = {}
    for lib in (*mesh.brains.values(), mesh.wiki):
        for atom in lib.all():
            if not atom.superseded_by:
                seen[atom.id] = atom
    cap = int(getattr(live_caps(), "vault", CAP) or CAP)
    atoms = sorted(seen.values(), key=lambda a: a.ts)[-cap:]
    lines = [render_ccl(a) for a in atoms]
    path = vault_path(root)
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    return {"path": str(path), "n": len(lines), "stored_prose": 0}


def load(root: Optional[Path] = None) -> List[Dict[str, str]]:
    path = vault_path(root)
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(parse_ccl(line))
    return rows
