"""SPARQL-shaped wiki query — a tiny dialect, not a SPARQL engine.

Forms:
  SELECT topic WHERE brain=memory
  SELECT * WHERE tier=T4_PRINCIPLE
  SELECT topic WHERE contains=elden
  SELECT * WHERE kind=principle

Unknown clauses are ignored. Results are topic/citation handles.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List

from skeleton.galaxy.atoms import token_set

_SELECT = re.compile(r"^\s*select\s+(\*|topic|id)\s+where\s+(.+)$", re.I)
_CLAUSE = re.compile(r"(brain|tier|kind|contains)\s*=\s*([^\s]+)", re.I)


def parse(q: str) -> Dict[str, str]:
    raw = (q or "").strip()
    m = _SELECT.match(raw)
    if not m:
        return {"proj": "topic", "contains": raw.lower()} if raw else {}
    proj = m.group(1).lower()
    out: Dict[str, str] = {"proj": "id" if proj == "id" else "topic"}
    if proj == "*":
        out["proj"] = "*"
    for key, val in _CLAUSE.findall(m.group(2)):
        out[key.lower()] = val.strip().strip("'\"")
    return out


def run(mesh, q: str, *, limit: int = 0) -> Dict[str, Any]:
    if limit <= 0:
        try:
            from skeleton.organism.caps import live as live_caps
            limit = int(live_caps().query)
        except Exception:
            limit = 24
    spec = parse(q)
    try:
        from skeleton.retrieval.query_language import QueryParser
        extra = []
        for term in QueryParser.parse(q or ""):
            if term.negated:
                continue
            extra.append(term.raw)
        if extra and not spec.get("contains"):
            spec["contains"] = " ".join(extra)[:80]
    except Exception:
        pass
    rows: List[Dict[str, Any]] = []
    seen = set()
    libs = list(mesh.brains.values()) + [mesh.wiki]
    needle = token_set(spec.get("contains") or "")
    for lib in libs:
        for atom in lib.all():
            if atom.id in seen or atom.superseded_by:
                continue
            if spec.get("brain") and atom.brain != spec["brain"]:
                continue
            if spec.get("tier") and atom.tier != spec["tier"]:
                continue
            if spec.get("kind") and atom.kind != spec["kind"]:
                continue
            if needle and not (set(needle) & set(atom.tokens)):
                continue
            seen.add(atom.id)
            if spec.get("proj") == "id":
                rows.append({"id": atom.id})
            elif spec.get("proj") == "*":
                rows.append({"id": atom.id, "topic": atom.topic, "brain": atom.brain,
                             "tier": atom.tier, "kind": atom.kind, "citation": atom.citation})
            else:
                rows.append({"topic": atom.topic, "citation": atom.citation, "brain": atom.brain})
            if len(rows) >= limit:
                break
        if len(rows) >= limit:
            break
    forest = None
    needle_q = spec.get("contains") or q
    if needle_q:
        try:
            from skeleton.galaxy.graph import reconstruct
            forest = reconstruct(mesh, needle_q, k=min(8, limit))
        except Exception:
            forest = None
    return {
        "kind": "wiki-query",
        "q": q[:160],
        "spec": spec,
        "n": len(rows),
        "rows": rows,
        "forest": forest,
        "stored_prose": 0,
    }
