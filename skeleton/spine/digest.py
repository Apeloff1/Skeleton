"""Structural digests: deterministic blake-like 16-hex fingerprints."""

from __future__ import annotations

import struct
from typing import Iterable, Sequence

from skeleton.spine.chain import SpineChain
from skeleton.spine.law import DIGEST_ALGO
from skeleton.spine.vertebra import Vertebra


def _rotl32(x: int, n: int) -> int:
    return ((x << n) | (x >> (32 - n))) & 0xFFFFFFFF


def _mix(h: int, v: int) -> int:
    h ^= v
    h = (h * 0x9E3779B1) & 0xFFFFFFFF
    h = _rotl32(h, 13)
    h = (h * 0xC2B2AE35) & 0xFFFFFFFF
    return h


def blake16(parts: Iterable[str], seed: int = 0xA5A5C3C3) -> str:
    """Tiny non-crypto digest → 16 hex chars. Deterministic."""
    h1 = seed & 0xFFFFFFFF
    h2 = (seed ^ 0x5A5A5A5A) & 0xFFFFFFFF
    count = 0
    for part in parts:
        data = part.encode("utf-8")
        for i in range(0, len(data), 4):
            chunk = data[i : i + 4]
            if len(chunk) < 4:
                chunk = chunk + b"\x00" * (4 - len(chunk))
            (v,) = struct.unpack("<I", chunk)
            if count % 2 == 0:
                h1 = _mix(h1, v)
            else:
                h2 = _mix(h2, v)
            count += 1
        h1 = _mix(h1, len(data))
    # finalize
    h1 ^= count
    h2 ^= (count * 0x85EBCA77) & 0xFFFFFFFF
    h1 = _mix(h1, h2)
    h2 = _mix(h2, h1)
    return f"{h1:08x}{h2:08x}"


def vertebra_digest(v: Vertebra) -> str:
    return blake16(v.digest_parts())


def chain_digest(chain: SpineChain) -> str:
    parts: list[str] = [DIGEST_ALGO, chain.name]
    for v in chain.vertebrae:
        parts.extend(v.digest_parts())
    for s in chain.segments:
        rel = s.relative.as_tuple()
        parts.append(s.label)
        parts.extend(f"{x:.4f}" for x in rel)
        parts.append("L" if s.locked else "M")
    return blake16(parts)


def digest_pair(chain: SpineChain) -> dict[str, str]:
    return {
        "algo": DIGEST_ALGO,
        "chain": chain_digest(chain),
        "cranial": vertebra_digest(chain.cranial()),
        "caudal": vertebra_digest(chain.caudal()),
    }


def digests_equal(a: SpineChain, b: SpineChain) -> bool:
    return chain_digest(a) == chain_digest(b)


def digest_drift(a: SpineChain, b: SpineChain) -> int:
    """Hamming distance over hex string (nibble-level)."""
    da, db = chain_digest(a), chain_digest(b)
    return sum(1 for x, y in zip(da, db) if x != y) + abs(len(da) - len(db))


def stable_neutral_digest() -> str:
    from skeleton.spine.chain import default_chain

    return chain_digest(default_chain("neutral"))


def assert_digest_format(d: str) -> None:
    if len(d) != 16 or any(c not in "0123456789abcdef" for c in d):
        raise AssertionError("digest-format")
