"""Rendezvous (highest-random-weight) hashing for kernel partitioning.

When the kernel shards work across agents — event topics, memory
partitions, vault shards — it needs a placement function that is:

- stable: removing one node remaps only that node's keys,
- uniform: keys spread evenly without central coordination,
- stateless: any node can compute the same placement independently.

Rendezvous hashing beats mod-N here because there's no reshuffle when
the roster changes. This module also provides virtual nodes to smooth
small-cluster variance, and a ``PartitionMap`` that answers owner(),
replicas(), and diff() (which keys move when the roster changes).

Zero deps, deterministic across processes (hashlib only).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from .errors import KernelError


class PartitionError(KernelError):
    code = "KRN.PARTITION"


def _digest(seed: str) -> int:
    return int.from_bytes(hashlib.blake2b(seed.encode(), digest_size=8).digest(), "big")


class RendezvousHash:
    """HRW over a roster of node ids, with virtual nodes for uniformity."""

    def __init__(self, nodes: Iterable[str], *, vnodes: int = 64) -> None:
        roster = tuple(sorted(set(nodes)))
        if not roster:
            raise PartitionError("rendezvous hash needs at least one node")
        if vnodes < 1:
            raise PartitionError("vnodes must be >= 1", context={"vnodes": vnodes})
        self.nodes: Tuple[str, ...] = roster
        self.vnodes = vnodes
        # (weight-seed suffix, owner) — weight computed per key on demand
        self._points: Tuple[Tuple[str, str], ...] = tuple(
            (f"{node}#{i}", node) for node in roster for i in range(vnodes)
        )

    def rank(self, key: str, *, k: Optional[int] = None) -> List[str]:
        """Nodes owning ``key``, best first."""
        scored = sorted(
            self._points,
            key=lambda p: _digest(f"{key}|{p[0]}"),
            reverse=True,
        )
        out: List[str] = []
        seen = set()
        for _, owner in scored:
            if owner not in seen:
                seen.add(owner)
                out.append(owner)
                if k is not None and len(out) >= k:
                    break
        return out if k is not None else out

    def owner(self, key: str) -> str:
        return self.rank(key, k=1)[0]

    def replicas(self, key: str, n: int) -> Tuple[str, ...]:
        if n > len(self.nodes):
            raise PartitionError(
                "replica count exceeds roster size",
                context={"replicas": n, "roster": len(self.nodes)},
            )
        return tuple(self.rank(key, k=n))


@dataclass(frozen=True)
class RebalancePlan:
    gained: Dict[str, Tuple[str, ...]]   # node -> keys it newly owns
    lost: Dict[str, Tuple[str, ...]]     # node -> keys it stops owning
    moved: int
    total: int


class PartitionMap:
    """Diffing wrapper: compare placements across roster changes."""

    def __init__(self, nodes: Iterable[str], *, vnodes: int = 64) -> None:
        self.hash = RendezvousHash(nodes, vnodes=vnodes)

    @property
    def nodes(self) -> Tuple[str, ...]:
        return self.hash.nodes

    def evolve(self, nodes: Iterable[str]) -> "PartitionMap":
        return PartitionMap(nodes, vnodes=self.hash.vnodes)

    def diff(self, keys: Iterable[str], other: "PartitionMap") -> RebalancePlan:
        """Which keys change owner when moving from self -> other."""
        gained: Dict[str, List[str]] = {}
        lost: Dict[str, List[str]] = {}
        moved = 0
        total = 0
        for key in keys:
            total += 1
            old = self.hash.owner(key)
            new = other.hash.owner(key)
            if old != new:
                moved += 1
                gained.setdefault(new, []).append(key)
                lost.setdefault(old, []).append(key)
        return RebalancePlan(
            gained={k: tuple(v) for k, v in gained.items()},
            lost={k: tuple(v) for k, v in lost.items()},
            moved=moved,
            total=total,
        )

    def distribution(self, keys: Iterable[str]) -> Dict[str, int]:
        counts: Dict[str, int] = {n: 0 for n in self.hash.nodes}
        for key in keys:
            counts[self.hash.owner(key)] += 1
        return counts
