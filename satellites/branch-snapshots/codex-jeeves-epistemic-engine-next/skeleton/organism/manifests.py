"""Forge manifests — levels, NPC, items, quests. Seeds only. No bodies."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional


DOMAINS = ("levels", "npc", "items", "quests")


def _seed(spec: Dict[str, Any], domain: str, i: int) -> str:
    raw = f"{spec.get('era')}|{spec.get('genre')}|{domain}|{i}|{spec.get('cue')}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]


def build(spec: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    era = str(spec.get("era") or "extraction_now")
    genre = str(spec.get("genre") or "action-adventure")
    out: Dict[str, List[Dict[str, Any]]] = {}
    templates = {
        "levels": ("room_01", "room_02", "extract"),
        "npc": ("vendor", "rival", "guide"),
        "items": ("tool", "core", "vent"),
        "quests": ("reach-extract", "first-core", "cool-heat"),
    }
    for domain, names in templates.items():
        rows = []
        for i, name in enumerate(names):
            rows.append({
                "id": name,
                "domain": domain,
                "era": era,
                "genre": genre,
                "seed": _seed(spec, domain, i),
                "stored_prose": 0,
            })
        out[domain] = rows
    return out


def write(spec: Dict[str, Any], root: Optional[Path] = None) -> Dict[str, Any]:
    base = Path(root) if root else Path(".")
    folder = base / "game" / "data" / "manifests"
    folder.mkdir(parents=True, exist_ok=True)
    bag = build(spec)
    n = 0
    for domain, rows in bag.items():
        p = folder / f"{domain}.json"
        p.write_text(json.dumps({"kind": f"manifest-{domain}", "rows": rows, "stored_prose": 0}, indent=2), encoding="utf-8")
        n += len(rows)
    return {"kind": "manifests", "n": n, "domains": list(bag), "dir": str(folder), "stored_prose": 0}
