"""Clip, pointer, era, merkle. No stored prose."""

from __future__ import annotations

import hashlib
import struct
from dataclasses import dataclass, field

MASS_CLIP = 1.1
STORED_PROSE = 0
N_CAP = 8
SEED_FAMILY = 8847291

class VolumeFault(ValueError):
    pass

@dataclass(frozen=True)
class PointerClause:
    house: str
    organ: str
    verb: str
    ordinal: int
    def key(self) -> str:
        return f"{self.house}/{self.organ}/{self.verb}#{self.ordinal}"

@dataclass
class MassState:
    prior: float
    current: float
    iteration: int
    trajectory: list[float] = field(default_factory=list)
    def clip(self, proposed: float) -> float:
        if self.prior <= 0:
            raise VolumeFault("prior")
        ceiling = self.prior * MASS_CLIP
        if proposed < 0:
            raise VolumeFault("mass")
        if proposed > ceiling:
            proposed = ceiling
        self.current = proposed
        self.iteration += 1
        self.trajectory.append(proposed)
        self.prior = proposed
        return proposed

def clip_mass(proposed: float, prior: float) -> float:
    return MassState(prior=prior, current=prior, iteration=0).clip(proposed)

def pointer_hash(clause: PointerClause, seed: int = SEED_FAMILY) -> str:
    return hashlib.sha256(f"{clause.key()}|{seed}|prose={STORED_PROSE}".encode()).hexdigest()

def merkle_leaf(clause: PointerClause, mass: float, seed: int = SEED_FAMILY) -> bytes:
    return hashlib.sha256(clause.key().encode() + struct.pack(">dQ", float(mass), seed & 0xFFFFFFFFFFFFFFFF)).digest()

def merkle_root(leaves: list[bytes]) -> str:
    if not leaves:
        raise VolumeFault("empty")
    layer = list(leaves)
    while len(layer) > 1:
        if len(layer) % 2 == 1:
            layer.append(layer[-1])
        layer = [hashlib.sha256(layer[i] + layer[i + 1]).digest() for i in range(0, len(layer), 2)]
    return layer[0].hex()

def split_pointer(stimulus: str, cap: int = N_CAP) -> list[str]:
    raw = [tok for tok in stimulus.replace(",", " ").split() if tok]
    return [tok for tok in raw if "://" in tok or "/" in tok or tok.startswith("GB-")][:cap]
