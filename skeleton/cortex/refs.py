"""Game references as tools Jeeves actually uses.

Lookup is local and instant. Live parse is opt-in and polite.
Provenance is an append-only log of pointer hashes — never page text.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from skeleton.cortex.acquire_repo import SPREE, parse_ref, reference_of
from skeleton.cortex.port import Thought
from skeleton.cortex.reference_provenance import (
    ReferenceProvenanceError,
    append_reference,
    read_reference_log,
    reference_scope,
    runtime_provenance_path,
)

__all__ = [
    "GameRefPort", "ReferenceProvenanceError", "index", "lookup", "match",
    "provenance_path", "read_provenance", "record_provenance", "refer", "reference_scope",
]


def _norm(s: str) -> str:
    return " ".join((s or "").lower().split())


def index() -> list[dict[str, Any]]:
    return [reference_of(g) for g in SPREE]


def match(stimulus: str) -> list[dict[str, Any]]:
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


def lookup(stimulus: str) -> dict[str, Any] | None:
    hits = match(stimulus)
    return hits[0] if hits else None


def provenance_path(root: Path | None = None) -> Path:
    return runtime_provenance_path(root)


def record_provenance(ref: dict[str, Any], *, action: str, root: Path | None = None) -> dict[str, Any]:
    return append_reference(provenance_path(root), ref, action=action)


def read_provenance(root: Path | None = None, *, max_records: int = 10_000) -> list[dict[str, Any]]:
    return read_reference_log(provenance_path(root), max_records=max_records)


def refer(stimulus: str, *, live: bool = False, root: Path | None = None) -> dict[str, Any]:
    ref = lookup(stimulus)
    if ref is None:
        return {"hit": 0, "reason": "no-reference"}
    if live:
        parsed = parse_ref(int(ref["appid"]), title=str(ref["title"]), era=str(ref.get("era") or ""))
        if parsed.get("parsed"):
            ref = {**ref, **{k: parsed[k] for k in ("dialect", "title", "genres") if k in parsed}}
    log = record_provenance(ref, action="live" if live else "lookup", root=root)
    return {"hit": 1, "ref": ref, "provenance": log, "live": int(live)}


class GameRefPort:
    """ModelPort. Speaks house dialect for a matched title. Never a blurb."""

    def __init__(self, slot: str = "right", *, name: str = "gameref", root: Path | None = None) -> None:
        self.slot = slot
        self.name = name
        self.scale = "tool"
        self.root = Path(root).resolve() if root is not None else None

    def think(self, stimulus: str, context: dict[str, Any]) -> Thought:
        out = refer(stimulus, live=bool((context or {}).get("live")), root=self.root)
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

    def snapshot(self) -> dict[str, Any]:
        return {"kind": "gameref", "slot": self.slot, "name": self.name}

    @classmethod
    def from_snapshot(cls, data: dict[str, Any], *, slot: str | None = None, root: Path | None = None) -> GameRefPort:
        return cls(slot=slot or str((data or {}).get("slot") or "right"),
                   name=str((data or {}).get("name") or "gameref"), root=root)

    def perplexity(self, texts) -> float:
        return 1.0
