"""DV640-223 conflict_23. Family conflict. VOL-155 completion. stored_prose=0.

Aligns with skeleton/document_vision/fusion.py page, region, and fusion laws.
Span text is hashed. The sentence is not stored. fusion.py is not forked.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass, field
from typing import Any

CAP_ID = "DV640-223"
NAME = "conflict_23"
FAMILY = "conflict"
PACKET = "DV-640"
PARENT = "#80"
STORED_PROSE = 0
N_CAP = 7
HEAT = 0.3
SEED = 2408088815
GATE = "region-mismatch"
MAX_PAGE = 4096
MAX_EDGE = 8000
MASS_CLIP = 1.1
_ID = re.compile(r"^[A-Z][A-Z0-9_.:-]{2,127}$")
FAILURE_MODES = ("bad-page", "bad-digest", "region-oob", "confidence", "mismatch", GATE)

class OrganError(ValueError):
    """Fail-closed document-vision rejection. Pointers only."""


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
        "citation": "docs/lineage/document_vision_vol155_batch640.md",
        "gate": GATE,
        "max_page": MAX_PAGE,
    }


def failure_modes() -> list[str]:
    return list(FAILURE_MODES)


def security() -> dict[str, Any]:
    return {"network": 0, "torch": 0, "hf": 0, "ace": "fail-closed", "coin": 0, "secret": 0}


@dataclass
class SpanPulse:
    generation: int
    sequence: int
    document_id: str
    page: int
    x: int
    y: int
    width: int
    height: int
    page_width: int
    page_height: int
    render_digest: str
    confidence: float
    pointers: tuple[str, ...] = ()
    cool: bool = False
    agree: bool = True

    def __post_init__(self) -> None:
        if self.generation < 1 or self.sequence < 0:
            raise OrganError("gen")
        if not _ID.fullmatch(self.document_id):
            raise OrganError("page")
        if self.page < 1 or self.page > MAX_PAGE:
            raise OrganError("page")
        if min(self.page_width, self.page_height, self.width, self.height) < 1:
            raise OrganError("bounds")
        if max(self.page_width, self.page_height, self.width, self.height) > MAX_EDGE:
            raise OrganError("bounds")
        if self.x < 0 or self.y < 0 or self.x + self.width > self.page_width or self.y + self.height > self.page_height:
            raise OrganError("region-oob")
        if len(self.render_digest) != 64 or any(ch not in "0123456789abcdef" for ch in self.render_digest):
            raise OrganError("digest")
        if not math.isfinite(self.confidence) or not 0.0 <= self.confidence <= 1.0:
            raise OrganError("confidence")
        if len(self.pointers) > N_CAP:
            raise OrganError("ncap")
        for p in self.pointers:
            if not p or " " in p or len(p) > 64:
                raise OrganError("pointer")


@dataclass
class Organ:
    """conflict_23. Reversible span bag. No stored sentence."""

    generation: int = 1
    closed: bool = False
    heat: float = 0.0
    dropped: int = 0
    accepted: int = 0
    conflicts: int = 0
    root: str = "0" * 64
    chain: list[str] = field(default_factory=list)
    seen: set[str] = field(default_factory=set)
    bag: list[dict[str, Any]] = field(default_factory=list)

    def snapshot(self) -> dict[str, Any]:
        return {
            "kind": "vision-organ",
            "id": CAP_ID,
            "name": NAME,
            "family": FAMILY,
            "hit": 1,
            "law": "vol155-conflict",
            "citation": "docs/lineage/document_vision_vol155_batch640.md",
            "stored_prose": 0,
            "generation": self.generation,
            "heat": round(self.heat, 6),
            "dropped": self.dropped,
            "accepted": self.accepted,
            "conflicts": self.conflicts,
            "root": self.root,
            "mass": len(self.bag),
            "gate": GATE,
        }

    def observe(self) -> dict[str, Any]:
        card = self.snapshot()
        card["obs"] = ["heat", "dropped", "accepted", "conflicts", "root", "mass"]
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

    def _card(self, pulse: SpanPulse, hit: int, reason: str, digest: str = "") -> dict[str, Any]:
        return {
            "kind": "vision-pulse",
            "id": CAP_ID,
            "name": NAME,
            "hit": hit,
            "law": reason,
            "citation": "docs/lineage/document_vision_vol155_batch640.md",
            "stored_prose": 0,
            "generation": pulse.generation,
            "sequence": pulse.sequence,
            "document_id": pulse.document_id,
            "page": pulse.page,
            "digest": digest,
            "root": self.root,
            "cool": 1 if pulse.cool else 0,
            "agree": 1 if pulse.agree else 0,
            "parent": PARENT,
        }

    def admit(self, pulse: SpanPulse) -> dict[str, Any]:
        if self.closed:
            self.dropped += 1
            raise OrganError("terminal")
        if pulse.generation != self.generation:
            self.dropped += 1
            raise OrganError("stale-generation")
        key = pulse.document_id + ":" + str(pulse.page) + ":" + str(pulse.sequence)
        if key in self.seen:
            self.dropped += 1
            raise OrganError("duplicate")
        if FAMILY == "conflict" and not pulse.agree:
            self.conflicts += 1
            self.dropped += 1
            return self._card(pulse, 0, "region-mismatch")
        if FAMILY == "confidence" and pulse.confidence < 0.15 and not pulse.cool:
            self.dropped += 1
            return self._card(pulse, 0, "confidence")
        area = pulse.width * pulse.height
        page_area = pulse.page_width * pulse.page_height
        self.heat = min(1.5, self.heat * 0.87 + (area / page_area) * HEAT + (1.0 - pulse.confidence) * 0.05)
        if self.heat >= 0.90 and not pulse.cool:
            self.dropped += 1
            return self._card(pulse, 0, "shunt")
        digest = _canon({
            "doc": pulse.document_id,
            "page": pulse.page,
            "box": [pulse.x, pulse.y, pulse.width, pulse.height],
            "render": pulse.render_digest,
            "conf": round(pulse.confidence, 4),
            "ptr": list(pulse.pointers),
            "agree": pulse.agree,
        })
        self.seen.add(key)
        self.accepted += 1
        self.root = _sha([self.root, digest, CAP_ID])
        self.chain.append(self.root)
        if len(self.chain) > 64:
            self.chain = self.chain[-64:]
        self.bag.append({
            "seq": pulse.sequence,
            "doc": pulse.document_id,
            "page": pulse.page,
            "digest": digest,
            "ptr": list(pulse.pointers)[:N_CAP],
            "agree": pulse.agree,
        })
        self._clip()
        return self._card(pulse, 1, "admit", digest)

    def reverse(self) -> dict[str, Any] | None:
        if not self.bag:
            return None
        last = self.bag.pop()
        self.accepted = max(0, self.accepted - 1)
        self.seen.discard(str(last["doc"]) + ":" + str(last["page"]) + ":" + str(last["seq"]))
        if self.chain:
            self.chain.pop()
        self.root = self.chain[-1] if self.chain else "0" * 64
        return last

    def replay(self) -> str:
        acc = "0" * 64
        for item in self.bag:
            acc = _sha([acc, str(item["digest"])])
        return acc

    def family_gate(self, pulse: SpanPulse) -> dict[str, Any]:
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
        if FAMILY == "pointer" and not pulse.pointers:
            raise OrganError("ncap")
        return self.admit(pulse)

    def capabilities(self) -> dict[str, Any]:
        return {
            "owner": "document_vision.vol155",
            "contract": contract(),
            "failure_modes": failure_modes(),
            "obs": ["heat", "dropped", "accepted", "conflicts", "root", "mass"],
            "security": security(),
        }
