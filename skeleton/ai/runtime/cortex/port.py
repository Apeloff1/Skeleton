"""Interchangeable model ports — the architecture is the model.

We are building a model, not implementing one. No weights, no tokenizer,
no transformer. A ModelPort is a slot a backend plugs into. Jeeves binds
any backend (local symbolic, echo, injected callable, another cortex's
own-system) into any slot and later acquires that slot's abilities.

Slots
-----
  pfc       small language model  — prefrontal cortex, boilerplate
  midbrain  medium language model — coordinator, salience, routing
  left      left hemisphere       — sequential, symbolic, analytic
  right     right hemisphere      — gestalt, spatial, analogical
  neo       Jeeves neocortex      — hivemind organizer + the model in training
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, Optional, Protocol, Tuple

SLOTS: Tuple[str, ...] = ("pfc", "midbrain", "left", "right")
SCALES: Tuple[str, ...] = ("small", "medium", "hemisphere", "neo", "injected")

_TOKEN = re.compile(r"[a-z0-9]+")


def fingerprint(text: str) -> str:
    toks = tuple(sorted(set(_TOKEN.findall((text or "").lower()))))
    return hashlib.sha256("|".join(toks).encode()).hexdigest()[:16]


def tokens(text: str) -> Tuple[str, ...]:
    return tuple(_TOKEN.findall((text or "").lower()))


def jaccard(a: Iterable[str], b: Iterable[str]) -> float:
    sa, sb = set(a or ()), set(b or ())
    if not sa and not sb:
        return 1.0
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def _signature(slot: str, kind: str, tags: Tuple[str, ...],
               numbers: Tuple[float, ...], text: str) -> str:
    blob = f"{slot}|{kind}|{','.join(tags)}|{','.join(f'{n:.4f}' for n in numbers)}|{text[:240]}"
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


@dataclass(frozen=True)
class Thought:
    slot: str
    text: str
    kind: str
    confidence: float
    tags: Tuple[str, ...] = ()
    numbers: Tuple[float, ...] = ()
    signature: str = ""

    def __post_init__(self) -> None:
        conf = 0.0 if self.confidence < 0 else 1.0 if self.confidence > 1 else float(self.confidence)
        object.__setattr__(self, "confidence", conf)
        if not self.signature:
            object.__setattr__(self, "signature", _signature(
                self.slot, self.kind, self.tags, self.numbers, self.text,
            ))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "slot": self.slot,
            "kind": self.kind,
            "text": self.text,
            "confidence": round(self.confidence, 4),
            "tags": list(self.tags),
            "numbers": [round(n, 4) for n in self.numbers],
            "signature": self.signature,
        }


class ModelPort(Protocol):
    """The only seam. Bind anything that speaks this surface."""

    name: str
    scale: str
    slot: str

    def think(self, stimulus: str, context: Dict[str, Any]) -> Thought: ...
    def fit(self, text: str) -> int: ...
    def decode(self, stimulus: str, *, n: int = 8, seed: int = 0) -> str: ...
    def snapshot(self) -> Dict[str, Any]: ...
    def perplexity(self, texts: Iterable[str]) -> float: ...


class EchoBackend:
    """Identity backend — proves a slot is interchangeable."""

    def __init__(self, slot: str = "left", *, name: str = "echo") -> None:
        self.slot = slot
        self.name = name
        self.scale = "injected"

    def think(self, stimulus: str, context: Dict[str, Any]) -> Thought:
        return Thought(
            slot=self.slot, kind="echo",
            text=f"ECHO[{self.slot}] {(stimulus or '')[:160]}",
            confidence=1.0, tags=("echo", self.slot),
        )

    def fit(self, text: str) -> int:
        return 0

    def decode(self, stimulus: str, *, n: int = 8, seed: int = 0) -> str:
        return f"ECHO[{self.slot}] {(stimulus or '')[: max(1, int(n) * 8)]}"

    def snapshot(self) -> Dict[str, Any]:
        return {"kind": "echo", "slot": self.slot, "name": self.name}

    @classmethod
    def from_snapshot(cls, data: Dict[str, Any], *, slot: str | None = None) -> "EchoBackend":
        sl = slot or str((data or {}).get("slot") or "left")
        return cls(slot=sl, name=str((data or {}).get("name") or "echo"))

    def perplexity(self, texts: Iterable[str]) -> float:
        return 1.0


class CallableBackend:
    """Wrap an injected callable (LLM, hive agent, another model).

    The callable may return a Thought (full authorship) or a string.
    Strings that contain ``mix trash=N elite=M boss=K`` become numbers
    the builder can compile. That is how an injected left tract authors
    a mix the local hemisphere never would.
    """

    def __init__(self, fn: Callable[[str, Dict[str, Any]], Any], *,
                 slot: str, name: str = "injected", scale: str = "injected") -> None:
        self.fn = fn
        self.slot = slot
        self.name = name
        self.scale = scale

    def think(self, stimulus: str, context: Dict[str, Any]) -> Thought:
        out = self.fn(stimulus or "", context or {})
        if isinstance(out, Thought):
            return out
        text = str(out)[:400]
        m = re.search(r"mix trash=(\d+) elite=(\d+) boss=(\d+)", text.lower())
        tags = ["injected", self.name, self.slot]
        numbers: Tuple[float, ...] = ()
        if m:
            numbers = (float(m.group(1)), float(m.group(2)), float(m.group(3)))
            tags.append("mix")
        return Thought(
            slot=self.slot, kind="injected",
            text=text, confidence=0.7,
            tags=tuple(tags), numbers=numbers,
        )

    def fit(self, text: str) -> int:
        return 0

    def decode(self, stimulus: str, *, n: int = 8, seed: int = 0) -> str:
        thought = self.think(stimulus or "", {})
        return (thought.text or "")[: max(1, int(n) * 12)]

    def snapshot(self) -> Dict[str, Any]:
        return {"kind": "callable", "slot": self.slot, "name": self.name, "scale": self.scale}

    @classmethod
    def from_snapshot(cls, data: Dict[str, Any], *, slot: str | None = None) -> "CallableBackend":
        sl = slot or str((data or {}).get("slot") or "left")
        return cls(lambda s, c: f"ECHO[{sl}] {s}", slot=sl, name=str((data or {}).get("name") or "injected"))

    def perplexity(self, texts: Iterable[str]) -> float:
        return 1.0
