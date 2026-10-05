"""DNA double helix — Watson (operator) / Crick (system) conversation strand.

Each pipeline stage is one helical turn. The operator utterance is
transcribed into a 16-base Watson codon; the system commit into Crick.
Complementarity (A↔T, G↔C) is scored; GC content drives melting
temperature; twist + writhe yield linking number. The cockpit may nick
(drop Lk by 1) or ligate (restore). Supercoiling σ = (Lk - Lk0) / Lk0.
"""
from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

NUC = "ACGT"
COMP = {"A": "T", "T": "A", "G": "C", "C": "G"}
BP_PER_TURN = 10  # classical B-DNA is 10.5; we snap to 10 for integer Tw


def transcribe(text: str, *, length: int = 16) -> str:
    digest = hashlib.sha256((text or "").encode()).digest()
    return "".join(NUC[b % 4] for b in digest[:length])


def complement(codon: str) -> str:
    return "".join(COMP.get(b, "N") for b in codon)


def gc_content(codon: str) -> float:
    if not codon:
        return 0.0
    return sum(1 for b in codon if b in "GC") / len(codon)


def complementarity(w: str, c: str) -> float:
    n = min(len(w), len(c))
    if n == 0:
        return 0.0
    return sum(1 for i in range(n) if COMP.get(w[i]) == c[i]) / n


@dataclass
class BasePair:
    turn: int
    stage: str
    watson: str
    crick: str
    operator: str
    system: str

    @property
    def gc(self) -> float:
        return gc_content(self.watson + self.crick)

    @property
    def paired(self) -> float:
        return complementarity(self.watson, self.crick)

    def to_dict(self) -> Dict[str, object]:
        return {
            "turn": self.turn,
            "stage": self.stage,
            "watson": self.watson,
            "crick": self.crick,
            "operator": self.operator[:120],
            "system": self.system[:120],
            "gc": round(self.gc, 3),
            "complementarity": round(self.paired, 3),
        }


@dataclass
class DNAHelix:
    pairs: List[BasePair] = field(default_factory=list)
    nicked: int = 0  # cumulative nicks the cockpit has opened

    def pair(self, stage: str, operator: str, system: str) -> BasePair:
        w = transcribe(operator)
        c = transcribe(system)
        bp = BasePair(turn=len(self.pairs) + 1, stage=stage,
                      watson=w, crick=c, operator=operator, system=system)
        self.pairs.append(bp)
        return bp

    @property
    def turns(self) -> int:
        return len(self.pairs)

    @property
    def twist(self) -> float:
        # Tw ≈ N / 10
        bases = sum(len(p.watson) for p in self.pairs)
        return bases / BP_PER_TURN

    @property
    def writhe(self) -> float:
        # Wr from mean complementarity drift + nicks
        if not self.pairs:
            return 0.0
        mean_p = sum(p.paired for p in self.pairs) / len(self.pairs)
        return (0.5 - mean_p) * self.twist - self.nicked

    @property
    def linking_number(self) -> float:
        return self.twist + self.writhe

    @property
    def lk0(self) -> float:
        return self.twist  # relaxed B-DNA

    @property
    def supercoiling(self) -> float:
        if self.lk0 == 0:
            return 0.0
        return (self.linking_number - self.lk0) / self.lk0

    def nick(self) -> None:
        self.nicked += 1

    def ligate(self) -> None:
        self.nicked = max(0, self.nicked - 1)

    def melting_temp(self) -> float:
        """Wallace-rule-ish: 2(A+T)+4(G+C) averaged across turns."""
        if not self.pairs:
            return 0.0
        temps = []
        for p in self.pairs:
            seq = p.watson
            at = sum(1 for b in seq if b in "AT")
            gc = sum(1 for b in seq if b in "GC")
            temps.append(2 * at + 4 * gc)
        return sum(temps) / len(temps)

    def crossover(self, other: "DNAHelix", cut: Optional[int] = None) -> "DNAHelix":
        cut = cut if cut is not None else min(len(self.pairs), len(other.pairs)) // 2
        child = DNAHelix()
        child.pairs = list(self.pairs[:cut]) + list(other.pairs[cut:])
        return child

    def to_dict(self) -> Dict[str, object]:
        return {
            "turns": self.turns,
            "twist": round(self.twist, 3),
            "writhe": round(self.writhe, 3),
            "linking_number": round(self.linking_number, 3),
            "supercoiling": round(self.supercoiling, 4),
            "nicked": self.nicked,
            "Tm": round(self.melting_temp(), 2),
            "pairs": [p.to_dict() for p in self.pairs],
        }
