"""Deterministic seed helper for pipelines — thread through RNGs.

Pipelines claim determinism; the seed helper wraps random.Random
instances and returns reproducible choice lists, plus a helper for
a new derived seed per stage so stages don't bleed into each other.

- :class:`SeedRegistry` — per-stage derived RNGs
"""

from __future__ import annotations

import hashlib
import random
from typing import Any, Callable, Dict, Optional, Sequence

from skeleton.kernel.errors import PipelineError


class SeedError(PipelineError):
    code = "PPL.SEED"


@dataclass
class StageSeed:
    stage: str
    seed: int


class SeedRegistry:
    """Root seed + deterministic per-stage derived seed (hash-based)."""

    def __init__(self, root_seed: int) -> None:
        self._root = root_seed
        self._seeds: Dict[str, int] = {}

    def seed_for(self, stage: str) -> int:
        if stage not in self._seeds:
            digest = hashlib.sha256(f"{self._root}:{stage}".encode()).hexdigest()
            self._seeds[stage] = int(digest[:8], 16)
        return self._seeds[stage]

    def rng_for(self, stage: str) -> random.Random:
        return random.Random(self.seed_for(stage))

    def root(self) -> int:
        return self._root
