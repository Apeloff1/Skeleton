"""
Skeleton Contexts — Backlog Context

Marks unfinished work, stores it in tensor cubes, and seals it into
a blockchain that gets mined while the system is idle.

Three layers:

1. BacklogContext — the fixed-size plane of deferred/incomplete work
2. TensorCube   — NxNxN priority-density cube per backlog batch;
                  position encodes (priority, age, connector class),
                  so the next-best item is a cube argmax, not a scan
3. WorkChain    — append-only blockchain of sealed work blocks;
                  a background miner seals pending cubes into blocks
                  whenever the system is idle

"""

from __future__ import annotations

import hashlib
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from skeleton.kernel.events import DomainEvent, EventBus


BACKLOG_SIZE = 32  # same size as other context planes
CUBE_DIM = 4       # 4x4x4 tensor cube per batch


@dataclass
class BacklogItem:
    """A unit of unfinished work."""
    item_id: str
    kind: str  # spilled_order | failed_order | deferred_plan | interrupted
    payload: Dict[str, Any] = field(default_factory=dict)
    priority: float = 1.0
    age_cycles: int = 0
    deferred_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "item_id": self.item_id,
            "kind": self.kind,
            "priority": round(self.priority, 3),
            "age_cycles": self.age_cycles,
        }


class TensorCube:
    """4x4x4 priority-density cube over a batch of backlog items.

    Axes: (priority_band, age_band, connector_band). The cell value is
    the summed priority of items in that band. argmax() yields the
    band holding the most urgent unfinished work.
    """

    def __init__(self, dim: int = CUBE_DIM):
        self.dim = dim
        self._cells: List[List[List[float]]] = [
            [[0.0] * dim for _ in range(dim)] for _ in range(dim)
        ]
        self._count = 0

    @staticmethod
    def _band(value: float, lo: float, hi: float, dim: int) -> int:
        if hi <= lo:
            return 0
        return min(dim - 1, max(0, int((value - lo) / (hi - lo) * dim)))

    def insert(self, item: BacklogItem, max_priority: float = 10.0,
               max_age: float = 64.0, connector_idx: int = 0) -> None:
        p = self._band(item.priority, 0.0, max_priority, self.dim)
        a = self._band(float(item.age_cycles), 0.0, max_age, self.dim)
        c = min(self.dim - 1, connector_idx)
        self._cells[p][a][c] += item.priority
        self._count += 1

    def argmax(self) -> Tuple[int, int, int, float]:
        """Coordinates + value of the densest (most urgent) cell."""
        best = (0, 0, 0, -1.0)
        for p in range(self.dim):
            for a in range(self.dim):
                for c in range(self.dim):
                    v = self._cells[p][a][c]
                    if v > best[3]:
                        best = (p, a, c, v)
        return best

    def density(self) -> float:
        total = sum(v for plane in self._cells for row in plane for v in row)
        return total / max(1, self._count)

    def to_dict(self) -> Dict[str, Any]:
        p, a, c, v = self.argmax()
        return {"dim": self.dim, "items": self._count, "density": round(self.density(), 3),
                "hottest_band": {"priority": p, "age": a, "connector": c, "weight": round(v, 3)}}


@dataclass
class WorkBlock:
    """A sealed block of backlog work on the chain."""
    index: int
    sealed_at: float
    cube_snapshot: Dict[str, Any]
    item_ids: List[str]
    prev_hash: str
    nonce: int = 0
    block_hash: str = ""

    def compute_hash(self) -> str:
        body = f"{self.index}|{self.sealed_at}|{self.item_ids}|{self.prev_hash}|{self.nonce}"
        return hashlib.sha256(body.encode()).hexdigest()


class WorkChain:
    """Append-only blockchain of sealed backlog cubes, mined while idle."""

    def __init__(self, difficulty: int = 2):
        self._chain: List[WorkBlock] = []
        self._difficulty = difficulty  # leading zeros required
        self._mine_genesis()

    def _mine_genesis(self) -> None:
        block = WorkBlock(index=0, sealed_at=time.time(), cube_snapshot={},
                          item_ids=[], prev_hash="0" * 64)
        block.block_hash = block.compute_hash()
        self._chain.append(block)

    @property
    def tip(self) -> WorkBlock:
        return self._chain[-1]

    def _valid(self, block: WorkBlock) -> bool:
        return block.compute_hash().startswith("0" * self._difficulty)

    def seal(self, cube: TensorCube, item_ids: List[str], max_nonce: int = 100_000) -> WorkBlock:
        """Mine a new block sealing a cube snapshot (proof of work)."""
        block = WorkBlock(
            index=self.tip.index + 1,
            sealed_at=time.time(),
            cube_snapshot=cube.to_dict(),
            item_ids=item_ids,
            prev_hash=self.tip.block_hash,
        )
        while not self._valid(block) and block.nonce < max_nonce:
            block.nonce += 1
        block.block_hash = block.compute_hash()
        self._chain.append(block)
        return block

    def verify(self) -> bool:
        for i in range(1, len(self._chain)):
            cur, prev = self._chain[i], self._chain[i - 1]
            if cur.prev_hash != prev.block_hash:
                return False
            if cur.compute_hash() != cur.block_hash:
                return False
        return True

    def stats(self) -> Dict[str, Any]:
        return {"blocks": len(self._chain), "difficulty": self._difficulty,
                "tip_hash": self.tip.block_hash[:16]}


class BacklogContext:
    """Fixed-size plane of unfinished work with cube + chain storage."""

    def __init__(self, bus: Optional[EventBus] = None, chain_difficulty: int = 2):
        self._bus = bus
        self.items: List[BacklogItem] = []
        self.cubes: List[TensorCube] = []
        self.chain = WorkChain(difficulty=chain_difficulty)
        self._miner: Optional[threading.Thread] = None
        self._mine_event = threading.Event()
        self._stats = {"deferred": 0, "resumed": 0, "cubes_built": 0, "blocks_sealed": 0}

    def defer(self, work: Any, kind: str = "spilled_order") -> BacklogItem:
        """Mark work as unfinished and store it."""
        item = BacklogItem(
            item_id=getattr(work, "order_id", None) or str(uuid.uuid4())[:10],
            kind=kind,
            payload=getattr(work, "payload", {}) or {},
            priority=getattr(work, "priority", 1.0),
        )
        if len(self.items) >= BACKLOG_SIZE:
            self._archive_oldest()
        self.items.append(item)
        self._stats["deferred"] += 1
        if self._bus:
            self._bus.emit("contexts.backlog.deferred", {"item_id": item.item_id, "kind": kind})
        return item

    def resume_next(self) -> Optional[BacklogItem]:
        """Pop the highest-priority unfinished item."""
        if not self.items:
            return None
        best = max(self.items, key=lambda i: (i.priority, -i.age_cycles))
        self.items.remove(best)
        self._stats["resumed"] += 1
        return best

    def age_all(self) -> None:
        for item in self.items:
            item.age_cycles += 1

    def build_cube(self) -> TensorCube:
        """Fold current backlog into a tensor cube."""
        cube = TensorCube()
        for item in self.items:
            cube.insert(item)
        self.cubes.append(cube)
        self._stats["cubes_built"] += 1
        return cube

    def _archive_oldest(self) -> None:
        """Plane full: cube the oldest half and mark it for sealing."""
        oldest = sorted(self.items, key=lambda i: i.deferred_at)[: BACKLOG_SIZE // 2]
        for item in oldest:
            self.items.remove(item)
        cube = TensorCube()
        for item in oldest:
            cube.insert(item)
        self.cubes.append(cube)
        self._stats["cubes_built"] += 1

    # --- Idle mining ---------------------------------------------------------

    def start_idle_miner(self, idle_seconds: float = 1.0) -> None:
        """Background thread: seal cubes into blocks while idle."""
        if self._miner is not None:
            return

        def _mine() -> None:
            while not self._mine_event.is_set():
                if self.cubes:
                    cube = self.cubes.pop(0)
                    block = self.chain.seal(cube, [i.item_id for i in self.items])
                    self._stats["blocks_sealed"] += 1
                    if self._bus:
                        self._bus.publish(DomainEvent(
                            topic="contexts.backlog.sealed",
                            payload={"block": block.index, "hash": block.block_hash[:12]},
                        ))
                else:
                    self._mine_event.wait(idle_seconds)

        self._miner = threading.Thread(target=_mine, daemon=True)
        self._miner.start()

    def stop_idle_miner(self) -> None:
        self._mine_event.set()
        self._miner = None

    def summary(self) -> Dict[str, Any]:
        return {
            "backlog": len(self.items),
            "capacity": BACKLOG_SIZE,
            "cubes_pending": len(self.cubes),
            "chain": self.chain.stats(),
            "chain_valid": self.chain.verify(),
            **self._stats,
        }
