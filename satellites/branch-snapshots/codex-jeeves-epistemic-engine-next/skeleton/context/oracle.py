"""Magic 8-Ball on the 20 vertices of the dodecahedron.

Each vertex is a mouth. The roll is not uniform: vertex weight is the
mean activation of its five incident faces (dual of the icosa). A seed
derived from the tensor fingerprint makes the roll reproducible for a
given cube — cockpit may reseed.
"""
from __future__ import annotations

import hashlib
import struct
from dataclasses import dataclass
from typing import Dict, List, Sequence, Tuple

from skeleton.context.dodeca import ADJ, Dodecahedron, FACES
from skeleton.context.tensor import ContextTensor

# 20 canonical oracles — one per dodeca vertex. Tone is era-agnostic;
# the lattice chooses *which* mouth speaks.
MOUTHS: Tuple[str, ...] = (
    "Signs point to extraction — move now.",
    "Heat is the silent boss; respect the vent.",
    "Scavenge three parts before you greed a fourth.",
    "The elite TTK is honest. Yours may not be.",
    "Collapse is a clock, not a vibe.",
    "Jeeves would tell you to swap families.",
    "A kinetic shot is a vote against entropy.",
    "Do not sprint through a critical bar.",
    "Loot is a liability until it is a loadout.",
    "The authorial grain wants one more room. Decline.",
    "Opacity favours the player who already knows the layout.",
    "Spectacle is cheap; agency is the scarce good.",
    "Intimacy with the weapon beats intimacy with the lore.",
    "Grind only pays if the recipe graph is open.",
    "Reply hazy — check the tensor fingerprint.",
    "Outlook good if the snowball mass is past 0.6.",
    "Very doubtful: that forge wire has a type mismatch.",
    "As I see it, yes — bind the soulslike pack.",
    "Concentrate and ask the cockpit again.",
    "Better not tell you now: the helix is supercoiled.",
)

# Each vertex of a dodeca is incident to 3 faces; dual: each icosa vertex
# (our 12 faces) has degree 5. We assign 20 mouths to face-triples by
# walking ordered neighbour wedges so the mapping is stable.
def _vertex_faces() -> Tuple[Tuple[int, int, int], ...]:
    triples: List[Tuple[int, int, int]] = []
    seen = set()
    for u in range(12):
        nbrs = ADJ[u]
        for i, v in enumerate(nbrs):
            w = nbrs[(i + 1) % len(nbrs)]
            # only count a triangle once (u,v,w where u is smallest)
            if u < v and u < w and (v in ADJ[w] or w in ADJ[v]):
                key = tuple(sorted((u, v, w)))
                if key not in seen:
                    seen.add(key)
                    triples.append((u, v, w))
    # Icosa has 20 faces; we should have 20 triples. Pad/truncate defensively.
    while len(triples) < 20:
        triples.append(triples[len(triples) % max(len(triples), 1)] if triples else (0, 1, 2))
    return tuple(triples[:20])


VERTEX_FACES: Tuple[Tuple[int, int, int], ...] = _vertex_faces()


def _u32(seed: bytes) -> int:
    return struct.unpack(">I", seed[:4])[0]


@dataclass(frozen=True)
class OracleReading:
    index: int
    text: str
    faces: Tuple[str, str, str]
    weight: float
    seed: str

    def to_dict(self) -> Dict[str, object]:
        return {
            "index": self.index,
            "text": self.text,
            "faces": list(self.faces),
            "weight": round(self.weight, 4),
            "seed": self.seed,
        }


class Magic8Ball:
    def __init__(self, lattice: Dodecahedron, *, salt: str = "") -> None:
        self.lattice = lattice
        self.salt = salt
        self._weights = self._compute_weights()

    def _compute_weights(self) -> Tuple[float, ...]:
        act = self.lattice.activations
        raw = []
        for triple in VERTEX_FACES:
            raw.append(sum(act[i] for i in triple) / 3.0)
        total = sum(raw) or 1.0
        return tuple(x / total for x in raw)

    def _seed_bytes(self, tensor: ContextTensor, nonce: int = 0) -> bytes:
        material = f"{tensor.fingerprint()}|{self.salt}|{nonce}".encode()
        return hashlib.sha256(material).digest()

    def roll(self, tensor: ContextTensor, *, nonce: int = 0) -> OracleReading:
        seed = self._seed_bytes(tensor, nonce)
        pick = _u32(seed) / 2**32
        acc = 0.0
        idx = len(self._weights) - 1
        for i, w in enumerate(self._weights):
            acc += w
            if pick <= acc:
                idx = i
                break
        faces = tuple(FACES[j] for j in VERTEX_FACES[idx])  # type: ignore[assignment]
        return OracleReading(
            index=idx,
            text=MOUTHS[idx],
            faces=faces,  # type: ignore[arg-type]
            weight=self._weights[idx],
            seed=seed.hex()[:12],
        )

    def top(self, n: int = 5) -> List[Tuple[int, float, str]]:
        ranked = sorted(enumerate(self._weights), key=lambda iw: -iw[1])
        return [(i, w, MOUTHS[i]) for i, w in ranked[:n]]
