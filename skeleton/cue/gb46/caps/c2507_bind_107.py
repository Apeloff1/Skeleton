"""CUE2560-2507 bind_107. Family bind. GB-46 completion. stored_prose=0.

Aligns with skeleton/cue/law.py five-axis vocab. Stimulus is dropped.
Does not fork law.py, fold.py, compose.py, or capabilities.py.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field
from typing import Any

CAP_ID = "CUE2560-2507"
NAME = "bind_107"
FAMILY = "bind"
PACKET = "CUE-2560"
PARENT = "#80"
STORED_PROSE = 0
N_CAP = 6
HEAT = 0.36
SEED = 2185197199
GATE = "parent-cite"
MASS_CLIP = 1.1
AXES = ("house", "topic", "depth", "think", "obscure")
VOCAB = {
    "house": ("xarchive", "archive", "x", "github", "arxiv"),
    "topic": ("plan", "loop", "kv", "attn", "forge"),
    "depth": ("r1", "r2", "r3halt", "smelt", "etd"),
    "think": ("why", "how", "reason", "proof", "latent"),
    "obscure": ("yarn", "sink", "mla", "softpick", "qkmla", "aqnoise"),
}
FAILURE_MODES = ("bad-axis", "bad-token", "stimulus", "ncap", "stale", GATE)

class OrganError(ValueError):
    """Fail-closed cue rejection. Tokens only."""


def _sha(parts: list[str]) -> str:
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def _canon(obj: object) -> str:
    try:
        blob = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise OrganError("canon") from exc
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def contract() -> dict[str, Any]:
    return {
        "id": CAP_ID,
        "name": NAME,
        "family": FAMILY,
        "n_cap": N_CAP,
        "heat": HEAT,
        "stored_prose": 0,
        "parent": PARENT,
        "citation": "docs/lineage/cue_gb46_batch2560.md",
        "gate": GATE,
        "axes": list(AXES),
    }


def failure_modes() -> list[str]:
    return list(FAILURE_MODES)


def security() -> dict[str, Any]:
    return {"network": 0, "torch": 0, "hf": 0, "ace": "fail-closed", "coin": 0, "secret": 0}


@dataclass
class CuePulse:
    generation: int
    sequence: int
    house: str
    topic: str
    depth: str
    think: str
    obscure: str
    pointers: tuple[str, ...] = ()
    cool: bool = False
    stimulus: str = ""

    def __post_init__(self) -> None:
        if self.generation < 1 or self.sequence < 0:
            raise OrganError("gen")
        tokens = {
            "house": self.house,
            "topic": self.topic,
            "depth": self.depth,
            "think": self.think,
            "obscure": self.obscure,
        }
        for axis, token in tokens.items():
            if token not in VOCAB[axis]:
                raise OrganError(axis)
        if self.stimulus:
            raise OrganError("stimulus")
        if len(self.pointers) > N_CAP:
            raise OrganError("ncap")
        for p in self.pointers:
            if not p or " " in p or len(p) > 64:
                raise OrganError("pointer")


@dataclass
class Organ:
    """bind_107. Reversible token bag. Stimulus dropped."""

    generation: int = 1
    closed: bool = False
    heat: float = 0.0
    dropped: int = 0
    accepted: int = 0
    root: str = "0" * 64
    chain: list[str] = field(default_factory=list)
    seen: set[str] = field(default_factory=set)
    bag: list[dict[str, Any]] = field(default_factory=list)

    def snapshot(self) -> dict[str, Any]:
        return {
            "kind": "cue-organ",
            "id": CAP_ID,
            "name": NAME,
            "family": FAMILY,
            "hit": 1,
            "law": "gb46-bind",
            "citation": "docs/lineage/cue_gb46_batch2560.md",
            "stored_prose": 0,
            "generation": self.generation,
            "heat": round(self.heat, 6),
            "dropped": self.dropped,
            "accepted": self.accepted,
            "root": self.root,
            "mass": len(self.bag),
            "gate": GATE,
        }

    def observe(self) -> dict[str, Any]:
        card = self.snapshot()
        card["obs"] = ["heat", "dropped", "accepted", "root", "mass"]
        card["G"] = round(1.0 - min(self.heat, 1.0), 6)
        card["G0"] = 1.0
        card["G_delta"] = round(card["G"] - 1.0, 6)
        card["mass_hint"] = len(self.bag)
        return card

    def seal(self) -> str:
        self.closed = True
        self.root = _sha([self.root, "seal", str(self.generation), CAP_ID])
        self.chain.append(self.root)
        return self.root

    def _clip(self) -> None:
        limit = int(max(1, self.accepted) * MASS_CLIP) + 8
        if len(self.bag) > limit:
            self.bag = self.bag[-limit:]

    def _card(self, pulse: CuePulse, hit: int, reason: str, digest: str = "") -> dict[str, Any]:
        return {
            "kind": "cue-pulse",
            "id": CAP_ID,
            "name": NAME,
            "hit": hit,
            "law": reason,
            "citation": "docs/lineage/cue_gb46_batch2560.md",
            "stored_prose": 0,
            "generation": pulse.generation,
            "sequence": pulse.sequence,
            "house": pulse.house,
            "topic": pulse.topic,
            "digest": digest,
            "root": self.root,
            "cool": 1 if pulse.cool else 0,
            "parent": PARENT,
        }

    def admit(self, pulse: CuePulse) -> dict[str, Any]:
        if self.closed:
            self.dropped += 1
            raise OrganError("terminal")
        if pulse.generation != self.generation:
            self.dropped += 1
            raise OrganError("stale-generation")
        key = pulse.house + ":" + pulse.topic + ":" + str(pulse.sequence)
        if key in self.seen:
            self.dropped += 1
            raise OrganError("duplicate")
        if FAMILY == "drop" and pulse.stimulus:
            self.dropped += 1
            raise OrganError("stimulus")
        self.heat = min(1.5, self.heat * 0.85 + HEAT)
        if self.heat >= 0.90 and not pulse.cool:
            self.dropped += 1
            return self._card(pulse, 0, "shunt")
        digest = _canon({
            "house": pulse.house,
            "topic": pulse.topic,
            "depth": pulse.depth,
            "think": pulse.think,
            "obscure": pulse.obscure,
            "ptr": list(pulse.pointers),
        })
        self.seen.add(key)
        self.accepted += 1
        self.root = _sha([self.root, digest, CAP_ID])
        self.chain.append(self.root)
        if len(self.chain) > 64:
            self.chain = self.chain[-64:]
        self.bag.append({
            "seq": pulse.sequence,
            "house": pulse.house,
            "topic": pulse.topic,
            "digest": digest,
            "ptr": list(pulse.pointers)[:N_CAP],
        })
        self._clip()
        return self._card(pulse, 1, "admit", digest)

    def reverse(self) -> dict[str, Any] | None:
        if not self.bag:
            return None
        last = self.bag.pop()
        self.accepted = max(0, self.accepted - 1)
        self.seen.discard(str(last["house"]) + ":" + str(last["topic"]) + ":" + str(last["seq"]))
        if self.chain:
            self.chain.pop()
        self.root = self.chain[-1] if self.chain else "0" * 64
        return last

    def replay(self) -> str:
        acc = "0" * 64
        for item in self.bag:
            acc = _sha([acc, str(item["digest"])])
        return acc

    def family_gate(self, pulse: CuePulse) -> dict[str, Any]:
        if not math.isfinite(self.heat):
            raise OrganError("heat")
        if FAMILY == "export":
            card = self.admit(pulse)
            if card.get("stored_prose", 0) != 0:
                raise OrganError("stored-prose")
            card["mass_clip"] = MASS_CLIP
            return card
        if FAMILY == "witness":
            card = self.admit(pulse)
            card["replay"] = self.replay()
            return card
        return self.admit(pulse)

    def capabilities(self) -> dict[str, Any]:
        return {
            "owner": "cue.gb46",
            "contract": contract(),
            "failure_modes": failure_modes(),
            "obs": ["heat", "dropped", "accepted", "root", "mass"],
            "security": security(),
        }
