"""Cue-tag reconstruction forest.

House mapping of "memory is reconstructed, not retrieved":
atoms are Content, tokens are Tags, query tokens are Cues.
Edges exist when two atoms share a tag. Reconstruct expands one
hop from cue seeds under a live query budget.

Cite https://arxiv.org/abs/2606.06036 as the stance. No paper graph
format, no bodies on edges.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, Iterable, List, Set, Tuple

from skeleton.galaxy.atoms import jaccard, token_set

CITE = "https://arxiv.org/abs/2606.06036"


def _atoms(mesh) -> List[Any]:
    seen: Dict[str, Any] = {}
    for lib in list((mesh.brains or {}).values()) + [mesh.wiki]:
        shelf = getattr(lib, "shelf", {}) or {}
        items = shelf.values() if isinstance(shelf, dict) else getattr(lib, "all", lambda: [])()
        for atom in items:
            if getattr(atom, "id", None) and not getattr(atom, "superseded_by", ""):
                seen[atom.id] = atom
    return list(seen.values())


def index_tags(atoms: Iterable[Any]) -> Dict[str, List[str]]:
    tags: Dict[str, List[str]] = defaultdict(list)
    for atom in atoms:
        for tok in getattr(atom, "tokens", ()) or ():
            tags[str(tok)].append(atom.id)
    return dict(tags)


def edges_of(atoms: Iterable[Any], *, min_j: float = 0.12) -> List[Tuple[str, str, float]]:
    rows = list(atoms)
    out: List[Tuple[str, str, float]] = []
    by_tag = index_tags(rows)
    seen: Set[Tuple[str, str]] = set()
    lookup = {a.id: a for a in rows}
    for ids in by_tag.values():
        uniq = list(dict.fromkeys(ids))
        for i, a in enumerate(uniq):
            for b in uniq[i + 1 :]:
                pair = (a, b) if a < b else (b, a)
                if pair in seen:
                    continue
                seen.add(pair)
                w = jaccard(lookup[a].tokens, lookup[b].tokens)
                if w >= min_j:
                    out.append((pair[0], pair[1], round(w, 4)))
    return out


def reconstruct(mesh, cue: str, *, k: int = 0) -> Dict[str, Any]:
    if k <= 0:
        try:
            from skeleton.organism.caps import live as live_caps
            k = int(live_caps().query)
        except Exception:
            k = 12
    k = max(2, min(24, int(k)))
    atoms = _atoms(mesh)
    q = token_set(cue)
    seeds = sorted(
        ((jaccard(q, a.tokens), a) for a in atoms),
        key=lambda p: p[0],
        reverse=True,
    )
    seeds = [a for s, a in seeds if s > 0][: max(2, k // 2)]
    seed_ids = {a.id for a in seeds}
    ed = edges_of(atoms)
    nbrs: Dict[str, List[Tuple[str, float]]] = defaultdict(list)
    for a, b, w in ed:
        nbrs[a].append((b, w))
        nbrs[b].append((a, w))
    forest_ids: Set[str] = set(seed_ids)
    forest_e: List[Tuple[str, str, float]] = []
    for sid in list(seed_ids):
        for nid, w in sorted(nbrs.get(sid, []), key=lambda p: -p[1])[:3]:
            if nid not in forest_ids and len(forest_ids) < k:
                forest_ids.add(nid)
                forest_e.append((sid, nid, w))
    lookup = {a.id: a for a in atoms}
    nodes = [
        {
            "id": aid,
            "topic": getattr(lookup[aid], "topic", ""),
            "brain": getattr(lookup[aid], "brain", ""),
            "kind": getattr(lookup[aid], "kind", ""),
            "citation": getattr(lookup[aid], "citation", ""),
            "seed": int(aid in seed_ids),
        }
        for aid in forest_ids
        if aid in lookup
    ]
    return {
        "kind": "reconstruct",
        "cue": (cue or "")[:160],
        "n": len(nodes),
        "e": len(forest_e),
        "nodes": nodes,
        "edges": [{"a": a, "b": b, "w": w} for a, b, w in forest_e],
        "cite": CITE,
        "stored_prose": 0,
    }


def card(mesh, cue: str = "") -> Dict[str, Any]:
    atoms = _atoms(mesh)
    ed = edges_of(atoms)
    rec = reconstruct(mesh, cue or "memory graph")
    return {
        "kind": "graph",
        "atoms": len(atoms),
        "edges": len(ed),
        "reconstruct": rec,
        "cite": CITE,
        "stored_prose": 0,
    }
