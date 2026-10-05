"""P4 ship — zip Godot / data / web, write store metadata, mobile health card."""
from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any, Dict, Optional


def store_meta(spec: Dict[str, Any]) -> Dict[str, Any]:
    era = str(spec.get("era") or "extraction_now")
    genre = str(spec.get("genre") or "action-adventure")
    vision = str(spec.get("vision") or f"{genre} in {era}")
    tags = [genre, era.split("_")[0], "godot", "skeleton"]
    stills = [
        f"{vision} — spawn room, wide still, no text",
        f"{vision} — extract door, heat haze, no text",
        f"{vision} — player tool on a data core, no text",
    ]
    return {
        "kind": "store-meta",
        "title": genre.replace("-", " ").title(),
        "description": vision[:280],
        "tags": tags,
        "stills": stills,
        "stored_prose": 0,
    }


def _zip_dir(src: Path, dest: Path, *, only: Optional[str] = None) -> int:
    dest.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as zf:
        if not src.exists():
            return 0
        for p in src.rglob("*"):
            if not p.is_file():
                continue
            rel = p.relative_to(src)
            if only and only not in str(rel) and not str(rel).startswith(only):
                continue
            zf.write(p, rel.as_posix())
            n += 1
    return n


def export(root: Optional[Path] = None) -> Dict[str, Any]:
    base = Path(root) if root else Path(".")
    game = base / "game"
    out = base / "game" / "export"
    out.mkdir(parents=True, exist_ok=True)
    godot_n = _zip_dir(game, out / "godot.zip")
    data_n = _zip_dir(game / "data", out / "data.zip")
    web_dir = out / "web"
    web_dir.mkdir(parents=True, exist_ok=True)
    (web_dir / "index.html").write_text(
        "<!doctype html><meta charset=utf-8><title>Skeleton slice</title>"
        "<p>Data-first web stub. Load data/spec.json.</p>\n",
        encoding="utf-8",
    )
    if (game / "data").exists():
        for p in (game / "data").rglob("*"):
            if p.is_file():
                dest = web_dir / "data" / p.relative_to(game / "data")
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(p.read_bytes())
    web_n = _zip_dir(web_dir, out / "web.zip")
    return {
        "kind": "export",
        "godot": str(out / "godot.zip"),
        "godot_n": godot_n,
        "data": str(out / "data.zip"),
        "data_n": data_n,
        "web": str(out / "web.zip"),
        "web_n": web_n,
        "stored_prose": 0,
    }


def health_mobile() -> Dict[str, Any]:
    from skeleton.kernel.bank import reset, boot
    reset()
    card = boot("mobile")
    names = card.get("names") or []
    need = ("looped", "socialk", "obscure", "orch")
    ok = all(n in names for n in need)
    return {
        "kind": "health-mobile",
        "ok": int(ok),
        "n": card.get("n"),
        "profile": "mobile",
        "need": list(need),
        "stored_prose": 0,
    }


def ship(org=None, *, spec: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    root = Path(getattr(org, "root", None) or ".")
    spec = spec or {}
    if not spec:
        p = root / "game" / "data" / "spec.json"
        if p.is_file():
            try:
                spec = json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                spec = {}
    meta = store_meta(spec)
    meta_path = root / "game" / "data" / "store.json"
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    ex = export(root)
    hz = health_mobile()
    return {
        "kind": "ship",
        "store": str(meta_path),
        "export": ex,
        "health": hz,
        "ok": int(bool(ex.get("godot_n")) and hz.get("ok")),
        "stored_prose": 0,
    }
