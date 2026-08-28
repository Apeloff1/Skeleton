"""Repo acquisition — pointers and house dialect only.

Law: do not store third-party prose, assets, binaries, or keys.
Steam and Wikipedia are cited by URL. Files keep id, title, house dialect.
"""
from __future__ import annotations

import hashlib
import json
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT_NAME = "skeleton/acquired"


def repo_root(start: Optional[Path] = None) -> Path:
    here = Path(start or Path(__file__).resolve())
    for p in [here, *here.parents]:
        if (p / "skeleton" / "cortex").is_dir() and (p / "tests").is_dir():
            return p
    return Path.cwd()


def acquired_dir(root: Optional[Path] = None) -> Path:
    d = (root or repo_root()) / ROOT_NAME
    d.mkdir(parents=True, exist_ok=True)
    (d / "gaming").mkdir(parents=True, exist_ok=True)
    (d / "gates").mkdir(parents=True, exist_ok=True)
    (d / "genos").mkdir(parents=True, exist_ok=True)
    return d


def _get_json(url: str, *, timeout: float = 8.0, headers: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    req = urllib.request.Request(url, headers=headers or {"User-Agent": "SkeletonGenos/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8")
    data = json.loads(raw)
    if not isinstance(data, dict):
        return {"payload": data}
    return data


def _write(path: Path, payload: Dict[str, Any]) -> Dict[str, Any]:
    if not payload:
        raise ValueError("empty-payload")
    blob = json.dumps(payload, indent=2, sort_keys=True, default=str)
    digest = hashlib.sha256(blob.encode("utf-8")).hexdigest()
    payload = dict(payload)
    payload["sha256"] = digest
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")
    return {"path": str(path), "sha256": digest, "bytes": path.stat().st_size}


def steam_app(appid: int = 1245620) -> Dict[str, Any]:
    url = f"https://store.steampowered.com/api/appdetails?appids={int(appid)}&l=en"
    data = _get_json(url)
    node = data.get(str(appid)) or data.get(appid) or {}
    inner = node.get("data") if isinstance(node, dict) else None
    if not isinstance(inner, dict):
        raise ValueError("steam-empty")
    genres = [g.get("description") for g in (inner.get("genres") or []) if isinstance(g, dict)][:8]
    name = inner.get("name")
    return {
        "source": "steam",
        "appid": int(appid),
        "name": name,
        "type": inner.get("type"),
        "url": f"https://store.steampowered.com/app/{int(appid)}/",
        "genres": genres,
        "dialect": _dialect(name, "", genres),
    }


def wikipedia_game(title: str = "Elden Ring") -> Dict[str, Any]:
    q = urllib.parse.quote(title)
    url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{q}"
    data = _get_json(url, headers={"User-Agent": "SkeletonGenos/1.0 (gameforge; acquire)"})
    title_out = data.get("title") or title
    url = ((data.get("content_urls") or {}).get("desktop") or {}).get("page")
    if not title_out:
        raise ValueError("wiki-empty")
    return {
        "source": "wikipedia",
        "title": title_out,
        "url": url or f"https://en.wikipedia.org/wiki/{urllib.parse.quote(str(title_out))}",
        "license": "CC BY-SA — cite the URL, do not copy the article",
        "dialect": _dialect(title_out, "", []),
    }


def _dialect(name, blurb, genres) -> str:
    bits = [str(name or "game").lower()]
    gtxt = " ".join(str(g.get("description") if isinstance(g, dict) else g) for g in (genres or [])).lower()
    text = f"{blurb or ''} {gtxt}".lower()
    if any(w in text for w in ("soul", "dark fantasy", "die", "bonfire", "sekiro", "bloodborne")):
        bits.append("soulslike extraction ttk elite dread")
    if any(w in text for w in ("open world", "exploration", "action rpg")):
        bits.append("open-world exploration pack")
    if any(w in text for w in ("roguelike", "rogue-lite", "procedural", "hades", "slay the spire")):
        bits.append("roguelike lattice mix trash elite boss")
    if any(w in text for w in ("metroid", "castlevania", "hollow knight", "backtrack")):
        bits.append("metroidvania backtrack map")
    if any(w in text for w in ("extract", "tarkov", "hunt", "lethal")):
        bits.append("extraction_now ttk elite dread")
    if any(w in text for w in ("cozy", "farm", "stardew")):
        bits.append("cozy harvest era")
    bits.append("plan tensor ttk hp dps")
    return " ".join(bits)


def acquire_gaming(neo=None, *, appid: int = 1245620, title: str = "Elden Ring",
                   root: Optional[Path] = None) -> Dict[str, Any]:
    dest = acquired_dir(root) / "gaming"
    written: List[Dict[str, Any]] = []
    errors: List[str] = []
    dialect_bits: List[str] = []
    try:
        steam = steam_app(appid)
        written.append(_write(dest / f"steam_{appid}.json", steam))
        if steam.get("dialect"):
            dialect_bits.append(str(steam["dialect"]))
    except Exception as exc:
        errors.append(f"steam:{type(exc).__name__}")
    try:
        wiki = wikipedia_game(title)
        slug = "".join(ch if ch.isalnum() else "_" for ch in title.lower())[:40]
        written.append(_write(dest / f"wiki_{slug}.json", wiki))
        if wiki.get("dialect"):
            dialect_bits.append(str(wiki["dialect"]))
    except Exception as exc:
        errors.append(f"wiki:{type(exc).__name__}")
    index = {
        "kind": "gaming-acquire",
        "written": written,
        "errors": errors,
        "ok": int(any(str(w.get("path") or "").endswith(".json") and "index" not in str(w.get("path") or "") for w in written[:-1]) if written else 0),
        "dialect": " | ".join(dialect_bits)[:400],
    }
    written.append(_write(dest / "index.json", index))
    if neo is not None and dialect_bits:
        blob = " ".join(dialect_bits)
        xf = getattr(neo, "transformer", None)
        if xf is not None and hasattr(xf, "fit"):
            xf.fit([blob], lr=0.04, schedule="cosine")
        rms = getattr(neo, "neo_rms", None)
        if rms is not None and hasattr(rms, "fit"):
            rms.fit([blob], lr=0.04, schedule="cosine")
        if hasattr(neo, "own") and hasattr(neo.own, "ingest_model"):
            neo.own.ingest_model("gaming", index)
        if hasattr(neo, "think"):
            neo.think(blob[:180])
    return {"acquired": len(written), "errors": errors, "files": written, "dialect": index.get("dialect")}


def acquire_catalog(root: Optional[Path] = None) -> Dict[str, Any]:
    from skeleton.cortex.catalog import catalog
    from skeleton.cortex.gates import probe_all
    dest = acquired_dir(root) / "gates"
    card = {"kind": "catalog", "families": catalog(), "probe": probe_all()}
    meta = _write(dest / "catalog.json", card)
    return {"acquired": 1, "errors": [], "files": [meta]}


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


def acquire_spree(neo=None, *, root: Optional[Path] = None) -> Dict[str, Any]:
    dest = acquired_dir(root) / "gaming"
    rows: List[Dict[str, Any]] = []
    errors: List[str] = []
    dialects: List[str] = []
    for game in SPREE:
        row = {"title": game["title"], "appid": game["appid"], "era": game["era"], "ok": 0}
        try:
            out = acquire_gaming(None, appid=int(game["appid"]), title=str(game["title"]), root=root)
            row["ok"] = 1 if not out.get("errors") else 0
            row["files"] = len(out.get("files") or [])
            row["errors"] = list(out.get("errors") or [])
            if out.get("dialect"):
                dialects.append(str(out["dialect"]))
            errors.extend(f"{game['title']}:{e}" for e in (out.get("errors") or []))
        except Exception as exc:
            row["errors"] = [type(exc).__name__]
            errors.append(f"{game['title']}:{type(exc).__name__}")
        rows.append(row)
    blob = " || ".join(dialects)
    if neo is not None and blob:
        xf = getattr(neo, "transformer", None)
        if xf is not None:
            xf.fit(dialects, lr=0.04, schedule="cosine")
        rms = getattr(neo, "neo_rms", None)
        if rms is not None:
            rms.fit(dialects, lr=0.04, schedule="cosine")
        if hasattr(neo, "own"):
            neo.own.ingest_model("gaming-spree", {"n": len(rows), "dialect": blob[:400]})
        if hasattr(neo, "think"):
            for d in dialects[:8]:
                neo.think(d[:160])
        if hasattr(neo, "genos"):
            pulse = neo.genos(blob[:180])
        else:
            pulse = {}
    else:
        pulse = {}
    index = {
        "kind": "gaming-spree",
        "games": rows,
        "ok": int(all(r.get("ok") for r in rows)),
        "errors": errors,
        "n": len(rows),
        "dialects": len(dialects),
        "G": (pulse or {}).get("G"),
        "epsilon": (pulse or {}).get("epsilon"),
    }
    written = _write(dest / "spree.json", index)
    if pulse:
        _write(acquired_dir(root) / "genos" / "spree_pulse.json", {"kind": "genos-spree", "card": pulse})
    return {"acquired": len(rows), "ok": index["ok"], "errors": errors, "files": [written], "pulse": pulse}
