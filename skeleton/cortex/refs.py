"""Game references as tools Jeeves actually uses.

Lookup is local and instant. Live parse is opt-in and polite.
Provenance is an append-only log of pointer hashes — never page text.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from skeleton.cortex.acquire_repo import SPREE, acquired_dir, parse_ref, reference_of
from skeleton.cortex.laws import check
from skeleton.cortex.port import Thought


def _norm(s: str) -> str:
    return " ".join((s or "").lower().split())


def index() -> List[Dict[str, Any]]:
    return [reference_of(g) for g in SPREE]


def match(stimulus: str) -> List[Dict[str, Any]]:
    text = _norm(stimulus)
    hits = []
    for ref in index():
        title = _norm(str(ref.get("title") or ""))
        if title and title in text:
            hits.append(ref)
            continue
        toks = [t for t in title.split() if len(t) > 3]
        if toks and all(t in text for t in toks):
            hits.append(ref)
    return hits


def lookup(stimulus: str) -> Optional[Dict[str, Any]]:
    hits = match(stimulus)
    return hits[0] if hits else None


def provenance_path(root: Optional[Path] = None) -> Path:
    return acquired_dir(root) / "gaming" / "provenance.jsonl"


def record_provenance(ref: Dict[str, Any], *, action: str, root: Optional[Path] = None) -> Dict[str, Any]:
    pointer = {
        "action": action,
        "appid": ref.get("appid"),
        "title": ref.get("title"),
        "url": ref.get("url"),
        "license": ref.get("license"),
        "dialect": (ref.get("dialect") or "")[:160],
        "stored_prose": 0,
    }
    check(pointer)
    blob = json.dumps(pointer, sort_keys=True, default=str)
    pointer["sha256"] = hashlib.sha256(blob.encode("utf-8")).hexdigest()
    path = provenance_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(pointer, sort_keys=True) + "\n")
    return pointer


def refer(stimulus: str, *, live: bool = False) -> Dict[str, Any]:
    ref = lookup(stimulus)
    if ref is None:
        return {"hit": 0, "reason": "no-reference"}
    if live:
        parsed = parse_ref(int(ref["appid"]), title=str(ref["title"]), era=str(ref.get("era") or ""))
        if parsed.get("parsed"):
            ref = {**ref, **{k: parsed[k] for k in ("dialect", "title", "genres") if k in parsed}}
    log = record_provenance(ref, action="live" if live else "lookup")
    return {"hit": 1, "ref": ref, "provenance": log, "live": int(live)}


class GameRefPort:
    """ModelPort. Speaks house dialect for a matched title. Never a blurb."""

    def __init__(self, slot: str = "right", *, name: str = "gameref") -> None:
        self.slot = slot
        self.name = name
        self.scale = "tool"

    def think(self, stimulus: str, context: Dict[str, Any]) -> Thought:
        out = refer(stimulus, live=bool((context or {}).get("live")))
        if not out.get("hit"):
            return Thought(slot=self.slot, kind="ref-miss", text="", confidence=0.2,
                           tags=("ref", "miss", self.slot))
        dialect = str((out["ref"] or {}).get("dialect") or "")
        return Thought(
            slot=self.slot, kind="ref",
            text=dialect[:400],
            confidence=0.91,
            tags=("ref", "tool", self.slot, str((out["ref"] or {}).get("era") or "era")),
        )

    def fit(self, text: str) -> int:
        return 0

    def decode(self, stimulus: str, *, n: int = 8, seed: int = 0) -> str:
        return self.think(stimulus or "", {}).text

    def snapshot(self) -> Dict[str, Any]:
        return {"kind": "gameref", "slot": self.slot, "name": self.name}

    @classmethod
    def from_snapshot(cls, data: Dict[str, Any], *, slot: str | None = None) -> "GameRefPort":
        return cls(slot=slot or str((data or {}).get("slot") or "right"))

    def perplexity(self, texts) -> float:
        return 1.0
