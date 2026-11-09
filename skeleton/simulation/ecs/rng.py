"""Deterministic, serialisable random streams for simulation logic.

Python's :mod:`random` is deterministic for a seed but its internal state is
large, version-coupled and awkward to hash into replay evidence.  Game logic
here uses **xoshiro256\\*\\*** (Blackman & Vigna) seeded through
**SplitMix64**: four 64-bit words of state, bit-exact across platforms and
Python versions, trivially snapshotted.

Independent sub-streams are derived by label (:meth:`DeterministicRng.fork`)
so adding a new consumer never perturbs the numbers an existing system draws.
"""
from __future__ import annotations

import hashlib
from collections.abc import Mapping, MutableSequence, Sequence
from typing import Any, TypeVar

from .errors import ValidationError

_MASK64 = (1 << 64) - 1
T = TypeVar("T")


def _splitmix64(state: int) -> tuple[int, int]:
    state = (state + 0x9E3779B97F4A7C15) & _MASK64
    z = state
    z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & _MASK64
    z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & _MASK64
    return state, z ^ (z >> 31)


def _rotl(x: int, k: int) -> int:
    return ((x << k) | (x >> (64 - k))) & _MASK64


def seed_from(value: Any) -> int:
    """Map an ``int`` or ``str`` seed onto 64 bits deterministically."""
    if isinstance(value, bool):
        raise ValidationError("rng seed must be int or str")
    if isinstance(value, int):
        return value & _MASK64
    if isinstance(value, str):
        return int.from_bytes(hashlib.sha256(value.encode("utf-8")).digest()[:8], "big")
    raise ValidationError("rng seed must be int or str", context={"type": type(value).__name__})


class DeterministicRng:
    __slots__ = ("_s",)

    def __init__(self, seed: int | str = 0) -> None:
        state = seed_from(seed)
        words = []
        for _ in range(4):
            state, word = _splitmix64(state)
            words.append(word)
        if not any(words):  # the all-zero state is a fixed point
            words[0] = 1
        self._s = words

    # -- core generator ----------------------------------------------------
    def next_u64(self) -> int:
        s = self._s
        result = (_rotl((s[1] * 5) & _MASK64, 7) * 9) & _MASK64
        t = (s[1] << 17) & _MASK64
        s[2] ^= s[0]
        s[3] ^= s[1]
        s[1] ^= s[2]
        s[0] ^= s[3]
        s[2] ^= t
        s[3] = _rotl(s[3], 45)
        return result

    def next_u32(self) -> int:
        return self.next_u64() >> 32

    def random(self) -> float:
        """Uniform float in ``[0, 1)`` with 53 bits of precision."""
        return (self.next_u64() >> 11) * (1.0 / (1 << 53))

    def uniform(self, low: float, high: float) -> float:
        if not isinstance(low, (int, float)) or not isinstance(high, (int, float)) or isinstance(low, bool) or isinstance(high, bool):
            raise ValidationError("uniform bounds must be numbers")
        return low + (high - low) * self.random()

    def randint(self, low: int, high: int) -> int:
        """Uniform integer in ``[low, high]`` (inclusive) without modulo bias."""
        for value in (low, high):
            if isinstance(value, bool) or not isinstance(value, int):
                raise ValidationError("randint bounds must be integers")
        if high < low:
            raise ValidationError("randint high must be >= low")
        span = high - low + 1
        if span > (1 << 64):
            raise ValidationError("randint span exceeds 64 bits")
        if span & (span - 1) == 0:
            return low + (self.next_u64() & (span - 1))
        limit = (1 << 64) - ((1 << 64) % span)
        while True:
            draw = self.next_u64()
            if draw < limit:
                return low + draw % span

    def chance(self, probability: float) -> bool:
        if isinstance(probability, bool) or not isinstance(probability, (int, float)) or not 0.0 <= probability <= 1.0:
            raise ValidationError("chance probability must be within [0, 1]")
        return self.random() < probability

    def choice(self, items: Sequence[T]) -> T:
        if not items:
            raise ValidationError("choice from empty sequence")
        return items[self.randint(0, len(items) - 1)]

    def shuffle(self, items: MutableSequence[Any]) -> None:
        for i in range(len(items) - 1, 0, -1):
            j = self.randint(0, i)
            items[i], items[j] = items[j], items[i]

    def weighted_index(self, weights: Sequence[float]) -> int:
        total = 0.0
        for w in weights:
            if isinstance(w, bool) or not isinstance(w, (int, float)) or w < 0:
                raise ValidationError("weights must be non-negative numbers")
            total += w
        if total <= 0:
            raise ValidationError("weights must not all be zero")
        point = self.random() * total
        acc = 0.0
        for index, w in enumerate(weights):
            acc += w
            if point < acc:
                return index
        return len(weights) - 1

    # -- streams -----------------------------------------------------------
    def fork(self, label: str) -> DeterministicRng:
        """Derive an independent stream from the *current* state and a label.

        Forking does not advance this stream.
        """
        if not isinstance(label, str) or not label:
            raise ValidationError("fork label must be non-empty text")
        material = b"".join(w.to_bytes(8, "big") for w in self._s) + label.encode("utf-8")
        return DeterministicRng(int.from_bytes(hashlib.sha256(material).digest()[:8], "big"))

    # -- persistence -------------------------------------------------------
    def state(self) -> list[int]:
        return list(self._s)

    def set_state(self, state: Sequence[int]) -> None:
        words = list(state)
        if len(words) != 4 or any(isinstance(w, bool) or not isinstance(w, int) or not 0 <= w <= _MASK64 for w in words):
            raise ValidationError("rng state must be four unsigned 64-bit integers")
        if not any(words):
            raise ValidationError("rng state must not be all zero")
        self._s = words

    @classmethod
    def from_state(cls, state: Sequence[int]) -> DeterministicRng:
        rng = cls(0)
        rng.set_state(state)
        return rng

    def to_record(self) -> Mapping[str, Any]:
        return {"algorithm": "xoshiro256**", "state": self.state()}


__all__ = ["DeterministicRng", "seed_from"]
