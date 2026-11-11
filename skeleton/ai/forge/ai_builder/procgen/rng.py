"""Seeded named substreams for the generators.

Reuses ``skeleton.simulation.ecs.rng.DeterministicRng`` (xoshiro256** seeded
through SplitMix64, bit-exact across platforms) for the numbers, and the FLGB
``SeedContract`` (skeleton.game.generation.seed_contract) to derive a stable
per-substream digest. A substream is addressed by a slash path such as
``"dungeon/locks"``; asking for one never advances another, so adding a new
consumer does not perturb what existing generators draw.
"""
from __future__ import annotations

import hashlib
import re
from typing import Any

from skeleton.game.generation.seed_contract import GenerationContractError, SeedContract
from skeleton.simulation.ecs.rng import DeterministicRng

from .errors import ProcgenError

GENERATOR_VERSION = "forge.procgen.v2"
_NAME = re.compile(r"^[a-z][a-z0-9_.-]{0,47}(/[a-z0-9][a-z0-9_.-]{0,47}){0,7}$")


def root_digest(seed: int | str) -> str:
    if isinstance(seed, bool) or not isinstance(seed, (int, str)):
        raise ProcgenError("seed must be int or str")
    if isinstance(seed, str) and (not seed or len(seed) > 1024):
        raise ProcgenError("seed must be non-empty and bounded")
    if isinstance(seed, int) and seed.bit_length() > 256:
        raise ProcgenError("seed integer exceeds bounded width")
    return hashlib.sha256(f"{type(seed).__name__}:{seed}".encode("utf-8")).hexdigest()


class Streams:
    """Factory for independent, reproducible random streams."""

    def __init__(self, seed: int | str, *, project_id: str = "forge-procgen",
                 _root: str | None = None) -> None:
        self.seed = seed
        try:
            self.contract = SeedContract(project_id, _root or root_digest(seed), GENERATOR_VERSION)
        except GenerationContractError as exc:
            raise ProcgenError(str(exc)) from exc
        self._issued: dict[str, str] = {}

    @property
    def root(self) -> str:
        return self.contract.root_seed_digest

    def digest(self, name: str) -> str:
        if not isinstance(name, str) or not _NAME.match(name):
            raise ProcgenError(f"invalid substream name {name!r}")
        domain, _, identity = name.partition("/")
        d = self.contract.derive(domain, identity or "root")
        self._issued[name] = d
        return d

    def stream(self, name: str) -> DeterministicRng:
        """A fresh generator for ``name``; the same name always restarts the same sequence."""
        return DeterministicRng(int(self.digest(name)[:16], 16))

    def child(self, name: str) -> "Streams":
        """A nested namespace whose root is this namespace's ``name`` digest."""
        return Streams(self.seed, project_id=self.contract.project_id, _root=self.digest(name))

    def issued(self) -> dict[str, str]:
        """Names handed out so far and the first 16 hex of their digests (provenance)."""
        return {k: v[:16] for k, v in sorted(self._issued.items())}

    def as_dict(self) -> dict[str, Any]:
        return {"generator_version": GENERATOR_VERSION, "root": self.root[:16], "streams": self.issued()}


def gauss(rng: DeterministicRng, mu: float = 0.0, sigma: float = 1.0) -> float:
    """Box-Muller on the deterministic stream (no reliance on :mod:`random`)."""
    import math
    if (not all(type(v) in (int, float) and math.isfinite(v) for v in (mu, sigma))
            or sigma < 0):
        raise ProcgenError("invalid finite Gaussian distribution")
    # Never busy-loop forever if an untrusted or broken RNG emits zero.
    u1 = 0.0
    for _ in range(64):
        u1 = rng.random()
        if type(u1) in (int, float) and math.isfinite(u1) and 1e-300 < u1 < 1.0:
            break
    else:
        raise ProcgenError("Gaussian generator failed bounded sample admission")
    u2 = rng.random()
    if type(u2) not in (int, float) or not math.isfinite(u2) or not 0.0 <= u2 < 1.0:
        raise ProcgenError("invalid Gaussian generator sample")
    return mu + sigma * math.sqrt(-2.0 * math.log(u1)) * math.cos(2.0 * math.pi * u2)
