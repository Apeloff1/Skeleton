"""VID320-237 drop_17. Family drop. VOL-158 completion. stored_prose=0.

Aligns with skeleton/video/pipeline.py asset, segment, and frame laws.
Does not fork pipeline.py.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass, field
from typing import Any

CAP_ID = "VID320-237"
NAME = "drop_17"
FAMILY = "drop"
PACKET = "VID-320"
PARENT = "#80"
STORED_PROSE = 0
N_CAP = 6
HEAT = 0.18
SEED = 2500276149
GATE = "shunt"
MAX_PIXELS = 1920 * 1080
MAX_DURATION_MS = 120_000
MAX_FRAMES = 3600
MAX_BYTES = 32_000_000
MASS_CLIP = 1.1
_ID = re.compile(r"^[A-Z][A-Z0-9_.:-]{2,127}$")
FAILURE_MODES = ("bad-asset", "bad-digest", "pixel-cap", "segment-oob", "sample-budget", GATE)

class OrganError(ValueError):
    """Fail-closed video rejection. Pointers only."""


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
        "citation": "docs/lineage/video_vol158_batch320.md",
        "max_pixels": MAX_PIXELS,
        "max_frames": MAX_FRAMES,
        "gate": GATE,
    }


def failure_modes() -> list[str]:
    return list(FAILURE_MODES)


def security() -> dict[str, Any]:
    return {"network": 0, "torch": 0, "hf": 0, "ace": "fail-closed", "coin": 0, "secret": 0}


@dataclass
class FramePulse:
    generation: int
    sequence: int
    asset_id: str
    width: int
    height: int
    timestamp_ms: int
    frame_digest: str
    pointers: tuple[str, ...] = ()
    cool: bool = False
    keyframe: bool = False

    def __post_init__(self) -> None:
        if self.generation < 1 or self.sequence < 0:
            raise OrganError("gen")
        if not _ID.fullmatch(self.asset_id):
            raise OrganError("asset")
        if self.width < 1 or self.height < 1:
            raise OrganError("pixel")
        if self.width * self.height > MAX_PIXELS:
            raise OrganError("pixel-cap")
        if self.timestamp_ms < 0 or self.timestamp_ms > MAX_DURATION_MS:
            raise OrganError("duration")
        if len(self.frame_digest) != 64 or any(ch not in "0123456789abcdef" for ch in self.frame_digest):
            raise OrganError("digest")
        if len(self.pointers) > N_CAP:
            raise OrganError("ncap")
        for p in self.pointers:
            if not p or " " in p or len(p) > 64:
                raise OrganError("pointer")


@dataclass
class Organ:
    """drop_17. Reversible frame bag. No stored sentence."""

    generation: int = 1
    closed: bool = False
    heat: float = 0.0
    dropped: int = 0
    accepted: int = 0
    root: str = "0" * 64
    chain: list[str] = field(default_factory=list)
    seen: set[str] = field(default_factory=set)
    bag: list[dict[str, Any]] = field(default_factory=list)
    last_pts: int = -1
    keyframes: int = 0
    open_gop: bool = False

    def snapshot(self) -> dict[str, Any]:
        return {
            "kind": "video-organ",
            "id": CAP_ID,
            "name": NAME,
            "family": FAMILY,
            "hit": 1,
            "law": "vol158-drop",
            "citation": "docs/lineage/video_vol158_batch320.md",
            "stored_prose": 0,
            "generation": self.generation,
            "heat": round(self.heat, 6),
            "dropped": self.dropped,
            "accepted": self.accepted,
            "root": self.root,
            "mass": len(self.bag),
            "keyframes": self.keyframes,
            "gate": GATE,
        }

    def observe(self) -> dict[str, Any]:
        card = self.snapshot()
        card["obs"] = ["heat", "dropped", "accepted", "root", "mass", "keyframes"]
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

    def _card(self, pulse: FramePulse, hit: int, reason: str, digest: str = "") -> dict[str, Any]:
        return {
            "kind": "video-pulse",
            "id": CAP_ID,
            "name": NAME,
            "hit": hit,
            "law": reason,
            "citation": "docs/lineage/video_vol158_batch320.md",
            "stored_prose": 0,
            "generation": pulse.generation,
            "sequence": pulse.sequence,
            "asset_id": pulse.asset_id,
            "timestamp_ms": pulse.timestamp_ms,
            "digest": digest,
            "root": self.root,
            "cool": 1 if pulse.cool else 0,
            "keyframe": 1 if pulse.keyframe else 0,
            "parent": PARENT,
        }

    def admit(self, pulse: FramePulse) -> dict[str, Any]:
        if self.closed:
            self.dropped += 1
            raise OrganError("terminal")
        if pulse.generation != self.generation:
            self.dropped += 1
            raise OrganError("stale-generation")
        if self.accepted >= MAX_FRAMES:
            self.dropped += 1
            raise OrganError("frame-budget")
        key = pulse.asset_id + ":" + str(pulse.sequence)
        if key in self.seen:
            self.dropped += 1
            raise OrganError("duplicate")
        if FAMILY == "clock" and pulse.timestamp_ms < self.last_pts:
            self.dropped += 1
            raise OrganError("pts-order")
        if FAMILY == "keyframe" and self.accepted == 0 and not pulse.keyframe:
            self.dropped += 1
            return self._card(pulse, 0, "keyframe-required")
        if FAMILY == "gop" and pulse.keyframe:
            self.open_gop = True
        if FAMILY == "segment" and pulse.timestamp_ms > MAX_DURATION_MS:
            self.dropped += 1
            raise OrganError("segment-oob")
        pixels = pulse.width * pulse.height
        self.heat = min(1.5, self.heat * 0.86 + (pixels / MAX_PIXELS) * HEAT)
        if self.heat >= 0.90 and not pulse.cool and not pulse.keyframe:
            self.dropped += 1
            return self._card(pulse, 0, "shunt")
        digest = _canon({
            "asset": pulse.asset_id,
            "pts": pulse.timestamp_ms,
            "seq": pulse.sequence,
            "digest": pulse.frame_digest,
            "ptr": list(pulse.pointers),
            "kf": pulse.keyframe,
        })
        self.seen.add(key)
        self.accepted += 1
        self.last_pts = pulse.timestamp_ms
        if pulse.keyframe:
            self.keyframes += 1
        self.root = _sha([self.root, digest, CAP_ID])
        self.chain.append(self.root)
        if len(self.chain) > 64:
            self.chain = self.chain[-64:]
        self.bag.append({
            "seq": pulse.sequence,
            "asset": pulse.asset_id,
            "pts": pulse.timestamp_ms,
            "digest": digest,
            "ptr": list(pulse.pointers)[:N_CAP],
            "kf": pulse.keyframe,
        })
        self._clip()
        return self._card(pulse, 1, "admit", digest)

    def reverse(self) -> dict[str, Any] | None:
        if not self.bag:
            return None
        last = self.bag.pop()
        self.accepted = max(0, self.accepted - 1)
        self.seen.discard(str(last["asset"]) + ":" + str(last["seq"]))
        if last.get("kf") and self.keyframes:
            self.keyframes -= 1
        if self.chain:
            self.chain.pop()
        self.root = self.chain[-1] if self.chain else "0" * 64
        self.last_pts = int(self.bag[-1]["pts"]) if self.bag else -1
        return last

    def replay(self) -> str:
        acc = "0" * 64
        for item in self.bag:
            acc = _sha([acc, str(item["digest"])])
        return acc

    def mix_score(self, sequence: int) -> float:
        raw = (sequence * 0x9E3779B1 + SEED) & 0xFFFFFFFF
        return (raw % 10000) / 10000.0

    def family_gate(self, pulse: FramePulse) -> dict[str, Any]:
        if not math.isfinite(self.heat):
            raise OrganError("heat")
        if FAMILY == "sample" and pulse.sequence > 64:
            self.dropped += 1
            return self._card(pulse, 0, "sample-budget")
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
        if FAMILY == "limit" and pulse.width * pulse.height > MAX_PIXELS:
            raise OrganError("decode-limit")
        return self.admit(pulse)

    def capabilities(self) -> dict[str, Any]:
        return {
            "owner": "video.vol158",
            "contract": contract(),
            "failure_modes": failure_modes(),
            "obs": ["heat", "dropped", "accepted", "root", "mass", "keyframes"],
            "security": security(),
        }
