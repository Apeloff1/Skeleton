"""Field walk — bind unbound SOTA pointers under a hardware cap.

Day and pulse rotate both call claim(). Duplicate topics are refused.
Bodies stay off-shelf. Only citation handles land on editor+wiki.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

CAP = {"tight": 1, "mobile": 2, "desktop": 4, "small": 2, "workstation": 4}


def _profile() -> str:
    try:
        from skeleton.kernel.profiles import card as profiles_card
        return str(profiles_card().get("profile") or "mobile")
    except Exception:
        return "mobile"


def cap(profile: Optional[str] = None) -> int:
    return int(CAP.get(profile or _profile(), 2))


def seen(root=None) -> set:
    from skeleton.organism.runloop import bound_path
    import json
    p = bound_path(root)
    out = set()
    if not p.is_file():
        return out
    for line in p.read_text(encoding="utf-8").splitlines():
        try:
            out.add(str(json.loads(line).get("topic") or ""))
        except Exception:
            continue
    out.discard("")
    return out


def unbound(root=None) -> List[Dict[str, str]]:
    from skeleton.social.sources import SOTA_POINTERS
    have = seen(root)
    return [dict(r) for r in SOTA_POINTERS if r.get("topic") not in have]


HOUSE_ORDER = ("Xarchive", "Internet Archive", "X", "GitHub", "arXiv")


def take(root=None, k: int = 2) -> List[Dict[str, str]]:
    """House-round-robin so arXiv cannot starve archive/github."""
    from collections import defaultdict, deque
    buckets: Dict[str, Any] = defaultdict(deque)
    for row in unbound(root):
        buckets[str(row.get("house") or "web")].append(row)
    order = [h for h in HOUSE_ORDER if h in buckets] + [h for h in buckets if h not in HOUSE_ORDER]
    out: List[Dict[str, str]] = []
    while len(out) < k and any(buckets[h] for h in order):
        for h in order:
            if len(out) >= k:
                break
            if buckets[h]:
                out.append(buckets[h].popleft())
    return out


def claim(org, row: Dict[str, str], *, root=None) -> Dict[str, Any]:
    from skeleton.organism.runloop import bind_row, advance
    topic = str(row.get("topic") or "")
    if not topic or topic in seen(root):
        return {"ok": 0, "why": "seen", "topic": topic, "stored_prose": 0}
    bind_row(row, root=root)
    advance(root)
    cdx = ""
    xarchive = ""
    try:
        from skeleton.social.archivex import pointer, wayback_cdx_url
        ptr = pointer(str(row.get("url") or ""))
        cdx = str(ptr.get("cdx") or wayback_cdx_url(str(row.get("url") or "")))
        xarchive = str(ptr.get("xarchive") or "")
    except Exception:
        cdx = ""
        xarchive = ""
    try:
        atom = org.galaxy.codec.encode(
            topic, kind="citation", brain="editor",
            citation=str(row.get("url") or ""), url=str(row.get("url") or ""),
            depth_hint=5, tags=("social", str(row.get("house") or "web"), "cdx"),
        )
        org.galaxy.mesh.publish(atom)
        org.galaxy.editor.index_topic(atom)
    except Exception:
        pass
    try:
        from skeleton.organism.follow import grow
        grow(topic + " " + str(row.get("url") or ""), root=root)
    except Exception:
        pass
    return {
        "ok": 1,
        "topic": topic,
        "house": row.get("house"),
        "url": row.get("url"),
        "cdx": cdx,
        "xarchive": xarchive,
        "stored_prose": 0,
    }


def walk(org=None, *, n: int = 0, root=None) -> Dict[str, Any]:
    from skeleton.organism.organismer import live_organismer
    org = org or live_organismer()
    root = root if root is not None else getattr(org, "root", None)
    profile = _profile()
    asked = int(n or 0)
    k = max(1, min(4, asked if asked else cap(profile)))
    took = take(root, k)
    bound = [claim(org, row, root=root) for row in took]
    from skeleton.organism.runloop import bound_card
    inventory = bound_card(root)
    return {
        "kind": "field-walk",
        "profile": profile,
        "asked": k,
        "ok": sum(1 for b in bound if b.get("ok")),
        "topics": [b.get("topic") for b in bound if b.get("ok")],
        "houses": [b.get("house") for b in bound if b.get("ok")],
        "bound": bound,
        "inventory": inventory,
        "stored_prose": 0,
    }
