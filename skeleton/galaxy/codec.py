"""Knowledge codec — tier every topic and its depth.

CODE (capture→organize→distill→express) plus PARA actionability plus
Zettel links, recast as house tiers T0–T5. Long-form conversation is
not a transcript dump: it is a stack of atoms at increasing depth
with round-trip recoverability of commitments.

Rendering is ASCII-first compact (house CCL): 
  T<n>|<kind>|<topic>|<conf>|<cite?>
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Tuple

from skeleton.galaxy.atoms import TIERS, TIER_DEPTH, Atom, house_dialect, jaccard, token_set
from skeleton.galaxy.hoag import color_of


TIER_BUDGET = {
    "T0_FLASH": 240,
    "T1_SESSION": 180,
    "T2_EPISODE": 120,
    "T3_SEMANTIC": 80,
    "T4_PRINCIPLE": 40,
    "T5_INDEX": 24,
}


def pick_tier(kind: str, depth_hint: Optional[int] = None) -> str:
    if depth_hint is not None:
        depth_hint = max(0, min(5, int(depth_hint)))
        for name, d in TIER_DEPTH.items():
            if d == depth_hint:
                return name
    mapping = {
        "capture": "T0_FLASH",
        "commitment": "T1_SESSION",
        "episode": "T2_EPISODE",
        "zettel": "T3_SEMANTIC",
        "dream": "T2_EPISODE",
        "principle": "T4_PRINCIPLE",
        "index": "T5_INDEX",
        "citation": "T5_INDEX",
        "route": "T5_INDEX",
    }
    return mapping.get(kind, "T3_SEMANTIC")


def render_ccl(atom: Atom) -> str:
    cite = atom.citation[:48] if atom.citation else "-"
    return f"{atom.tier[1]}|{atom.kind}|{atom.topic[:40]}|{atom.confidence:.2f}|{cite}"


def parse_ccl(line: str) -> Dict[str, str]:
    parts = (line or "").split("|")
    while len(parts) < 5:
        parts.append("")
    return {
        "tier_digit": parts[0],
        "kind": parts[1],
        "topic": parts[2],
        "confidence": parts[3],
        "citation": parts[4],
    }


class KnowledgeCodec:
    """Encode stimuli into tiered atoms; measure commitment density."""

    def encode(
        self,
        stimulus: str,
        *,
        kind: str = "capture",
        brain: str = "memory",
        citation: str = "",
        url: str = "",
        depth_hint: Optional[int] = None,
        tags: Tuple[str, ...] = (),
    ) -> Atom:
        tier = pick_tier(kind, depth_hint)
        dialect = house_dialect(stimulus)
        topic = " ".join(token_set(stimulus)[:6]) or "untitled"
        return Atom.mint(
            kind=kind,
            tier=tier,
            topic=topic,
            dialect=dialect,
            brain=brain,
            color=color_of(brain),
            citation=citation,
            url=url,
            tags=tags,
            confidence=0.62 if kind == "capture" else 0.78,
        )

    def mix(self, stimulus: str, *, citation: str = "") -> List[Atom]:
        """F-6 — one stimulus at three depths: flash, episode, principle."""
        return [
            self.encode(stimulus, kind="capture", brain="memory", citation=citation, depth_hint=0),
            self.encode(stimulus, kind="episode", brain="compiler", citation=citation, depth_hint=2),
            self.encode(stimulus, kind="principle", brain="distiller", citation=citation, depth_hint=4),
        ]

    def encode_conversation(self, turns: Iterable[str], *, citation: str = "") -> List[Atom]:
        atoms: List[Atom] = []
        buf: List[str] = []
        for i, turn in enumerate(turns):
            flash = self.encode(turn, kind="capture", brain="memory", citation=citation)
            atoms.append(flash)
            buf.append(flash.dialect)
            if (i + 1) % 3 == 0:
                session = self.encode(
                    " ".join(buf[-3:]),
                    kind="commitment",
                    brain="compiler",
                    citation=citation,
                    depth_hint=1,
                )
                atoms.append(session)
        if len(buf) >= 4:
            atoms.append(self.encode(
                " ".join(buf),
                kind="episode",
                brain="dream",
                citation=citation,
                depth_hint=2,
            ))
        return atoms

    def density(self, atoms: List[Atom]) -> Dict[str, Any]:
        if not atoms:
            return {"count": 0, "commitment_density": 0.0, "mean_depth": 0.0, "stored_prose": 0}
        depths = [a.depth for a in atoms]
        principles = sum(1 for a in atoms if a.kind == "principle")
        return {
            "count": len(atoms),
            "commitment_density": round(principles / max(1, len(atoms)), 4),
            "mean_depth": round(sum(depths) / len(depths), 4),
            "by_tier": {t: sum(1 for a in atoms if a.tier == t) for t in TIERS},
            "stored_prose": 0,
        }

    def structure_longform(self, atoms: List[Atom]) -> Dict[str, Any]:
        """Outline a long-form conversation from tiered atoms."""
        layers: Dict[str, List[str]] = {t: [] for t in TIERS}
        for a in atoms:
            layers[a.tier].append(a.topic)
        spine = layers["T4_PRINCIPLE"] or layers["T3_SEMANTIC"] or layers["T1_SESSION"]
        return {
            "spine": spine[:12],
            "flash": layers["T0_FLASH"][:16],
            "sessions": layers["T1_SESSION"][:8],
            "episodes": layers["T2_EPISODE"][:8],
            "principles": layers["T4_PRINCIPLE"][:8],
            "index": layers["T5_INDEX"][:8],
            "turns": sum(1 for a in atoms if a.kind == "capture"),
            "stored_prose": 0,
        }
