"""Four-axis critique (GB-43) and four-cell cockpit Monte Carlo (GB-44).

Live knobs are not written. Doctor cue is the weakest axis. No prose.
"""

from __future__ import annotations

import hashlib
from typing import Any, Mapping


AXES = ("fun", "clarity", "feasibility", "originality")
CELLS = ("heat", "extract", "sleep", "forge")
MAX_SAMPLES = 64


class CritiqueError(ValueError):
    """Critique / cockpit-MC contract violation."""


def _clamp(value: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CritiqueError("axis score must be numeric")
    if value < 0.0 or value > 1.0:
        raise CritiqueError("axis score must be in [0, 1]")
    return float(value)


def critique(scores: Mapping[str, Any] | None) -> dict[str, Any]:
    raw = dict(scores or {})
    axes = {name: _clamp(float(raw.get(name, 0.5))) for name in AXES}
    weakest = min(AXES, key=lambda name: axes[name])
    return {
        "kind": "critique",
        "axes": axes,
        "weakest": weakest,
        "doctor": weakest,
        "min": axes[weakest],
        "stored_prose": 0,
    }


def _cell_roll(seed: int, cell: str, sample: int) -> float:
    material = f"{int(seed)}:{cell}:{sample}:cockpit".encode("utf-8")
    n = int.from_bytes(hashlib.sha256(material).digest()[:8], "big")
    return (n % 10_001) / 10_000.0


def monte_carlo(*, seed: int, samples: int = 16) -> dict[str, Any]:
    if isinstance(samples, bool) or not isinstance(samples, int):
        raise CritiqueError("samples must be an integer")
    if samples < 1 or samples > MAX_SAMPLES:
        raise CritiqueError("samples out of range")
    cells: dict[str, list[float]] = {cell: [] for cell in CELLS}
    for i in range(samples):
        for cell in CELLS:
            cells[cell].append(_cell_roll(int(seed), cell, i))
    means = {cell: sum(values) / len(values) for cell, values in cells.items()}
    weakest = min(CELLS, key=lambda name: means[name])
    return {
        "kind": "balance",
        "seed": int(seed),
        "samples": samples,
        "means": means,
        "weakest": weakest,
        "retune": False,
        "stored_prose": 0,
    }


def improve(scores: Mapping[str, Any] | None, *, seed: int) -> dict[str, Any]:
    taste = critique(scores)
    balance = monte_carlo(seed=seed, samples=16)
    return {
        "kind": "improve",
        "critique": taste,
        "balance": balance,
        "doctor": taste["doctor"],
        "retune": False,
        "stored_prose": 0,
    }
