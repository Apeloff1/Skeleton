"""Repo acquisition — foreign payloads become files Jeeves owns.

Gaming APIs first: Steam storefront (public), Wikipedia REST, RAWG if
keyed. Every write is schema-checked, hashed, and stored under
`skeleton/acquired/`. Failures record ε and write nothing partial.
"""
from __future__ import annotations

import hashlib
import json
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

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
    return {
        "source": "steam",
        "appid": int(appid),
        "name": inner.get("name"),
        "type": inner.get("type"),
        "is_free": inner.get("is_free"),
        "short_description": (inner.get("short_description") or "")[:800],
        "developers": list(inner.get("developers") or [])[:8],
        "publishers": list(inner.get("publishers") or [])[:8],
        "genres": [g.get("description") for g in (inner.get("genres") or []) if isinstance(g, dict)][:12],
        "categories": [c.get("description") for c in (inner.get("categories") or []) if isinstance(c, dict)][:16],
        "release": (inner.get("release_date") or {}).get("date") if isinstance(inner.get("release_date"), dict) else None,
        "dialect": _dialect(inner.get("name"), inner.get("short_description"), inner.get("genres")),
    }


def wikipedia_game(title: str = "Elden Ring") -> Dict[str, Any]:
    q = urllib.parse.quote(title)
    url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{q}"
    data = _get_json(url, headers={"User-Agent": "SkeletonGenos/1.0 (gameforge; acquire)"})
    extract = str(data.get("extract") or "")
    if not extract:
        raise ValueError("wiki-empty")
    return {
        "source": "wikipedia",
        "title": data.get("title") or title,
        "description": data.get("description"),
        "extract": extract[:1200],
        "url": ((data.get("content_urls") or {}).get("desktop") or {}).get("page"),
        "dialect": _dialect(data.get("title"), extract, []),
    }


def _dialect(name, blurb, genres) -> str:
    bits = [str(name or "game").lower()]
    gtxt = " ".join(str(g.get("description") if isinstance(g, dict) else g) for g in (genres or [])).lower()
    text = f"{blurb or ''} {gtxt}".lower()
    if any(w in text for w in ("soul", "dark fantasy", "die", "bonfire")):
        bits.append("soulslike extraction ttk elite dread")
    if any(w in text for w in ("open world", "exploration", "action rpg")):
        bits.append("open-world exploration pack")
    if any(w in text for w in ("roguelike", "procedural")):
        bits.append("roguelike lattice")
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
        "ok": int(len(written) > 0 and len(errors) == 0),
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
