"""FAC-PARS-0067. Facet parse/pointer. stored_prose=0. Live file not forked."""

from __future__ import annotations

import hashlib, json, math
from dataclasses import dataclass, field
from typing import Any

CAP_ID = "FAC-PARS-0067"
PLANE = "parse"
TOKEN = "pointer"
PACKET = "FACET-10240"
PARENT = "#80"
STORED_PROSE = 0
HEAT = 0.1
N_CAP = 8
MASS_CLIP = 1.1
COIN = 0

class OrganError(ValueError):
    pass

def _sha(parts: list[str]) -> str:
    return hashlib.sha256("|".join(parts).encode()).hexdigest()

def contract() -> dict[str, Any]:
    return {"id": CAP_ID, "plane": PLANE, "token": TOKEN, "heat": HEAT,
             "stored_prose": 0, "coin": 0, "parent": PARENT,
             "citation": "docs/lineage/facet_batch10240.md"}

def failure_modes() -> list[str]:
    return ["bad-token", "stale", "stimulus", "ncap", "coin", "heat"]

def security() -> dict[str, Any]:
    return {"network": 0, "torch": 0, "hf": 0, "ace": "fail-closed", "coin": 0}

@dataclass
class Pulse:
    generation: int
    sequence: int
    token: str
    pointers: tuple[str, ...] = ()
    cool: bool = False
    stimulus: str = ""
    coin: int = 0
    def __post_init__(self) -> None:
        if self.generation < 1 or self.sequence < 0:
            raise OrganError("gen")
        if self.token != TOKEN:
            raise OrganError("token")
        if self.stimulus:
            raise OrganError("stimulus")
        if self.coin:
            raise OrganError("coin")
        if len(self.pointers) > N_CAP:
            raise OrganError("ncap")

@dataclass
class Organ:
    generation: int = 1
    heat: float = 0.0
    dropped: int = 0
    accepted: int = 0
    root: str = "0" * 64
    chain: list[str] = field(default_factory=list)
    seen: set[str] = field(default_factory=set)
    bag: list[dict[str, Any]] = field(default_factory=list)

    def snapshot(self) -> dict[str, Any]:
        return {"kind": "facet-organ", "id": CAP_ID, "plane": PLANE, "token": TOKEN,
                 "hit": 1, "law": "facet-parse", "stored_prose": 0, "coin": 0,
                 "citation": "docs/lineage/facet_batch10240.md",
                 "heat": round(self.heat, 6), "dropped": self.dropped,
                 "accepted": self.accepted, "root": self.root, "mass": len(self.bag)}

    def observe(self) -> dict[str, Any]:
        card = self.snapshot()
        card["G"] = round(1.0 - min(self.heat, 1.0), 6)
        card["G0"] = 1.0
        card["G_delta"] = round(card["G"] - 1.0, 6)
        card["mass_hint"] = len(self.bag)
        return card

    def admit(self, pulse: Pulse) -> dict[str, Any]:
        if pulse.generation != self.generation:
            self.dropped += 1
            raise OrganError("stale-generation")
        key = pulse.token + ":" + str(pulse.sequence)
        if key in self.seen:
            self.dropped += 1
            raise OrganError("duplicate")
        self.heat = min(1.5, self.heat * 0.82 + HEAT)
        if self.heat >= 0.90 and not pulse.cool:
            self.dropped += 1
            return {"id": CAP_ID, "hit": 0, "law": "shunt", "stored_prose": 0, "plane": PLANE, "coin": 0}
        digest = hashlib.sha256(json.dumps({
            "plane": PLANE, "token": pulse.token, "ptr": list(pulse.pointers),
        }, sort_keys=True).encode()).hexdigest()
        self.seen.add(key)
        self.accepted += 1
        self.root = _sha([self.root, digest, CAP_ID])
        self.chain.append(self.root)
        if len(self.chain) > 32:
            self.chain = self.chain[-32:]
        self.bag.append({"seq": pulse.sequence, "digest": digest})
        limit = int(max(1, self.accepted) * MASS_CLIP) + 4
        if len(self.bag) > limit:
            self.bag = self.bag[-limit:]
        return {"id": CAP_ID, "hit": 1, "law": "admit", "stored_prose": 0,
                 "plane": PLANE, "digest": digest, "parent": PARENT, "coin": 0}

    def reverse(self):
        if not self.bag:
            return None
        last = self.bag.pop()
        self.accepted = max(0, self.accepted - 1)
        if self.chain:
            self.chain.pop()
        self.root = self.chain[-1] if self.chain else "0" * 64
        return last

    def capabilities(self) -> dict[str, Any]:
        return {"owner": PLANE, "contract": contract(), "failure_modes": failure_modes(), "security": security()}
