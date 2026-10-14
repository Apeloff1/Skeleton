"""AUD1280-0492 kind_12. Family kind. VOL-156 completion. stored_prose=0.

Aligns with skeleton/audio/pipeline.py asset, segment, and result laws.
Does not fork pipeline.py. No stored sentence.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass, field
from typing import Any

CAP_ID = "AUD1280-0492"
NAME = "kind_12"
FAMILY = "kind"
PACKET = "AUD-1280"
PARENT = "#80"
STORED_PROSE = 0
N_CAP = 6
HEAT = 0.36
SEED = 1578817890
GATE = "kind-enum"
KINDS = ("speech", "music", "event")
MAX_RATE = 96000
MAX_CHANNELS = 8
MAX_DURATION_MS = 600_000
MAX_BYTES = 64_000_000
MASS_CLIP = 1.1
_ID = re.compile(r"^[A-Z][A-Z0-9_.:-]{2,127}$")
FAILURE_MODES = ("bad-asset", "bad-digest", "segment-oob", "kind", "confidence", GATE)

class OrganError(ValueError):
    """Fail-closed audio rejection. Pointers only."""


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
        "citation": "docs/lineage/audio_vol156_batch1280.md",
        "gate": GATE,
        "kinds": list(KINDS),
    }


def failure_modes() -> list[str]:
    return list(FAILURE_MODES)


def security() -> dict[str, Any]:
    return {"network": 0, "torch": 0, "hf": 0, "ace": "fail-closed", "coin": 0, "secret": 0}


@dataclass
class EnvelopePulse:
    generation: int
    sequence: int
    asset_id: str
    sample_rate: int
    channels: int
    start_ms: int
    end_ms: int
    duration_ms: int
    kind: str
    confidence: float
    source_digest: str
    pointers: tuple[str, ...] = ()
    cool: bool = False

    def __post_init__(self) -> None:
        if self.generation < 1 or self.sequence < 0:
            raise OrganError("gen")
        if not _ID.fullmatch(self.asset_id):
            raise OrganError("asset")
        if self.sample_rate < 1 or self.sample_rate > MAX_RATE:
            raise OrganError("rate")
        if self.channels < 1 or self.channels > MAX_CHANNELS:
            raise OrganError("channel")
        if self.duration_ms < 1 or self.duration_ms > MAX_DURATION_MS:
            raise OrganError("duration")
        if self.start_ms < 0 or self.end_ms <= self.start_ms or self.end_ms > self.duration_ms:
            raise OrganError("segment")
        if self.kind not in KINDS:
            raise OrganError("kind")
        if not math.isfinite(self.confidence) or not 0.0 <= self.confidence <= 1.0:
            raise OrganError("confidence")
        if len(self.source_digest) != 64 or any(ch not in "0123456789abcdef" for ch in self.source_digest):
            raise OrganError("digest")
        if len(self.pointers) > N_CAP:
            raise OrganError("ncap")
        for p in self.pointers:
            if not p or " " in p or len(p) > 64:
                raise OrganError("pointer")


@dataclass
class Organ:
    """kind_12. Reversible envelope bag. No stored sentence."""

    generation: int = 1
    closed: bool = False
    heat: float = 0.0
    dropped: int = 0
    accepted: int = 0
    root: str = "0" * 64
    chain: list[str] = field(default_factory=list)
    seen: set[str] = field(default_factory=set)
    bag: list[dict[str, Any]] = field(default_factory=list)
    last_end: int = -1

    def snapshot(self) -> dict[str, Any]:
        return {
            "kind": "audio-organ",
            "id": CAP_ID,
            "name": NAME,
            "family": FAMILY,
            "hit": 1,
            "law": "vol156-kind",
            "citation": "docs/lineage/audio_vol156_batch1280.md",
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

    def _card(self, pulse: EnvelopePulse, hit: int, reason: str, digest: str = "") -> dict[str, Any]:
        return {
            "kind": "audio-pulse",
            "id": CAP_ID,
            "name": NAME,
            "hit": hit,
            "law": reason,
            "citation": "docs/lineage/audio_vol156_batch1280.md",
            "stored_prose": 0,
            "generation": pulse.generation,
            "sequence": pulse.sequence,
            "asset_id": pulse.asset_id,
            "audio_kind": pulse.kind,
            "digest": digest,
            "root": self.root,
            "cool": 1 if pulse.cool else 0,
            "parent": PARENT,
        }

    def admit(self, pulse: EnvelopePulse) -> dict[str, Any]:
        if self.closed:
            self.dropped += 1
            raise OrganError("terminal")
        if pulse.generation != self.generation:
            self.dropped += 1
            raise OrganError("stale-generation")
        key = pulse.asset_id + ":" + str(pulse.sequence)
        if key in self.seen:
            self.dropped += 1
            raise OrganError("duplicate")
        if FAMILY == "clock" and pulse.start_ms < self.last_end:
            self.dropped += 1
            raise OrganError("pts-order")
        if FAMILY == "buffer" and self.accepted >= 64:
            self.dropped += 1
            return self._card(pulse, 0, "backpressure")
        span = pulse.end_ms - pulse.start_ms
        self.heat = min(1.5, self.heat * 0.86 + (span / pulse.duration_ms) * HEAT + (1.0 - pulse.confidence) * 0.04)
        if self.heat >= 0.90 and not pulse.cool:
            self.dropped += 1
            return self._card(pulse, 0, "shunt")
        digest = _canon({
            "asset": pulse.asset_id,
            "rate": pulse.sample_rate,
            "ch": pulse.channels,
            "span": [pulse.start_ms, pulse.end_ms],
            "kind": pulse.kind,
            "conf": round(pulse.confidence, 4),
            "src": pulse.source_digest,
            "ptr": list(pulse.pointers),
        })
        self.seen.add(key)
        self.accepted += 1
        self.last_end = pulse.end_ms
        self.root = _sha([self.root, digest, CAP_ID])
        self.chain.append(self.root)
        if len(self.chain) > 64:
            self.chain = self.chain[-64:]
        self.bag.append({
            "seq": pulse.sequence,
            "asset": pulse.asset_id,
            "end": pulse.end_ms,
            "digest": digest,
            "ptr": list(pulse.pointers)[:N_CAP],
            "audio_kind": pulse.kind,
        })
        self._clip()
        return self._card(pulse, 1, "admit", digest)

    def reverse(self) -> dict[str, Any] | None:
        if not self.bag:
            return None
        last = self.bag.pop()
        self.accepted = max(0, self.accepted - 1)
        self.seen.discard(str(last["asset"]) + ":" + str(last["seq"]))
        if self.chain:
            self.chain.pop()
        self.root = self.chain[-1] if self.chain else "0" * 64
        self.last_end = int(self.bag[-1]["end"]) if self.bag else -1
        return last

    def replay(self) -> str:
        acc = "0" * 64
        for item in self.bag:
            acc = _sha([acc, str(item["digest"])])
        return acc

    def family_gate(self, pulse: EnvelopePulse) -> dict[str, Any]:
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
        if FAMILY == "kind" and pulse.kind not in KINDS:
            raise OrganError("kind")
        return self.admit(pulse)

    def capabilities(self) -> dict[str, Any]:
        return {
            "owner": "audio.vol156",
            "contract": contract(),
            "failure_modes": failure_modes(),
            "obs": ["heat", "dropped", "accepted", "root", "mass"],
            "security": security(),
        }
