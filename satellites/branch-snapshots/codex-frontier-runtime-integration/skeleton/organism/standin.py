"""Local stand-in teacher. No HuggingFace. House dialect only.

Binds a port named `teacher` onto a neo so contact + LoRA write-back
have a copy to work. Weights are an NGramLM. Not a frontier mouth.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from skeleton.cortex.lm import NGramLM, gameforge_corpus
from skeleton.cortex.port import Thought


class StandinTeacher:
    name = "teacher"
    scale = "injected"

    def __init__(self, slot: str = "right") -> None:
        self.slot = slot
        self._ng = NGramLM(order=2)
        self._ng.fit(gameforge_corpus()[:12])
        self.lora = None
        self.transformer = self
        self.standin = self

    def think(self, stimulus: str, context: Dict[str, Any]) -> Thought:
        return Thought(
            slot=self.slot, kind="standin-teacher",
            text=(stimulus or "plan tensor ttk")[:200],
            confidence=0.7, tags=("teacher", "standin", self.slot),
        )

    def fit(self, texts, lr: float = 0.05, schedule: str = "cosine") -> int:
        if isinstance(texts, str):
            texts = [texts]
        return int(self._ng.fit(texts))

    def perplexity(self, texts) -> float:
        return float(self._ng.perplexity(texts))

    def hidden(self, stimulus: str):
        raw = (stimulus or "x").encode("utf-8")[:8]
        return tuple((b / 255.0) * 2 - 1 for b in (raw + b"\x00" * 8)[:8])

    def snapshot(self) -> Dict[str, Any]:
        return {"kind": "standin-teacher", "slot": self.slot, "lm": self._ng.snapshot()}

    def attach_lora(self, rank: int = 2, alpha: float = 4.0) -> Dict[str, Any]:
        self.lora = {"rank": rank, "alpha": alpha, "kind": "standin-lora"}
        return {"attached": ["standin"], "rank": rank}

    def merge_lora(self) -> Dict[str, Any]:
        merged = bool(self.lora)
        self.lora = None
        return {"merged": ["standin"] if merged else []}

    def ingest_residual(self, text: str) -> int:
        return self.fit(text)


def bind(neo, *, slot: str = "right") -> Dict[str, Any]:
    if neo is None:
        return {"bound": 0, "reason": "no-mouth", "stored_prose": 0}
    slots = getattr(neo, "slots", None)
    if slots is None:
        try:
            neo.slots = {}
            slots = neo.slots
        except Exception:
            return {"bound": 0, "reason": "no-slots", "stored_prose": 0}
    port = StandinTeacher(slot)
    slots[slot] = port
    setattr(neo, "standin_teacher", port)
    if not hasattr(neo, "attach_lora"):
        neo.attach_lora = port.attach_lora
        neo.merge_lora = port.merge_lora
        neo.ingest_residual = port.ingest_residual
    return {
        "bound": 1,
        "slot": slot,
        "name": port.name,
        "teacher": True,
        "stored_prose": 0,
    }
