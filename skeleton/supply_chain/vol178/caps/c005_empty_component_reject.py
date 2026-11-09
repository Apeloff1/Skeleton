"""SC160-005 empty_component_reject. Family identity. VOL-178 completion. stored_prose=0.

Aligns with skeleton/supply_chain/sbom.py scopes and severities.
Does not fork sbom.py or model_bom.py.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field
from typing import Any

CAP_ID = "SC160-005"
NAME = "empty_component_reject"
FAMILY = "identity"
PACKET = "SC-160"
PARENT = "#80"
STORED_PROSE = 0
N_CAP = 4
HEAT = 0.17
SEED = 2636827737
SCOPES = ("direct", "transitive", "native", "container")
SEVERITIES = ("unknown", "low", "medium", "high", "critical")
STATUSES = ("open", "accepted-risk", "fixed", "not-affected")
FAILURE_MODES = ['empty-id', 'duplicate-id', 'token-space', 'id-cap']
MASS_CLIP = 1.1

class OrganError(ValueError):
    """Fail-closed supply-chain rejection. Pointers only."""


def _mix(a: int, b: int) -> int:
    return (a * 0x9E3779B1 + b * 0x85EBCA77 + SEED) & 0xFFFFFFFF


def _sha(parts: list[str]) -> str:
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def _canon(obj: object) -> str:
    try:
        blob = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise OrganError("canon") from exc
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _hex64(value: str) -> str:
    if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise OrganError("digest")
    return value


def _hex40(value: str) -> str:
    if len(value) != 40 or any(ch not in "0123456789abcdef" for ch in value):
        raise OrganError("revision")
    return value


def contract() -> dict[str, Any]:
    return {
        "id": CAP_ID,
        "name": NAME,
        "family": FAMILY,
        "n_cap": N_CAP,
        "heat": HEAT,
        "stored_prose": 0,
        "parent": PARENT,
        "citation": "docs/lineage/supply_chain_vol178_batch160.md",
        "scopes": list(SCOPES),
        "format": "cyclonedx-json",
    }


def failure_modes() -> list[str]:
    return list(FAILURE_MODES)


def security() -> dict[str, Any]:
    return {"network": 0, "torch": 0, "hf": 0, "ace": "fail-closed", "coin": 0, "secret": 0}


@dataclass
class ComponentPulse:
    generation: int
    sequence: int
    component_id: str
    scope: str
    severity: str
    status: str
    digest: str
    revision: str
    pointers: tuple[str, ...] = ()
    cool: bool = False

    def __post_init__(self) -> None:
        if self.generation < 1 or self.sequence < 0:
            raise OrganError("gen")
        if not self.component_id or " " in self.component_id or len(self.component_id) > 64:
            raise OrganError("component")
        if self.scope not in SCOPES:
            raise OrganError("scope")
        if self.severity not in SEVERITIES:
            raise OrganError("severity")
        if self.status not in STATUSES:
            raise OrganError("status")
        _hex64(self.digest)
        _hex40(self.revision)
        if len(self.pointers) > N_CAP:
            raise OrganError("ncap")
        for p in self.pointers:
            if not p or " " in p or len(p) > 64:
                raise OrganError("pointer")


@dataclass
class Organ:
    """empty_component_reject. Reversible component bag. No stored sentence."""

    generation: int = 1
    closed: bool = False
    heat: float = 0.0
    dropped: int = 0
    accepted: int = 0
    root: str = "0" * 64
    chain: list[str] = field(default_factory=list)
    seen: set[str] = field(default_factory=set)
    bag: list[dict[str, Any]] = field(default_factory=list)
    scopes_seen: set[str] = field(default_factory=set)
    risk: int = 0

    def snapshot(self) -> dict[str, Any]:
        return {
            "kind": "supply-organ",
            "id": CAP_ID,
            "name": NAME,
            "family": FAMILY,
            "hit": 1,
            "law": "vol178-identity",
            "citation": "docs/lineage/supply_chain_vol178_batch160.md",
            "stored_prose": 0,
            "generation": self.generation,
            "heat": round(self.heat, 6),
            "dropped": self.dropped,
            "accepted": self.accepted,
            "root": self.root,
            "mass": len(self.bag),
            "scopes": sorted(self.scopes_seen),
            "risk": self.risk,
        }

    def observe(self) -> dict[str, Any]:
        card = self.snapshot()
        card["obs"] = ["heat", "dropped", "accepted", "root", "mass", "risk"]
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

    def coverage(self) -> tuple[str, ...]:
        return tuple(s for s in SCOPES if s not in self.scopes_seen)

    def _clip(self) -> None:
        prior = max(1, self.accepted)
        limit = int(prior * MASS_CLIP) + 8
        if len(self.bag) > limit:
            self.bag = self.bag[-limit:]

    def _card(self, pulse: ComponentPulse, hit: int, reason: str, digest: str = "") -> dict[str, Any]:
        return {
            "kind": "supply-pulse",
            "id": CAP_ID,
            "name": NAME,
            "hit": hit,
            "law": reason,
            "citation": "docs/lineage/supply_chain_vol178_batch160.md",
            "stored_prose": 0,
            "generation": pulse.generation,
            "sequence": pulse.sequence,
            "scope": pulse.scope,
            "severity": pulse.severity,
            "status": pulse.status,
            "digest": digest,
            "root": self.root,
            "cool": 1 if pulse.cool else 0,
            "parent": PARENT,
        }

    def admit(self, pulse: ComponentPulse) -> dict[str, Any]:
        if self.closed:
            self.dropped += 1
            raise OrganError("terminal")
        if pulse.generation != self.generation:
            self.dropped += 1
            raise OrganError("stale-generation")
        key = pulse.component_id + ":" + str(pulse.sequence)
        if key in self.seen:
            self.dropped += 1
            raise OrganError("duplicate")
        rank = SEVERITIES.index(pulse.severity)
        self.heat = min(1.5, self.heat * 0.84 + (0.05 + rank * 0.08) * HEAT)
        if pulse.severity == "critical" and pulse.status == "accepted-risk":
            self.dropped += 1
            raise OrganError("critical-block")
        if self.heat >= 0.90 and not pulse.cool and pulse.severity in ("high", "critical"):
            self.dropped += 1
            return self._card(pulse, 0, "shunt")
        if FAMILY == "scope" and pulse.scope in self.scopes_seen and pulse.sequence > 2:
            self.dropped += 1
            return self._card(pulse, 0, "scope-dup")
        if FAMILY == "policy" and pulse.status == "accepted-risk":
            self.risk += 1
            if self.risk > 3:
                self.dropped += 1
                raise OrganError("risk-cap")
        if FAMILY == "closure" and pulse.sequence > 24:
            self.dropped += 1
            return self._card(pulse, 0, "depth")
        if FAMILY == "container" and pulse.scope != "container" and pulse.sequence == 0:
            return self._card(pulse, 0, "image-scope")
        digest = _canon({
            "id": pulse.component_id,
            "scope": pulse.scope,
            "severity": pulse.severity,
            "status": pulse.status,
            "digest": pulse.digest,
            "revision": pulse.revision,
            "ptr": list(pulse.pointers),
        })
        if FAMILY == "digest" and digest == pulse.digest:
            pass
        self.seen.add(key)
        self.scopes_seen.add(pulse.scope)
        self.accepted += 1
        self.root = _sha([self.root, digest, CAP_ID])
        self.chain.append(self.root)
        if len(self.chain) > 64:
            self.chain = self.chain[-64:]
        self.bag.append({
            "seq": pulse.sequence,
            "id": pulse.component_id,
            "scope": pulse.scope,
            "severity": pulse.severity,
            "status": pulse.status,
            "digest": digest,
            "revision": pulse.revision,
            "ptr": list(pulse.pointers)[:N_CAP],
        })
        self._clip()
        return self._card(pulse, 1, "admit", digest)

    def reverse(self) -> dict[str, Any] | None:
        if not self.bag:
            return None
        last = self.bag.pop()
        self.accepted = max(0, self.accepted - 1)
        self.seen.discard(str(last["id"]) + ":" + str(last["seq"]))
        if self.chain:
            self.chain.pop()
        self.root = self.chain[-1] if self.chain else "0" * 64
        return last

    def replay(self) -> str:
        acc = "0" * 64
        for item in self.bag:
            acc = _sha([acc, str(item["digest"])])
        return acc

    def rank(self, severity: str) -> int:
        return SEVERITIES.index(severity)

    def mix_score(self, sequence: int) -> float:
        return (_mix(self.generation, sequence) % 10000) / 10000.0

    def family_gate(self, pulse: ComponentPulse) -> dict[str, Any]:
        if not math.isfinite(self.heat):
            raise OrganError("heat")
        if FAMILY == "revision":
            _hex40(pulse.revision)
        if FAMILY == "purl" and any(":" not in p for p in pulse.pointers):
            raise OrganError("purl")
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
            "owner": "supply_chain.vol178",
            "contract": contract(),
            "failure_modes": failure_modes(),
            "obs": ["heat", "dropped", "accepted", "root", "mass", "risk"],
            "security": security(),
        }
