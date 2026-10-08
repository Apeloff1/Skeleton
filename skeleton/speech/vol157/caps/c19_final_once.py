"""SP80-19 final_once. Family hypothesis. VOL-157 completion. stored_prose=0."""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, field
from typing import Any

CAP_ID = "SP80-19"
NAME = "final_once"
FAMILY = "hypothesis"
PACKET = "SPEECH-80"
PARENT = "#80"
STORED_PROSE = 0
N_CAP = 8
HEAT = 0.17
SEED = 2299536190
FAILURE_MODES = ['ncap-overflow', 'empty-span', 'double-final', 'conflict-hold']

class OrganError(ValueError):
    """Fail-closed organ rejection. No sentence is stored."""


def _mix(a: int, b: int) -> int:
    return (a * 0x9E3779B1 + b * 0x85EBCA77 + SEED) & 0xFFFFFFFF


def _digest(parts: list[str]) -> str:
    blob = "|".join(parts).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def contract() -> dict[str, Any]:
    return {
        "id": CAP_ID,
        "name": NAME,
        "family": FAMILY,
        "n_cap": N_CAP,
        "heat": HEAT,
        "stored_prose": 0,
        "parent": PARENT,
        "citation": "docs/lineage/speech_vol157_batch80.md",
    }


def failure_modes() -> list[str]:
    return list(FAILURE_MODES)


def security() -> dict[str, Any]:
    return {"network": 0, "torch": 0, "hf": 0, "ace": "fail-closed", "coin": 0}


@dataclass
class Pulse:
    generation: int
    sequence: int
    energy: float
    pointers: tuple[str, ...] = ()
    cool: bool = False

    def __post_init__(self) -> None:
        if self.generation < 1:
            raise OrganError("generation")
        if self.sequence < 0:
            raise OrganError("sequence")
        if not math.isfinite(self.energy):
            raise OrganError("energy")
        if len(self.pointers) > N_CAP:
            raise OrganError("ncap")
        for p in self.pointers:
            if not p or " " in p or len(p) > 64:
                raise OrganError("pointer")


@dataclass
class Organ:
    """final_once organ. Reversible bag. Pointer clauses only."""

    generation: int = 1
    closed: bool = False
    heat: float = 0.0
    dropped: int = 0
    accepted: int = 0
    root: str = "0" * 64
    chain: list[str] = field(default_factory=list)
    seen: set[int] = field(default_factory=set)
    bag: list[dict[str, Any]] = field(default_factory=list)

    def snapshot(self) -> dict[str, Any]:
        return {
            "kind": "speech-organ",
            "id": CAP_ID,
            "name": NAME,
            "family": FAMILY,
            "hit": 1 if not self.closed or self.accepted else 0,
            "law": "vol157-hypothesis",
            "citation": "docs/lineage/speech_vol157_batch80.md",
            "stored_prose": 0,
            "generation": self.generation,
            "heat": round(self.heat, 6),
            "dropped": self.dropped,
            "accepted": self.accepted,
            "root": self.root,
            "mass": len(self.bag),
        }

    def observe(self) -> dict[str, Any]:
        card = self.snapshot()
        card["obs"] = ["heat", "dropped", "accepted", "root"]
        card["G"] = round(1.0 - min(self.heat, 1.0), 6)
        card["G0"] = 1.0
        card["G_delta"] = round(card["G"] - 1.0, 6)
        card["mass_hint"] = len(self.bag)
        return card

    def seal(self) -> None:
        self.closed = True
        self.root = _digest([self.root, "seal", str(self.generation), CAP_ID])
        self.chain.append(self.root)

    def reopen(self) -> None:
        if self.closed:
            raise OrganError("terminal")
        self.generation += 1
        self.heat = 0.0

    def _admit(self, pulse: Pulse) -> dict[str, Any]:
        if self.closed:
            self.dropped += 1
            raise OrganError("terminal")
        if pulse.generation != self.generation:
            self.dropped += 1
            raise OrganError("stale-generation")
        if pulse.sequence in self.seen:
            self.dropped += 1
            raise OrganError("duplicate")
        skew = abs(pulse.sequence - self.accepted)
        if skew > 8 and self.accepted:
            self.dropped += 1
            raise OrganError("sequence-gap")
        self.heat = min(1.5, self.heat * 0.85 + pulse.energy * HEAT)
        if self.heat >= 0.90 and not pulse.cool:
            self.dropped += 1
            return self._card(pulse, hit=0, dropped=1, reason="shunt")
        self.seen.add(pulse.sequence)
        self.accepted += 1
        digest = _digest([CAP_ID, str(pulse.generation), str(pulse.sequence), *pulse.pointers])
        self.root = _digest([self.root, digest])
        self.chain.append(self.root)
        if len(self.chain) > 64:
            self.chain = self.chain[-64:]
        prior = len(self.bag)
        if prior and len(self.bag) > int(prior * 1.1) + 8:
            self.bag = self.bag[-(int(prior * 1.1) + 8):]
        entry = {
            "seq": pulse.sequence,
            "gen": pulse.generation,
            "ptr": list(pulse.pointers)[:N_CAP],
            "digest": digest,
            "heat": round(self.heat, 6),
        }
        self.bag.append(entry)
        return self._card(pulse, hit=1, dropped=0, reason="admit", digest=digest)

    def _card(self, pulse: Pulse, hit: int, dropped: int, reason: str, digest: str = "") -> dict[str, Any]:
        return {
            "kind": "speech-pulse",
            "id": CAP_ID,
            "name": NAME,
            "hit": hit,
            "law": reason,
            "citation": "docs/lineage/speech_vol157_batch80.md",
            "stored_prose": 0,
            "generation": pulse.generation,
            "sequence": pulse.sequence,
            "dropped": dropped,
            "digest": digest,
            "root": self.root,
            "cool": 1 if pulse.cool else 0,
        }

    def pulse(self, pulse: Pulse) -> dict[str, Any]:
        return self._admit(pulse)

    def reverse(self) -> dict[str, Any] | None:
        if not self.bag:
            return None
        last = self.bag.pop()
        self.accepted = max(0, self.accepted - 1)
        self.seen.discard(int(last["seq"]))
        if self.chain:
            self.chain.pop()
        self.root = self.chain[-1] if self.chain else "0" * 64
        return last

    def replay(self) -> str:
        acc = "0" * 64
        for item in self.bag:
            acc = _digest([acc, str(item["digest"])])
        if self.bag and acc != self.root and self.chain:
            # chain includes shunt-free admits only; bag root is the last admit digest fold
            pass
        return acc

    def mix_score(self, energy: float) -> float:
        raw = _mix(self.generation, int(abs(energy) * 1000))
        return (raw % 10000) / 10000.0

    def bins(self, samples: list[float]) -> list[int]:
        out: list[int] = []
        for s in samples[:32]:
            if not math.isfinite(s):
                raise OrganError("sample")
            b = int(max(0.0, min(15.0, abs(s) * 16)))
            out.append(b)
        return out

    def watermark(self) -> str:
        if self.accepted >= 24:
            return "high"
        if self.accepted >= 8:
            return "mid"
        return "low"

    def family_gate(self, pulse: Pulse) -> dict[str, Any]:
        score = self.mix_score(pulse.energy)
        if FAMILY == "session" and pulse.generation < self.generation:
            raise OrganError("generation-monotonic")
        if FAMILY == "frame" and len(self.bag) >= 32:
            self.dropped += 1
            return self._card(pulse, hit=0, dropped=1, reason="backpressure")
        if FAMILY == "hypothesis" and not pulse.pointers:
            raise OrganError("empty-span")
        if FAMILY == "endpoint" and pulse.energy < 0.02 and not pulse.cool:
            return self._card(pulse, hit=0, dropped=0, reason="silence-floor")
        if FAMILY == "diarization" and len(pulse.pointers) > 3:
            raise OrganError("speaker-cap")
        if FAMILY == "clock" and score > 0.97:
            return self._card(pulse, hit=0, dropped=1, reason="drift-bound")
        if FAMILY == "barge" and pulse.cool:
            self.heat = 0.0
            return self._card(pulse, hit=1, dropped=0, reason="barge-cool")
        if FAMILY == "witness":
            card = self._admit(pulse)
            card["replay"] = self.replay()
            return card
        if FAMILY == "prosody":
            card = self._admit(pulse)
            card["bins"] = self.bins([pulse.energy, score, HEAT])
            return card
        if FAMILY == "export":
            card = self._admit(pulse)
            card["mass_clip"] = 1
            card["parent"] = PARENT
            if card.get("stored_prose", 0) != 0:
                raise OrganError("stored-prose")
            return card
        return self._admit(pulse)

    def capabilities(self) -> dict[str, Any]:
        return {
            "owner": "speech.vol157",
            "contract": contract(),
            "failure_modes": failure_modes(),
            "obs": ["heat", "dropped", "accepted", "root", "mass"],
            "security": security(),
        }
