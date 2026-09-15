"""Typed knowledge atoms — commitments, not blobs.

Context is a set of commitments (goals, constraints, decisions,
preferences, evidence, safety). An Atom is the house unit: canonical
id, kind, depth tier, provenance pointer, house dialect only.
stored_prose is always 0. Third-party text stays a citation URL.
"""
from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

KINDS: Tuple[str, ...] = (
    "capture",
    "zettel",
    "episode",
    "dream",
    "principle",
    "index",
    "commitment",
    "citation",
    "route",
)

TIERS: Tuple[str, ...] = (
    "T0_FLASH",
    "T1_SESSION",
    "T2_EPISODE",
    "T3_SEMANTIC",
    "T4_PRINCIPLE",
    "T5_INDEX",
)

TIER_DEPTH: Dict[str, int] = {
    "T0_FLASH": 0,
    "T1_SESSION": 1,
    "T2_EPISODE": 2,
    "T3_SEMANTIC": 3,
    "T4_PRINCIPLE": 4,
    "T5_INDEX": 5,
}


def atom_id(*parts: str) -> str:
    raw = "|".join(str(p) for p in parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]


def token_set(text: str) -> Tuple[str, ...]:
    return tuple(t for t in "".join(
        ch.lower() if ch.isalnum() else " " for ch in (text or "")
    ).split() if t)


def jaccard(a: Tuple[str, ...], b: Tuple[str, ...]) -> float:
    sa, sb = set(a), set(b)
    if not sa and not sb:
        return 1.0
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


@dataclass
class Atom:
    id: str
    kind: str
    tier: str
    topic: str
    dialect: str
    brain: str
    color: str
    citation: str = ""
    url: str = ""
    parent: str = ""
    links: Tuple[str, ...] = ()
    tags: Tuple[str, ...] = ()
    confidence: float = 0.7
    risk: float = 0.0
    tokens: Tuple[str, ...] = ()
    stored_prose: int = 0
    superseded_by: str = ""
    ts: float = field(default_factory=time.time)

    def __post_init__(self) -> None:
        if self.kind not in KINDS:
            raise ValueError(f"unknown atom kind: {self.kind}")
        if self.tier not in TIER_DEPTH:
            raise ValueError(f"unknown tier: {self.tier}")
        if self.stored_prose != 0:
            self.stored_prose = 0
        if not self.tokens:
            self.tokens = token_set(f"{self.topic} {self.dialect}")

    @property
    def depth(self) -> int:
        return TIER_DEPTH[self.tier]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "tier": self.tier,
            "depth": self.depth,
            "topic": self.topic,
            "dialect": self.dialect,
            "brain": self.brain,
            "color": self.color,
            "citation": self.citation,
            "url": self.url,
            "parent": self.parent,
            "links": list(self.links),
            "tags": list(self.tags),
            "confidence": round(float(self.confidence), 4),
            "risk": round(float(self.risk), 4),
            "stored_prose": 0,
            "superseded_by": self.superseded_by,
            "ts": self.ts,
        }

    @classmethod
    def mint(
        cls,
        *,
        kind: str,
        tier: str,
        topic: str,
        dialect: str,
        brain: str,
        color: str,
        citation: str = "",
        url: str = "",
        parent: str = "",
        links: Tuple[str, ...] = (),
        tags: Tuple[str, ...] = (),
        confidence: float = 0.7,
        risk: float = 0.0,
    ) -> "Atom":
        aid = atom_id(kind, tier, topic, dialect, brain)
        return cls(
            id=aid, kind=kind, tier=tier, topic=topic, dialect=dialect,
            brain=brain, color=color, citation=citation, url=url,
            parent=parent, links=links, tags=tags,
            confidence=confidence, risk=risk,
        )

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Atom":
        tags = tuple(data.get("tags") or ())
        links = tuple(data.get("links") or ())
        atom = cls(
            id=str(data.get("id") or atom_id("restore")),
            kind=str(data.get("kind") or "capture"),
            tier=str(data.get("tier") or "T0_FLASH"),
            topic=str(data.get("topic") or "")[:160],
            dialect=str(data.get("dialect") or "")[:160],
            brain=str(data.get("brain") or "memory"),
            color=str(data.get("color") or ""),
            citation=str(data.get("citation") or "")[:240],
            url=str(data.get("url") or "")[:240],
            parent=str(data.get("parent") or ""),
            links=links,
            tags=tags,
            confidence=float(data.get("confidence") or 0.7),
            risk=float(data.get("risk") or 0.0),
            stored_prose=0,
            superseded_by=str(data.get("superseded_by") or ""),
            ts=float(data.get("ts") or time.time()),
        )
        return atom


def house_dialect(stimulus: str) -> str:
    """House paraphrase — pointers + structure, never source prose."""
    toks = token_set(stimulus)
    if not toks:
        return "empty-capture"
    head = " ".join(toks[:12])
    return f"house:{head}"
