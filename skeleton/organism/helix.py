"""Dual-helix eidetic chain.

Sense strand  — event hashes (writes, decisions, field topics).
Snap strand   — mesh merkle + compact atom cards (backup eidetic).

Each block stores prev on its own strand and pair on the other.
Recall searches both. Verify walks both. No article bodies.
"""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from skeleton.cortex.laws import check
from skeleton.galaxy.atoms import token_set
from skeleton.organism.paths import helix_sense_path, helix_snap_path

SNAP_ATOMS = 48
GENESIS = "0" * 64


def _sha(blob: str) -> str:
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _read_last(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    last = ""
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                last = line
    if not last:
        return {}
    try:
        return json.loads(last)
    except json.JSONDecodeError:
        return {}


def _height(path: Path) -> int:
    if not path.exists():
        return 0
    n = 0
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                n += 1
    return n


def head_sense(root: Optional[Path] = None) -> str:
    return str(_read_last(helix_sense_path(root)).get("sha") or GENESIS)


def head_snap(root: Optional[Path] = None) -> str:
    return str(_read_last(helix_snap_path(root)).get("sha") or GENESIS)


def mesh_merkle(mesh) -> str:
    ids: List[str] = []
    for lib in (*(mesh.brains or {}).values(), getattr(mesh, "wiki", None)):
        if lib is None:
            continue
        for atom in lib.all():
            ids.append(str(atom.id))
    ids.sort()
    topics = sorted((mesh.wiki.topics or {}).keys())
    return _sha("|".join(ids) + "#" + "|".join(topics))


def _compact_atoms(mesh, *, k: int = SNAP_ATOMS) -> List[Dict[str, Any]]:
    seen: Dict[str, Any] = {}
    for lib in (*(mesh.brains or {}).values(), getattr(mesh, "wiki", None)):
        if lib is None:
            continue
        for atom in lib.all():
            seen[atom.id] = atom
    ranked = sorted(seen.values(), key=lambda a: float(getattr(a, "ts", 0) or 0))[-k:]
    return [a.to_dict() for a in ranked]


def _stamp(payload: Dict[str, Any], path: Path) -> Dict[str, Any]:
    payload = check(payload)
    blob = json.dumps(payload, sort_keys=True, default=str)
    payload["sha"] = _sha(blob)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, sort_keys=True, default=str) + "\n")
    return payload


def sense(event: Dict[str, Any], *, root: Optional[Path] = None) -> Dict[str, Any]:
    path = helix_sense_path(root)
    return _stamp({
        "strand": "sense",
        "height": _height(path),
        "at": int(time.time() * 1000),
        "kind": event.get("kind") or "sense",
        "decision": str(event.get("decision") or "")[:80],
        "topic": str(event.get("topic") or "")[:120],
        "url": str(event.get("url") or "")[:240],
        "G": event.get("G"),
        "atoms": str(event.get("atoms") or "")[:160],
        "prev": head_sense(root),
        "pair": head_snap(root),
        "stored_prose": 0,
    }, path)


def snap(org, *, root: Optional[Path] = None) -> Dict[str, Any]:
    root = root if root is not None else getattr(org, "root", None)
    mesh = org.galaxy.mesh
    path = helix_snap_path(root)
    atoms = _compact_atoms(mesh)
    return _stamp({
        "strand": "snap",
        "height": _height(path),
        "at": int(time.time() * 1000),
        "kind": "eidetic",
        "merkle": mesh_merkle(mesh),
        "G": getattr(org, "G", None),
        "atoms_n": sum(len(lib.shelf) for lib in mesh.brains.values()),
        "wiki_n": len(mesh.wiki.topics or {}),
        "atoms": atoms,
        "topics": dict(mesh.wiki.topics or {}),
        "prev": head_snap(root),
        "pair": head_sense(root),
        "stored_prose": 0,
    }, path)


def stamp(org, event: Dict[str, Any], *, root: Optional[Path] = None) -> Dict[str, Any]:
    """Write both strands — sense event then eidetic snap."""
    root = root if root is not None else getattr(org, "root", None)
    s = sense(event, root=root)
    p = snap(org, root=root)
    return {
        "kind": "helix",
        "sense": {"sha": s["sha"], "height": s["height"], "pair": s["pair"]},
        "snap": {"sha": p["sha"], "height": p["height"], "merkle": p["merkle"], "pair": p["pair"]},
        "stored_prose": 0,
    }


def _walk(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    out: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def verify(root: Optional[Path] = None) -> Dict[str, Any]:
    def _chain(rows: List[Dict[str, Any]], strand: str) -> Dict[str, Any]:
        prev = GENESIS
        bad = 0
        for i, row in enumerate(rows):
            if str(row.get("prev") or GENESIS) != prev:
                bad += 1
            body = {k: v for k, v in row.items() if k != "sha"}
            expect = _sha(json.dumps(body, sort_keys=True, default=str))
            if str(row.get("sha") or "") != expect:
                bad += 1
            if str(row.get("strand") or "") != strand:
                bad += 1
            prev = str(row.get("sha") or prev)
        return {"n": len(rows), "bad": bad, "head": prev if rows else GENESIS}

    sense_rows = _walk(helix_sense_path(root))
    snap_rows = _walk(helix_snap_path(root))
    sc = _chain(sense_rows, "sense")
    pc = _chain(snap_rows, "snap")
    ok = int(sc["bad"] == 0 and pc["bad"] == 0)
    return {
        "kind": "helix-verify",
        "ok": ok,
        "sense": sc,
        "snap": pc,
        "stored_prose": 0,
    }


def recall(cue: str, *, root: Optional[Path] = None, k: int = 8) -> Dict[str, Any]:
    src = set(token_set(cue or ""))
    hits: List[Dict[str, Any]] = []
    for row in reversed(_walk(helix_snap_path(root))):
        blob = " ".join(str(t) for t in (row.get("topics") or {}).keys())
        for atom in row.get("atoms") or []:
            blob += " " + str(atom.get("topic") or "") + " " + str(atom.get("dialect") or "")
        tok = set(token_set(blob))
        score = (len(src & tok) / len(src | tok)) if src and tok else 0.0
        if score >= 0.08 or (cue and cue[:40] in blob):
            hits.append({
                "strand": "snap",
                "height": row.get("height"),
                "sha": row.get("sha"),
                "merkle": row.get("merkle"),
                "score": round(score, 4),
                "atoms_n": row.get("atoms_n"),
            })
        if len(hits) >= k:
            break
    for row in reversed(_walk(helix_sense_path(root))):
        topic = str(row.get("topic") or "")
        tok = set(token_set(topic + " " + str(row.get("url") or "")))
        score = (len(src & tok) / len(src | tok)) if src and tok else 0.0
        if score >= 0.12 or (cue and cue[:40] in topic):
            hits.append({
                "strand": "sense",
                "height": row.get("height"),
                "sha": row.get("sha"),
                "topic": topic[:80],
                "score": round(score, 4),
            })
        if len([h for h in hits if h["strand"] == "sense"]) >= k:
            break
    hits.sort(key=lambda h: float(h.get("score") or 0), reverse=True)
    return {
        "kind": "helix-recall",
        "cue": (cue or "")[:80],
        "n": len(hits),
        "hits": hits[:k],
        "stored_prose": 0,
    }


def card(root: Optional[Path] = None) -> Dict[str, Any]:
    v = verify(root)
    return {
        "kind": "helix",
        "sense_head": head_sense(root),
        "snap_head": head_snap(root),
        "sense_n": v["sense"]["n"],
        "snap_n": v["snap"]["n"],
        "ok": v["ok"],
        "stored_prose": 0,
    }
