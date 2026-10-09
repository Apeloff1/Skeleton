"""ERA5120-3796 voice_276. Era voice. Game-audio completion. stored_prose=0.

Polyphony, rate, and channel caps are era laws. No sample bank.
Does not fork pipeline.py or vol156.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field
from typing import Any

CAP_ID = "ERA5120-3796"
NAME = "voice_276"
ERA = "voice"
PACKET = "ERA-5120"
PARENT = "#80"
STORED_PROSE = 0
N_CAP = 5
HEAT = 0.31
SEED = 3099094274
VOICE_CAP = 4
RATE_CAP = 16000
CHANNEL_CAP = 1
MASS_CLIP = 1.1
FAILURE_MODES = ("polyphony", "rate", "channel", "gain", "stimulus", "stale")

class OrganError(ValueError):
    """Fail-closed era-audio rejection. No stored sentence."""


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
        "era": ERA,
        "voices": VOICE_CAP,
        "rate_cap": RATE_CAP,
        "channels": CHANNEL_CAP,
        "n_cap": N_CAP,
        "heat": HEAT,
        "stored_prose": 0,
        "parent": PARENT,
        "citation": "docs/lineage/audio_eras_batch5120.md",
    }


def failure_modes() -> list[str]:
    return list(FAILURE_MODES)


def security() -> dict[str, Any]:
    return {"network": 0, "torch": 0, "hf": 0, "ace": "fail-closed", "coin": 0, "secret": 0, "sample_bank": 0}


def rolloff(distance: float, ref: float = 1.0) -> float:
    if distance < 0 or not math.isfinite(distance):
        raise OrganError("distance")
    if ERA == "spatial":
        return 1.0 / (1.0 + max(0.0, distance - ref))
    if ERA == "occlude":
        return max(0.0, 1.0 - min(distance, 1.0))
    return 1.0


def mix_gain(voices: int, gain: float) -> float:
    if voices < 1 or voices > VOICE_CAP:
        raise OrganError("polyphony")
    if not math.isfinite(gain) or gain < 0 or gain > 1:
        raise OrganError("gain")
    if ERA == "bus":
        return min(1.0, gain * voices / VOICE_CAP)
    if ERA == "cdda":
        return gain
    return gain / voices


@dataclass
class EraPulse:
    generation: int
    sequence: int
    voices: int
    sample_rate: int
    channels: int
    gain: float
    distance: float = 1.0
    pointers: tuple[str, ...] = ()
    cool: bool = False
    stimulus: str = ""

    def __post_init__(self) -> None:
        if self.generation < 1 or self.sequence < 0:
            raise OrganError("gen")
        if self.voices < 1 or self.voices > VOICE_CAP:
            raise OrganError("polyphony")
        if self.sample_rate < 1 or self.sample_rate > RATE_CAP:
            raise OrganError("rate")
        if self.channels < 1 or self.channels > CHANNEL_CAP:
            raise OrganError("channel")
        if not math.isfinite(self.gain) or not 0.0 <= self.gain <= 1.0:
            raise OrganError("gain")
        if self.stimulus:
            raise OrganError("stimulus")
        if len(self.pointers) > N_CAP:
            raise OrganError("ncap")
        for p in self.pointers:
            if not p or " " in p or len(p) > 64:
                raise OrganError("pointer")


@dataclass
class Organ:
    """voice_276. Reversible era bag. No sample payload."""

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
            "kind": "era-organ",
            "id": CAP_ID,
            "name": NAME,
            "era": ERA,
            "hit": 1,
            "law": "era-voice",
            "citation": "docs/lineage/audio_eras_batch5120.md",
            "stored_prose": 0,
            "generation": self.generation,
            "heat": round(self.heat, 6),
            "dropped": self.dropped,
            "accepted": self.accepted,
            "root": self.root,
            "mass": len(self.bag),
            "voices": VOICE_CAP,
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

    def _card(self, pulse: EraPulse, hit: int, reason: str, digest: str = "") -> dict[str, Any]:
        return {
            "kind": "era-pulse",
            "id": CAP_ID,
            "name": NAME,
            "era": ERA,
            "hit": hit,
            "law": reason,
            "citation": "docs/lineage/audio_eras_batch5120.md",
            "stored_prose": 0,
            "generation": pulse.generation,
            "sequence": pulse.sequence,
            "voices": pulse.voices,
            "digest": digest,
            "root": self.root,
            "cool": 1 if pulse.cool else 0,
            "parent": PARENT,
        }

    def admit(self, pulse: EraPulse) -> dict[str, Any]:
        if self.closed:
            self.dropped += 1
            raise OrganError("terminal")
        if pulse.generation != self.generation:
            self.dropped += 1
            raise OrganError("stale-generation")
        key = ERA + ":" + str(pulse.sequence)
        if key in self.seen:
            self.dropped += 1
            raise OrganError("duplicate")
        gain = mix_gain(pulse.voices, pulse.gain) * rolloff(pulse.distance)
        self.heat = min(1.5, self.heat * 0.84 + HEAT * pulse.voices / VOICE_CAP)
        if self.heat >= 0.90 and not pulse.cool:
            self.dropped += 1
            return self._card(pulse, 0, "shunt")
        digest = _canon({
            "era": ERA,
            "voices": pulse.voices,
            "rate": pulse.sample_rate,
            "ch": pulse.channels,
            "gain": round(gain, 6),
            "ptr": list(pulse.pointers),
        })
        self.seen.add(key)
        self.accepted += 1
        self.root = _sha([self.root, digest, CAP_ID])
        self.chain.append(self.root)
        if len(self.chain) > 64:
            self.chain = self.chain[-64:]
        self.bag.append({"seq": pulse.sequence, "digest": digest, "gain": round(gain, 6)})
        self._clip()
        return self._card(pulse, 1, "admit", digest)

    def reverse(self) -> dict[str, Any] | None:
        if not self.bag:
            return None
        last = self.bag.pop()
        self.accepted = max(0, self.accepted - 1)
        self.seen.discard(ERA + ":" + str(last["seq"]))
        if self.chain:
            self.chain.pop()
        self.root = self.chain[-1] if self.chain else "0" * 64
        return last

    def replay(self) -> str:
        acc = "0" * 64
        for item in self.bag:
            acc = _sha([acc, str(item["digest"])])
        return acc

    def capabilities(self) -> dict[str, Any]:
        return {
            "owner": "audio.eras",
            "contract": contract(),
            "failure_modes": failure_modes(),
            "obs": ["heat", "dropped", "accepted", "root", "mass"],
            "security": security(),
        }
