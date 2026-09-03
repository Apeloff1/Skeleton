"""Bounded pulse walk. Stops on hold/tighten or N steps.

N defaults to 4, hard-capped at 8. Never an unbounded write.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

STOP = {"hold", "tighten"}


def rotate_stimulus(i: int, explicit: str = "") -> str:
    if explicit:
        return explicit
    from skeleton.social.sources import SOTA_POINTERS
    row = SOTA_POINTERS[i % len(SOTA_POINTERS)]
    return f"{row['topic']} {row['url']}"


def cursor_path(root=None):
    from pathlib import Path
    base = Path(root) if root else Path(".")
    return base / "chronicle" / "rotate.json"


def cursor(root=None) -> int:
    import json
    p = cursor_path(root)
    if not p.is_file():
        return 0
    try:
        return int(json.loads(p.read_text(encoding="utf-8")).get("i") or 0)
    except Exception:
        return 0


def advance(root=None) -> int:
    import json
    i = cursor(root) + 1
    p = cursor_path(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"kind": "rotate", "i": i, "stored_prose": 0}, indent=2), encoding="utf-8")
    return i


def bound_path(root=None):
    from pathlib import Path
    base = Path(root) if root else Path(".")
    return base / "chronicle" / "bound.jsonl"


def bind_row(row: dict, *, root=None) -> dict:
    import json
    p = bound_path(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    topic = str(row.get("topic") or "")
    if topic and p.is_file():
        try:
            if topic in p.read_text(encoding="utf-8"):
                return {"kind": "bound", "topic": topic, "dup": 1, "stored_prose": 0}
        except Exception:
            pass
    cdx = str(row.get("cdx") or "")
    xarchive = str(row.get("xarchive") or "")
    if not cdx and row.get("url"):
        try:
            from skeleton.social.archivex import pointer, wayback_cdx_url
            ptr = pointer(str(row.get("url")))
            cdx = str(ptr.get("cdx") or wayback_cdx_url(str(row.get("url"))))
            xarchive = xarchive or str(ptr.get("xarchive") or "")
        except Exception:
            cdx = ""
    rec = {
        "kind": "bound",
        "topic": topic,
        "url": row.get("url"),
        "house": row.get("house"),
        "cdx": cdx,
        "xarchive": xarchive,
        "stored_prose": 0,
    }
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec) + "\n")
    return rec


def bound_card(root=None) -> dict:
    import json
    p = bound_path(root)
    rows = []
    if p.is_file():
        for line in p.read_text(encoding="utf-8").splitlines()[-48:]:
            try:
                rows.append(json.loads(line))
            except Exception:
                continue
    houses = sorted({str(r.get("house")) for r in rows if r.get("house")})
    topics = sorted({str(r.get("topic")) for r in rows if r.get("topic")})
    from skeleton.social.sources import SOTA_POINTERS
    field_n = max(1, len(SOTA_POINTERS))
    return {
        "kind": "bound",
        "n": len(rows),
        "unique": len(topics),
        "houses": houses,
        "last": (rows[-1].get("topic") if rows else ""),
        "field_pct": round(100.0 * len(topics) / field_n, 2),
        "field_n": field_n,
        "cdx_n": sum(1 for r in rows if r.get("cdx")),
        "stored_prose": 0,
    }


def walk(org=None, *, neo=None, stimulus: str = "", n: int = 4,
         persist: Optional[bool] = None) -> Dict[str, Any]:
    from skeleton.organism.organismer import live_organismer
    from skeleton.organism.pulse import pulse

    org = org or live_organismer()
    try:
        from skeleton.organism.budget import walk_limit
        from skeleton.organism.caps import live as live_caps
        limit = walk_limit(live_caps().tier, int(n or 4))
    except Exception:
        limit = max(1, min(8, int(n or 4)))
    if not (org.galaxy.mesh.wiki.topics or {}):
        from skeleton.social.seed import seed_field
        seed_field(org.galaxy)
    queue: List[str] = []
    try:
        from skeleton.organism.scope import compose
        queue = list((compose(org, neo=neo).get("queue") or []))
    except Exception:
        queue = []
    cards: List[Dict[str, Any]] = []
    used: List[str] = []
    stopped = "cap"
    for i in range(limit):
        intent = queue[i] if i < len(queue) else "pulse"
        if intent == "dump":
            from skeleton.organism.chronicle.dump import dump
            dump(getattr(org, "root", None), force=False)
            cards.append({"code": "dump", "G": round(org.G, 6)})
            used.append("dump")
            continue
        stim = rotate_stimulus(i, stimulus)
        used.append(stim.split()[0])
        card = pulse(org, neo=neo, stimulus=stim, persist=persist)
        cards.append({
            "code": (card.get("acted") or {}).get("code"),
            "G": card.get("G"),
        })
        code = str((card.get("acted") or {}).get("code") or "")
        if code in STOP:
            stopped = code
            break
    return {
        "kind": "run",
        "n": len(cards),
        "limit": limit,
        "stopped": stopped,
        "codes": [c["code"] for c in cards],
        "topics": used,
        "queue": queue,
        "G": cards[-1]["G"] if cards else round(org.G, 6),
        "stored_prose": 0,
    }
