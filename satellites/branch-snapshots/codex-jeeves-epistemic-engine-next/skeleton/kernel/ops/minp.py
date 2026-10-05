"""Min-p / typical / eta sampling — obscure decoders.

Deterministic mass pick. No RNG. House path stays repeatable.
"""
from __future__ import annotations

import math
from typing import List, Sequence

from skeleton.kernel.ops._stat import bump


def _mass(logits: Sequence[float], temp: float) -> List[float]:
    t = max(1e-6, float(temp))
    m = max(logits)
    ex = [math.exp((v - m) / t) for v in logits]
    z = sum(ex) or 1.0
    return [e / z for e in ex]


def min_p(logits: Sequence[float], *, p: float = 0.05, temp: float = 1.0) -> int:
    if not logits:
        return 0
    probs = _mass(logits, temp)
    peak = max(probs)
    floor = max(0.0, float(p)) * peak
    keep = [i for i, pr in enumerate(probs) if pr >= floor] or [max(range(len(probs)), key=lambda i: probs[i])]
    pick = keep[max(range(len(keep)), key=lambda j: probs[keep[j]])]
    bump(1)
    return pick


def typical(logits: Sequence[float], *, mass: float = 0.2, temp: float = 1.0) -> int:
    if not logits:
        return 0
    probs = _mass(logits, temp)
    ent = -sum(pr * math.log(pr + 1e-12) for pr in probs)
    dev = [abs(-math.log(pr + 1e-12) - ent) for pr in probs]
    order = sorted(range(len(probs)), key=lambda i: dev[i])
    acc = 0.0
    keep = []
    want = max(0.01, min(1.0, float(mass)))
    for i in order:
        keep.append(i)
        acc += probs[i]
        if acc >= want:
            break
    pick = keep[max(range(len(keep)), key=lambda j: probs[keep[j]])]
    bump(1)
    return pick
