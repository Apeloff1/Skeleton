"""Deterministic sha256 merkle. No network. Leaves are pointers, not prose."""

from __future__ import annotations

import hashlib
from typing import Iterable, Sequence

from skeleton.primitives.cards import primitive_card
from skeleton.primitives.errors import MerkleError
from skeleton.primitives.law import CITATION


def _h(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def leaf_hash(item: str | bytes) -> str:
    if isinstance(item, str):
        item = item.encode("utf-8")
    return _h(b"leaf|" + item)


def pair_hash(left: str, right: str) -> str:
    a, b = (left, right) if left <= right else (right, left)
    return _h(b"node|" + a.encode("ascii") + b"|" + b.encode("ascii"))


def root_of(leaves: Sequence[str]) -> str:
    if not leaves:
        return _h(b"empty")
    layer = [leaf_hash(x) for x in leaves]
    while len(layer) > 1:
        nxt: list[str] = []
        it = iter(layer)
        for left in it:
            right = next(it, left)
            nxt.append(pair_hash(left, right))
        layer = nxt
    return layer[0]


def proof(leaves: Sequence[str], index: int) -> list[str]:
    if index < 0 or index >= len(leaves):
        raise MerkleError("index")
    layer = [leaf_hash(x) for x in leaves]
    idx = index
    out: list[str] = []
    while len(layer) > 1:
        if idx % 2 == 0:
            sib = layer[idx + 1] if idx + 1 < len(layer) else layer[idx]
        else:
            sib = layer[idx - 1]
        out.append(sib)
        nxt = []
        it = iter(layer)
        for left in it:
            right = next(it, left)
            nxt.append(pair_hash(left, right))
        layer = nxt
        idx //= 2
    return out


def verify(leaf: str, trail: Sequence[str], expected_root: str) -> bool:
    cur = leaf_hash(leaf)
    for sib in trail:
        cur = pair_hash(cur, sib)
    return cur == expected_root


def merkle_card(leaves: Iterable[str]) -> dict:
    seq = list(leaves)
    root = root_of(seq)
    return primitive_card(
        kind="merkle",
        hit=1 if root else 0,
        law="merkle present",
        citation=CITATION,
        extra={"root": root, "n": len(seq)},
    )
