"""Launch-ready distillation and knowledge card system.

Turns raw game artifacts and critique into compact, reusable knowledge cards
that the local AI can absorb and re-apply on future builds.
Fail-closed. Immediately usable.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
import hashlib
import json
import time


@dataclass
class KnowledgeCard:
    card_id: str
    kind: str
    payload: Dict[str, Any]
    fidelity: float
    era: str = "HOUSE_ERA"
    created_at: float = field(default_factory=time.time)
    source_hash: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "card_id": self.card_id,
            "kind": self.kind,
            "payload": self.payload,
            "fidelity": round(self.fidelity, 4),
            "era": self.era,
            "created_at": self.created_at,
            "source_hash": self.source_hash,
        }


class DistillationEngine:
    """
    Distills game build results into compact knowledge cards.

    Card kinds:
      - mechanic     : extracted core loops
      - layout       : room graph patterns
      - entity       : enemy/boss templates
      - narrative    : beat structures
      - critique     : axis scores and weakest links
      - refine       : successful delta applications
    """

    def __init__(self, era: str = "HOUSE_ERA") -> None:
        self.era = era
        self._store: Dict[str, KnowledgeCard] = {}

    def _hash(self, data: Any) -> str:
        raw = json.dumps(data, sort_keys=True, default=str).encode()
        return hashlib.sha256(raw).hexdigest()[:16]

    def distill(self, kind: str, payload: Dict[str, Any], fidelity: float) -> KnowledgeCard:
        if not kind or not payload:
            raise ValueError("kind and payload required")
        if fidelity < 0.0 or fidelity > 1.0:
            raise ValueError("fidelity must be in [0, 1]")

        card_id = f"{kind}_{self._hash(payload)}"
        card = KnowledgeCard(
            card_id=card_id,
            kind=kind,
            payload=payload,
            fidelity=fidelity,
            era=self.era,
            source_hash=self._hash(payload),
        )
        self._store[card_id] = card
        return card

    def absorb_pipeline_result(self, result: Dict[str, Any]) -> List[KnowledgeCard]:
        """Turn a full conductor.run() result into multiple cards."""
        cards: List[KnowledgeCard] = []
        stages = result.get("stages", [])
        for stage in stages:
            if not stage.get("ok"):
                continue
            kind = stage.get("stage", "unknown")
            payload = stage.get("artifacts", {})
            fid = float(stage.get("fidelity", 0.0))
            if payload and fid > 0.5:
                cards.append(self.distill(kind, payload, fid))
        # Overall card
        if result.get("ok"):
            cards.append(self.distill(
                "pipeline",
                {"fidelity": result.get("fidelity"), "stage_count": len(stages)},
                float(result.get("fidelity", 0.0)),
            ))
        return cards

    def query(self, kind: Optional[str] = None, min_fidelity: float = 0.0) -> List[KnowledgeCard]:
        results = []
        for card in self._store.values():
            if kind and card.kind != kind:
                continue
            if card.fidelity < min_fidelity:
                continue
            results.append(card)
        return sorted(results, key=lambda c: c.fidelity, reverse=True)

    def best(self, kind: str) -> Optional[KnowledgeCard]:
        matches = self.query(kind)
        return matches[0] if matches else None

    def export(self) -> List[Dict[str, Any]]:
        return [c.to_dict() for c in self._store.values()]

    def count(self) -> int:
        return len(self._store)
