"""Own-system — the model Jeeves builds to surpass its parts.

No weights. No tokenizer. No transformer. The own-system is a
compositional few-shot memory: every acquired tract is an exemplar
bundle. Recall is token-Jaccard (SHA fingerprints are exact-match
only; Hamming on a hash is noise). Compose stitches the nearest
left / right / pfc exemplars into one neo thought. Two cortices
interchange by exporting a Tract — Jeeves acquires the ability of
any bound backend, then answers from its own system.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Tuple

from skeleton.cortex.distill import Ability
from skeleton.cortex.port import Thought, jaccard, tokens

MIN_JACCARD = 0.40
K_RECALL = 5


@dataclass(frozen=True)
class Tract:
    """A transferable ability bundle. The unit of interchange."""

    slot: str
    backend: str
    scale: str
    capabilities: Tuple[str, ...]
    exemplars: Tuple[Ability, ...]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "slot": self.slot,
            "backend": self.backend,
            "scale": self.scale,
            "capabilities": list(self.capabilities),
            "exemplars": [e.to_dict() for e in self.exemplars],
            "size": len(self.exemplars),
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Tract":
        ex = tuple(Ability.from_dict(e) for e in (d.get("exemplars") or []))
        caps = tuple(d.get("capabilities") or ())
        return cls(
            slot=str(d.get("slot") or "neo"),
            backend=str(d.get("backend") or "unknown"),
            scale=str(d.get("scale") or "injected"),
            capabilities=caps,
            exemplars=ex,
        )


@dataclass
class RecallHit:
    jaccard: float
    ability: Ability

    def to_dict(self) -> Dict[str, Any]:
        return {
            "jaccard": round(self.jaccard, 4),
            "slot": self.ability.slot,
            "kind": self.ability.kind,
            "fp": self.ability.stimulus_fp,
            "tags": list(self.ability.tags),
        }


class OwnSystem:
    """The thing being trained. Stores tracts, recalls by Jaccard, composes."""

    def __init__(self) -> None:
        self._items: List[Ability] = []
        self._by_fp: Dict[str, List[Ability]] = {}

    def ingest(self, ability: Ability, stimulus: str = "") -> Ability:
        if not ability.tokens and stimulus:
            ability.tokens = tokens(stimulus)
        self._items.append(ability)
        self._by_fp.setdefault(ability.stimulus_fp, []).append(ability)
        return ability

    def extend(self, abilities: Iterable[Ability]) -> int:
        n = 0
        for ab in abilities:
            self.ingest(ab)
            n += 1
        return n

    def recall(self, stimulus: str, *, k: int = K_RECALL,
               min_jaccard: float = MIN_JACCARD,
               slot: Optional[str] = None) -> List[RecallHit]:
        q = tokens(stimulus)
        scored: List[RecallHit] = []
        seen: set = set()
        for ab in self._items:
            if slot and ab.slot not in {slot, "neo"} and slot not in ab.tags:
                continue
            key = (ab.slot, ab.stimulus_fp, ab.signature)
            if key in seen:
                continue
            seen.add(key)
            j = jaccard(q, ab.tokens)
            if j >= min_jaccard:
                scored.append(RecallHit(j, ab))
        def _rank(h: RecallHit):
            tags = h.ability.tags
            pri = 0 if ("acquired" in tags or "imported" in tags) else 1
            return (pri, -h.jaccard, -h.ability.confidence, -h.ability.seen)
        scored.sort(key=_rank)
        return scored[: max(1, k)]

    def compose(self, stimulus: str, *,
                min_jaccard: float = MIN_JACCARD) -> Optional[Tuple[Thought, float, List[RecallHit]]]:
        hits = self.recall(stimulus, k=K_RECALL, min_jaccard=min_jaccard)
        if not hits:
            return None
        by_src: Dict[str, RecallHit] = {}
        for h in hits:
            src = _source_slot(h.ability)
            if src not in by_src:
                by_src[src] = h
        order = ("pfc", "left", "right", "midbrain", "neo")
        parts: List[str] = []
        tags: List[str] = ["neo", "own"]
        confs: List[float] = []
        used: List[RecallHit] = []
        best_j = 0.0
        for src in order:
            h = by_src.get(src)
            if h is None:
                continue
            label = {"pfc": "P", "left": "L", "right": "R", "midbrain": "H", "neo": "N"}[src]
            parts.append(f"[{label}] {h.ability.text}")
            tags.extend(list(h.ability.tags[:4]))
            confs.append(h.ability.confidence * (0.50 + 0.50 * h.jaccard))
            used.append(h)
            if h.jaccard > best_j:
                best_j = h.jaccard
        if not parts:
            h = hits[0]
            parts = [h.ability.text]
            tags.extend(list(h.ability.tags))
            confs = [h.ability.confidence * (0.50 + 0.50 * h.jaccard)]
            used = [h]
            best_j = h.jaccard
        conf = min(1.0, sum(confs) / max(1, len(confs)))
        kind = "own-compose" if len(used) > 1 else "own"
        extra = "compose" if kind == "own-compose" else "recall"
        tag_t = tuple(dict.fromkeys(list(tags) + [extra]))
        mix: Tuple[float, ...] = ()
        left_hit = by_src.get("left")
        if left_hit is not None and len(left_hit.ability.numbers) >= 3:
            mix = tuple(float(x) for x in left_hit.ability.numbers[-3:])
        thought = Thought(
            slot="neo", kind=kind, text=" || ".join(parts),
            confidence=conf,
            tags=tag_t,
            numbers=mix if mix else (best_j, float(len(used))),
        )
        return thought, best_j, used

    def export_tract(self, slot: str, *, backend: str = "own",
                     scale: str = "neo") -> Tract:
        slot = (slot or "").lower()
        ex = tuple(
            a for a in self._items
            if a.slot == slot or slot in a.tags
        )
        if not ex:
            ex = tuple(a for a in self._items if a.slot == "neo")
        caps = tuple(dict.fromkeys(t for a in ex for t in a.tags))
        return Tract(slot=slot, backend=backend, scale=scale,
                     capabilities=caps, exemplars=ex)

    def import_tract(self, tract: Tract) -> int:
        n = 0
        for ab in tract.exemplars:
            tagged = Ability(
                slot="neo",
                stimulus_fp=ab.stimulus_fp,
                signature=ab.signature,
                kind=ab.kind,
                text=ab.text,
                tags=tuple(dict.fromkeys(ab.tags + ("imported", tract.slot, tract.backend))),
                numbers=ab.numbers,
                confidence=ab.confidence,
                seen=ab.seen,
                tokens=ab.tokens,
            )
            self.ingest(tagged)
            n += 1
        return n

    @property
    def size(self) -> int:
        return len(self._items)

    def capabilities(self) -> Tuple[str, ...]:
        return tuple(dict.fromkeys(t for a in self._items for t in a.tags))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "size": self.size,
            "fingerprints": len(self._by_fp),
            "capabilities": list(self.capabilities())[:24],
        }


def shadow_eval(own: Thought, teacher: Thought) -> bool:
    """Own wins if it is at least as sure and shares any structural tag."""
    tag_j = jaccard(own.tags, teacher.tags)
    return (own.confidence + 0.08) >= (teacher.confidence * 0.88) and (
        tag_j >= 0.12 or own.kind.startswith("own")
    )


def _source_slot(ab: Ability) -> str:
    if "acquired" in ab.tags:
        for s in ("pfc", "left", "right", "midbrain"):
            if s in ab.tags:
                return s
    if ab.slot in {"pfc", "left", "right", "midbrain", "neo"}:
        return ab.slot
    for s in ("pfc", "left", "right", "midbrain"):
        if s in ab.tags:
            return s
    return "neo"
