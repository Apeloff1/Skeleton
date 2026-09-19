"""GB-11 plane audit. Score only. No rewrite of scored trees."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

from skeleton.artifact_plane.cards import plane_card

PLANES = ("organism", "social", "galaxy")
SCORES = frozenset({"KEEP", "SHIM", "FOLD", "QUARANTINE"})
LEDGER_REL = Path("docs/lineage/plane_audit.jsonl")


def _iter_plane_files(root: Path) -> list[Path]:
    found: list[Path] = []
    for plane in PLANES:
        base = root / "skeleton" / plane
        if not base.is_dir():
            continue
        for path in base.rglob("*"):
            if path.is_file() and path.name != "__pycache__":
                if path.suffix in {".pyc", ".pyo"}:
                    continue
                found.append(path)
    return sorted(found)


class PlaneAudit:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.ledger_path = self.root / LEDGER_REL

    def load_ledger(self) -> list[dict[str, Any]]:
        if not self.ledger_path.is_file():
            return []
        rows: list[dict[str, Any]] = []
        for line in self.ledger_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
        return rows

    def audit(self) -> dict[str, Any]:
        rows = self.load_ledger()
        bad_score = [r["path"] for r in rows if r.get("score") not in SCORES]
        missing_fields = [
            r.get("path", "?")
            for r in rows
            if not all(k in r for k in ("plane", "path", "score", "stored_prose"))
        ]
        prose = [r["path"] for r in rows if r.get("stored_prose") not in (0, "0")]
        ledger_paths = {r["path"] for r in rows}
        disk = _iter_plane_files(self.root)
        disk_rel = {str(p.relative_to(self.root)).replace("\\", "/") for p in disk}
        missing_on_disk = sorted(p for p in disk_rel if p not in ledger_paths)
        hit = 1 if rows and not bad_score and not missing_fields and not prose else 0
        if disk and missing_on_disk:
            hit = 0
        counts: dict[str, int] = {}
        for r in rows:
            counts[str(r.get("score"))] = counts.get(str(r.get("score")), 0) + 1
        return plane_card(
            kind="plane-audit",
            hit=hit,
            law="GB-11",
            citation="docs/lineage/plane_audit.md",
            extra={
                "n": len(rows),
                "counts": counts,
                "bad_score": bad_score,
                "missing_fields": missing_fields,
                "prose": prose,
                "unscored_on_disk": missing_on_disk,
                "ledger_present": self.ledger_path.is_file(),
            },
        )

    def fail_closed(self) -> int:
        return 0 if self.audit().get("hit") == 1 else 2


def scored_paths(rows: Iterable[dict[str, Any]]) -> set[str]:
    return {str(r["path"]) for r in rows}
