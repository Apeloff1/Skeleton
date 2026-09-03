"""Decade dump — rotate hot books into backup files for bigger hardware.

When a hot file exceeds HOT_BYTES, copy it into chronicle/backup/YYYY/
with a sha256 manifest line, then trim the hot file. Restore lists
every dump so a larger machine can ingest the decade.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from skeleton.cortex.laws import check
from skeleton.organism.chronicle.books import (
    HOT_BYTES, HORIZON_YEARS, backup_dir, manifest_path, root as croot,
)
from skeleton.organism.paths import helix_sense_path, helix_snap_path, ledger_path
from skeleton.organism.journal import journal_path


def _sha_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _hot_targets(root: Optional[Path] = None) -> List[Path]:
    return [
        journal_path(root),
        ledger_path(root),
        helix_sense_path(root),
        helix_snap_path(root),
        croot(root) / "itinerary.jsonl",
    ]


def due(root: Optional[Path] = None) -> List[str]:
    ready = []
    for path in _hot_targets(root):
        limit = HOT_BYTES
        try:
            from skeleton.kernel.profiles import live_overlay
            extra = live_overlay().get("dump_hot_bytes")
            if extra:
                limit = min(limit, int(extra))
        except Exception:
            pass
        if path.exists() and path.stat().st_size >= limit:
            ready.append(str(path.name))
    return ready


def _manifest(row: Dict[str, Any], *, root: Optional[Path] = None) -> None:
    path = manifest_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(check(row), sort_keys=True, default=str) + "\n")


def rotate(src: Path, *, root: Optional[Path] = None) -> Dict[str, Any]:
    if not src.exists() or src.stat().st_size == 0:
        return {"rotated": 0, "name": src.name}
    year = datetime.now(timezone.utc).year
    dest = backup_dir(year, root_=root) / f"{src.stem}-{int(time.time())}{src.suffix}"
    shutil.copy2(src, dest)
    digest = _sha_file(dest)
    _manifest({
        "kind": "dump",
        "at": int(time.time() * 1000),
        "name": src.name,
        "dest": str(dest),
        "size": dest.stat().st_size,
        "sha256": digest,
        "year": year,
        "horizon": HORIZON_YEARS,
        "stored_prose": 0,
    }, root=root)
    # keep a hot tail so the live organism still has recent lines
    if src.suffix == ".jsonl":
        lines = src.read_text(encoding="utf-8").splitlines()
        keep = lines[-400:] if len(lines) > 400 else lines
        src.write_text(("\n".join(keep) + "\n") if keep else "", encoding="utf-8")
    return {"rotated": 1, "name": src.name, "dest": str(dest), "sha256": digest, "stored_prose": 0}


def dump(root: Optional[Path] = None, *, force: bool = False) -> Dict[str, Any]:
    names = due(root) if not force else [p.name for p in _hot_targets(root) if p.exists()]
    rotated = []
    for path in _hot_targets(root):
        if force or path.name in names:
            card = rotate(path, root=root)
            if card.get("rotated"):
                rotated.append(card)
    return {
        "kind": "decade-dump",
        "n": len(rotated),
        "rotated": [r["name"] for r in rotated],
        "horizon_years": HORIZON_YEARS,
        "hot_bytes": HOT_BYTES,
        "stored_prose": 0,
    }


def inventory(root: Optional[Path] = None) -> Dict[str, Any]:
    path = manifest_path(root)
    rows: List[Dict[str, Any]] = []
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    years = sorted({int(r.get("year") or 0) for r in rows if r.get("year")})
    return {
        "kind": "dump-inventory",
        "n": len(rows),
        "years": years,
        "horizon_years": HORIZON_YEARS,
        "files": [r.get("dest") for r in rows[-24:]],
        "stored_prose": 0,
    }
