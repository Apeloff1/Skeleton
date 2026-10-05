"""Reference tools — games are pointers. Parse on demand.

The house does not keep Steam blurbs or Wikipedia articles. A game is
an appid, a title, a URL, an era. parse_ref() may fetch a page, run it
through laws + anti-plagiarism, and emit house dialect. The page itself
is not written.
"""
from __future__ import annotations

import hashlib
import json
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from skeleton.cortex.antiplag import distill_dialect, guard
from skeleton.cortex.laws import LawError, check

ROOT_NAME = "skeleton/acquired"

SPREE: Tuple[Dict[str, Any], ...] = (
    {"appid": 1245620, "title": "Elden Ring", "era": "soulslike"},
    {"appid": 374320, "title": "Dark Souls III", "era": "soulslike"},
    {"appid": 814380, "title": "Sekiro Shadows Die Twice", "era": "soulslike"},
    {"appid": 1627720, "title": "Lies of P", "era": "soulslike"},
    {"appid": 1145360, "title": "Hades", "era": "roguelike"},
    {"appid": 646570, "title": "Slay the Spire", "era": "roguelike"},
    {"appid": 518790, "title": "Dead Cells", "era": "roguelike"},
    {"appid": 367520, "title": "Hollow Knight", "era": "metroidvania"},
    {"appid": 1809540, "title": "Nine Sols", "era": "metroidvania"},
    {"appid": 594650, "title": "Hunt Showdown", "era": "extraction_now"},
    {"appid": 1966720, "title": "Lethal Company", "era": "extraction_now"},
    {"appid": 413150, "title": "Stardew Valley", "era": "cozy"},
)


def repo_root(start: Optional[Path] = None) -> Path:
    here = Path(start or Path(__file__).resolve())
    for p in [here, *here.parents]:
        if (p / "skeleton" / "cortex").is_dir() and (p / "tests").is_dir():
            return p
    return Path.cwd()


def acquired_dir(root: Optional[Path] = None) -> Path:
    d = (root or repo_root()) / ROOT_NAME
    (d / "gaming").mkdir(parents=True, exist_ok=True)
    (d / "gates").mkdir(parents=True, exist_ok=True)
    (d / "genos").mkdir(parents=True, exist_ok=True)
    return d


def _write(path: Path, payload: Dict[str, Any]) -> Dict[str, Any]:
    payload = check(dict(payload))
    blob = json.dumps(payload, indent=2, sort_keys=True, default=str)
    digest = hashlib.sha256(blob.encode("utf-8")).hexdigest()
    payload["sha256"] = digest
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")
    return {"path": str(path), "sha256": digest, "bytes": path.stat().st_size}


def reference_of(game: Dict[str, Any]) -> Dict[str, Any]:
    from skeleton.cortex.cite import SPDX_STEAM, SPDX_WIKI, steam_cite, wiki_cite
    appid = int(game["appid"])
    title = str(game["title"])
    era = str(game.get("era") or "")
    dialect = distill_dialect(title, era)
    steam = steam_cite(appid, title, era=era, dialect=dialect)
    wiki = wiki_cite(title)
    return check({
        "kind": "reference",
        "appid": appid,
        "title": title,
        "era": era,
        "source": "steam",
        "url": steam["url"],
        "wiki": wiki["url"],
        "license": SPDX_STEAM,
        "wiki_license": SPDX_WIKI,
        "citation": steam["citation"],
        "wiki_citation": wiki["citation"],
        "dialect": dialect,
        "stored_prose": 0,
    })


def references() -> List[Dict[str, Any]]:
    return [reference_of(g) for g in SPREE]


def write_references(root: Optional[Path] = None) -> Dict[str, Any]:
    dest = acquired_dir(root) / "gaming"
    card = {"kind": "reference-index", "n": len(SPREE), "games": references()}
    return _write(dest / "references.json", card)


def _get_json(url: str, *, timeout: float = 8.0, headers: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    from skeleton.cortex.polite import fetch_json
    return fetch_json(url, timeout=timeout, headers=headers)


def parse_ref(appid: int, *, title: str = "", era: str = "") -> Dict[str, Any]:
    """Fetch live metadata. Persist nothing from the page. Return house dialect."""
    ref = reference_of({"appid": appid, "title": title or str(appid), "era": era})
    source_text = ""
    live_name = title
    genres: List[str] = []
    try:
        data = _get_json(f"https://store.steampowered.com/api/appdetails?appids={int(appid)}&l=en")
        node = data.get(str(appid)) or {}
        inner = node.get("data") if isinstance(node, dict) else None
        if isinstance(inner, dict):
            live_name = str(inner.get("name") or live_name)
            genres = [g.get("description") for g in (inner.get("genres") or []) if isinstance(g, dict)][:8]
            source_text = str(inner.get("short_description") or "")
    except Exception as exc:
        return {**ref, "parsed": 0, "error": type(exc).__name__}
    dialect = distill_dialect(live_name, era, genres)
    try:
        dialect = guard(dialect, source_text)
    except LawError as exc:
        return {**ref, "parsed": 0, "error": str(exc), "law": exc.law}
    out = check({
        "kind": "parse",
        "appid": int(appid),
        "title": live_name,
        "era": era,
        "url": ref["url"],
        "genres": genres,
        "dialect": dialect,
        "parsed": 1,
        "stored_prose": 0,
    })
    return out


def acquire_gaming(neo=None, *, appid: int = 1245620, title: str = "Elden Ring",
                   root: Optional[Path] = None) -> Dict[str, Any]:
    era = next((g["era"] for g in SPREE if int(g["appid"]) == int(appid)), "")
    parsed = parse_ref(int(appid), title=title, era=era)
    write_references(root)
    if neo is not None and parsed.get("dialect"):
        xf = getattr(neo, "transformer", None)
        if xf is not None:
            xf.fit([parsed["dialect"]], lr=0.04, schedule="cosine")
    return {"acquired": 1, "errors": [] if parsed.get("parsed") else [parsed.get("error") or "parse"],
            "files": [], "dialect": parsed.get("dialect"), "ref": parsed}


def acquire_spree(neo=None, *, root: Optional[Path] = None) -> Dict[str, Any]:
    written = write_references(root)
    dialects = [r["dialect"] for r in references()]
    errors: List[str] = []
    if neo is not None:
        xf = getattr(neo, "transformer", None)
        if xf is not None:
            xf.fit(dialects, lr=0.04, schedule="cosine")
        rms = getattr(neo, "neo_rms", None)
        if rms is not None:
            rms.fit(dialects, lr=0.04, schedule="cosine")
        if hasattr(neo, "genos"):
            pulse = neo.genos(" ".join(dialects)[:180])
        else:
            pulse = {}
    else:
        pulse = {}
    return {
        "acquired": len(SPREE),
        "ok": 1,
        "errors": errors,
        "files": [written],
        "pulse": pulse,
        "mode": "references",
    }


def acquire_catalog(root: Optional[Path] = None) -> Dict[str, Any]:
    from skeleton.cortex.catalog import catalog
    from skeleton.cortex.gates import probe_all
    dest = acquired_dir(root) / "gates"
    card = {"kind": "catalog", "families": catalog(), "probe": probe_all()}
    meta = _write(dest / "catalog.json", card)
    return {"acquired": 1, "errors": [], "files": [meta]}
