"""AI-tree fill laws. Fail closed. No coin. No stored sentence in the mesh."""

from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass, field
from typing import Iterable, Mapping, Sequence

MASS_SNOWBALL = 1.1
G_CLIP = 2.5
N_CAP = 8
POINTER_RE = re.compile(
    r"(https?://\S+|arxiv:\d{4}\.\d{4,5}|github\.com/\S+|VOL-\d+|AIFT-[A-Z0-9-]+|GB-\d+)",
    re.I,
)
SENTENCE_RE = re.compile(r"[A-Z][^.!?]{40,}[.!?]")


class LawBreak(RuntimeError):
    def __init__(self, law: str, detail: str) -> None:
        super().__init__(f"{law}: {detail}")
        self.law = law
        self.detail = detail


def sha256_hex(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def merkle_pair(left: str, right: str) -> str:
    return sha256_hex((left + right).encode("utf-8"))


def merkle_root(leaves: Sequence[str]) -> str:
    if not leaves:
        return sha256_hex(b"empty-root")
    layer = [sha256_hex(leaf.encode("utf-8")) for leaf in leaves]
    while len(layer) > 1:
        if len(layer) % 2 == 1:
            layer.append(layer[-1])
        layer = [merkle_pair(layer[i], layer[i + 1]) for i in range(0, len(layer), 2)]
    return layer[0]


def parse_pointers(stimulus: str, n_cap: int = N_CAP) -> list[str]:
    """Split stimulus into pointer clauses only. Sentences never enter the mesh."""
    if SENTENCE_RE.search(stimulus) and not POINTER_RE.search(stimulus):
        raise LawBreak("stored-prose", "stimulus carries a sentence and no pointer")
    found = POINTER_RE.findall(stimulus)
    clauses = []
    for raw in found:
        clause = raw.strip().rstrip(").,;")
        if clause and clause not in clauses:
            clauses.append(clause)
        if len(clauses) >= n_cap:
            break
    if not clauses:
        token = sha256_hex(stimulus.encode("utf-8"))[:16]
        clauses.append(f"ptr:{token}")
    return clauses[:n_cap]


def clip(value: float, lo: float, hi: float) -> float:
    if math.isnan(value) or math.isinf(value):
        raise LawBreak("numeric-clip", "non-finite value")
    return max(lo, min(hi, value))


@dataclass
class ClippedG:
    """G grows only through MHC * S with clips. A stamped G=10 without trajectory is illegal."""

    g0: float
    g: float
    mhc: float
    s: float
    trajectory: list[float] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.trajectory:
            raise LawBreak("gb-16", "stamped G without trajectory")
        if abs(self.g - self.trajectory[-1]) > 1e-9:
            raise LawBreak("gb-16", "G does not match trajectory tail")

    @property
    def delta(self) -> float:
        return self.g - self.g0

    def step(self, mhc: float, s: float) -> "ClippedG":
        grown = self.g + clip(mhc, -G_CLIP, G_CLIP) * clip(s, 0.0, 1.0)
        grown = clip(grown, 0.0, self.g0 + G_CLIP * max(1, len(self.trajectory)))
        trail = list(self.trajectory) + [grown]
        return ClippedG(self.g0, grown, mhc, s, trail)

    def card(self) -> dict:
        return {
            "G": self.g,
            "G0": self.g0,
            "G_delta": self.delta,
            "mhc": self.mhc,
            "S": self.s,
            "steps": len(self.trajectory),
            "law": "clipped-g",
        }


def mass_admit(prior: float, proposed: float) -> float:
    if prior < 0 or proposed < 0:
        raise LawBreak("mass-snowball", "negative mass")
    ceiling = prior * MASS_SNOWBALL if prior else proposed
    if proposed > ceiling + 1e-9:
        raise LawBreak("mass-snowball", f"{proposed} exceeds {ceiling}")
    return proposed


def era_bind(title: str, house_era: Mapping[str, str]) -> str:
    key = title.strip().lower()
    if key not in house_era:
        raise LawBreak("era-bind", f"unbound title {title}")
    return house_era[key]


def forbid_coin(payload: Mapping[str, object]) -> None:
    banned = {"coin", "token_mint", "chain_tx", "wallet"}
    hit = banned.intersection(payload)
    if hit:
        raise LawBreak("no-coin", ",".join(sorted(hit)))


def digest_card(card: Mapping[str, object]) -> str:
    blob = repr(sorted((str(k), repr(v)) for k, v in card.items())).encode("utf-8")
    return sha256_hex(blob)
