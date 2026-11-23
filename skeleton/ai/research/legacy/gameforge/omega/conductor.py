"""
Ω-ULTRA CONDUCTOR — production merge for AI systems (vΩ-Ultra).

Async, distributed, spacetime-aware fail-safe context/progress engine.
Extended for this backend with:
  • snapshot()  — JSON-friendly state for API responses
  • ConductorRegistry — in-process session manager keyed by role+id
"""
from __future__ import annotations

import asyncio
import hashlib
import math
import re
import statistics
import time
import uuid
from collections import Counter, deque
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple, Union


# ══════════════════════════════════════════════════════════════
# Exceptions
# ══════════════════════════════════════════════════════════════
class IntegrityError(Exception): ...
class RecoverableError(Exception): ...
class RepetitionError(Exception): ...
class ConsensusError(Exception): ...
class MarathonStateError(Exception): ...
class QueueOverflowError(Exception): ...

MAX_CONTENT_BYTES = 64 * 1024
MAX_SESSION_COMMITS = 4096
MAX_SESSIONS = 64
_MAX_SUBS = 256


# ══════════════════════════════════════════════════════════════
# Core Utilities
# ══════════════════════════════════════════════════════════════
def sha3(data: Union[str, bytes]) -> str:
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha3_256(data).hexdigest()


def now_ns() -> int:
    return time.perf_counter_ns()


def wall_ns() -> int:
    return time.time_ns()


def format_ns(ns: int) -> str:
    if ns < 1_000:
        return f"{ns} ns"
    if ns < 1_000_000:
        return f"{ns / 1_000:.2f} µs"
    if ns < 1_000_000_000:
        return f"{ns / 1_000_000:.2f} ms"
    s = ns / 1e9
    h, rem = divmod(int(s), 3600)
    m, sec = divmod(rem, 60)
    if h:
        return f"{h}h {m:02d}m {sec:02d}s"
    if m:
        return f"{m}m {sec:02d}s"
    return f"{sec}s"


# ══════════════════════════════════════════════════════════════
# 1. Hybrid Spacetime Clock
# ══════════════════════════════════════════════════════════════
@dataclass
class HybridClock:
    perf: int = 0
    wall: int = 0
    logical: int = 0
    vector: Dict[str, int] = field(default_factory=dict)
    entropy: float = 0.0

    def tick(self, node: str, ent: float = 0.0) -> "HybridClock":
        self.perf = now_ns()
        self.wall = wall_ns()
        self.logical += 1
        self.vector[node] = self.vector.get(node, 0) + 1
        self.entropy += ent
        return self

    def merge(self, other: "HybridClock") -> "HybridClock":
        self.logical = max(self.logical, other.logical) + 1
        for k, v in other.vector.items():
            self.vector[k] = max(self.vector.get(k, 0), v)
        self.entropy = max(self.entropy, other.entropy)
        self.perf = now_ns()
        self.wall = wall_ns()
        return self


# ══════════════════════════════════════════════════════════════
# 2. Causal DAG
# ══════════════════════════════════════════════════════════════
@dataclass
class CausalNode:
    id: str
    parents: List[str]
    clock: HybridClock
    progress: float
    spatial: Tuple[float, float, float, float]  # page, depth, branch, entropy
    content_hash: str
    full_content: Optional[str] = None
    page_id: Optional[str] = None


class CausalDAG:
    def __init__(self):
        self.nodes: Dict[str, CausalNode] = {}
        self.heads: Set[str] = set()
        self.root: Optional[str] = None
        self._content_order: deque[str] = deque()

    def add(self, node: CausalNode):
        for p in node.parents:
            if p not in self.nodes and p != "GENESIS":
                raise IntegrityError(f"Missing parent {p}")
        if node.id in self.nodes:
            raise IntegrityError("duplicate causal node")
        self.nodes[node.id] = node
        self._content_order.append(node.id)
        for p in node.parents:
            self.heads.discard(p)
        self.heads.add(node.id)
        if self.root is None:
            self.root = node.id

    def purge_old_content(self, keep: int = 5):
        while len(self._content_order) > keep:
            self.nodes[self._content_order.popleft()].full_content = None


# ══════════════════════════════════════════════════════════════
# 3. Merkle Tree
# ══════════════════════════════════════════════════════════════
class MerkleTree:
    """Incremental legacy duplicate-last tree with content inclusion proofs."""

    def __init__(self):
        self.leaves: List[str] = []
        self._layers: List[List[str]] = [self.leaves]
        self.root = "GENESIS_MERKLE"

    def append(self, leaf: str) -> str:
        if not isinstance(leaf, str) or not re.fullmatch(r"[0-9a-f]{64}", leaf):
            raise ValueError("invalid Merkle leaf digest")
        self.leaves.append(leaf)
        index = len(self.leaves) - 1
        layer_no = 0
        while len(self._layers[layer_no]) > 1:
            layer = self._layers[layer_no]
            parent = index // 2
            left = layer[parent * 2]
            right = layer[parent * 2 + 1] if parent * 2 + 1 < len(layer) else left
            value = sha3(left + right)
            layer_no += 1
            if len(self._layers) <= layer_no:
                self._layers.append([])
            upper = self._layers[layer_no]
            if parent == len(upper):
                upper.append(value)
            else:
                upper[parent] = value
            index = parent
        self.root = self._layers[layer_no][0]
        return self.root

    def proof(self, index: int) -> dict:
        if type(index) is not int or not 0 <= index < len(self.leaves):
            raise ValueError("invalid Merkle leaf index")
        original = index
        siblings = []
        for layer in self._layers:
            if len(layer) <= 1:
                break
            sibling = index ^ 1
            siblings.append(layer[sibling] if sibling < len(layer) else layer[index])
            index //= 2
        return {"index": original, "count": len(self.leaves),
                "leaf": self.leaves[original], "siblings": siblings, "root": self.root}

    @staticmethod
    def verify_proof(proof: dict, expected_root: str, expected_count: int) -> bool:
        try:
            index, count = proof["index"], proof["count"]
            current, siblings = proof["leaf"], proof["siblings"]
            if (type(index) is not int or type(count) is not int
                    or count != expected_count or not 0 <= index < count <= MAX_SESSION_COMMITS
                    or not isinstance(siblings, list) or len(siblings) > 16
                    or not re.fullmatch(r"[0-9a-f]{64}", current)):
                return False
            for sibling in siblings:
                if count <= 1 or not re.fullmatch(r"[0-9a-f]{64}", sibling):
                    return False
                if index % 2 == 0 and index + 1 == count and sibling != current:
                    return False
                current = sha3(sibling + current) if index % 2 else sha3(current + sibling)
                index //= 2
                count = (count + 1) // 2
            return count == 1 and current == expected_root == proof["root"]
        except (TypeError, KeyError, ValueError):
            return False


# ══════════════════════════════════════════════════════════════
# 4. Bloom + HyperLogLog (anti-repetition)
# ══════════════════════════════════════════════════════════════
class BloomFilter:
    def __init__(self, size: int = 1 << 20, hashes: int = 7):
        self.size = size
        self.hashes = hashes
        self.bits = bytearray(size // 8)

    def _idx(self, key: str) -> List[int]:
        h = sha3(key)
        return [int(h[i:i + 8], 16) % self.size for i in range(0, self.hashes * 8, 8)]

    def add(self, key: str):
        for i in self._idx(key):
            self.bits[i // 8] |= 1 << (i % 8)

    def __contains__(self, key: str) -> bool:
        return all(self.bits[i // 8] & (1 << (i % 8)) for i in self._idx(key))


class HyperLogLog:
    def __init__(self, b: int = 14):
        if type(b) is not int or not 4 <= b <= 16:
            raise ValueError("invalid HLL precision")
        self.b = b
        self.m = 1 << b
        self.reg = [0] * self.m

    def add(self, key: str):
        h = int(sha3(key)[:16], 16)
        idx = h & (self.m - 1)
        w = h >> self.b
        rank = 64 - self.b - w.bit_length() + 1
        self.reg[idx] = max(self.reg[idx], rank)

    def cardinality(self) -> float:
        z = sum(2.0 ** -r for r in self.reg)
        estimate = (0.7213 / (1 + 1.079 / self.m)) * self.m * self.m / z
        empty = self.reg.count(0)
        return self.m * math.log(self.m / empty) if empty and estimate <= 2.5 * self.m else estimate


# ══════════════════════════════════════════════════════════════
# 5. Kalman Predictor
# ══════════════════════════════════════════════════════════════
class KalmanProgress:
    def __init__(self):
        self.x = 0.0
        self.v = 0.0
        self.p = 1.0

    def predict(self, dt: float = 1.0):
        self.x += self.v * dt
        self.p += 0.008

    def update(self, z: float, r: float = 0.08):
        k = self.p / (self.p + r)
        self.x += k * (z - self.x)
        self.v = 0.85 * self.v + 0.15 * (z - self.x)
        self.p *= (1 - k)

    def eta(self, target: float) -> float:
        return float("inf") if self.v <= 1e-9 else max(0.0, (target - self.x) / self.v)


# ══════════════════════════════════════════════════════════════
# 6. TMR Clicker + Byzantine Consensus
# ══════════════════════════════════════════════════════════════
class TMRClicker:
    def __init__(self, total: float):
        self.total = float(total)
        self.vals = [0.0, 0.0, 0.0]
        self.clicks = [0, 0, 0]

    def advance(self, force: Optional[float] = None) -> float:
        target = min(force if force is not None else self.vals[0] + 1.0, self.total)
        self.vals = [target] * 3
        self.clicks = [c + 1 for c in self.clicks]
        return target

    @property
    def current(self) -> float:
        return statistics.median(self.vals)

    @property
    def click_count(self) -> int:
        return int(statistics.median(self.clicks))

    def percent(self) -> float:
        return 0.0 if self.total <= 0 else self.current / self.total * 100

    def reset(self):
        self.vals = [0.0] * 3
        self.clicks = [0] * 3


class ByzantineConsensus:
    """Compatibility facade over PROOD's local replica simulator, not a network quorum."""

    def __init__(self, node_id: str, n: int = 7, f: int | None = None):
        from gameforge.prood.quorum import QuorumConsensus
        self.node_id = node_id
        self.n = n
        self.f = (n - 1) // 3 if f is None else f
        self.seq = 0
        self._engine = QuorumConsensus(n=n, f=self.f)
        self.last_receipt = None

    async def agree(self, value: float, proof: str) -> float:
        receipt = self._engine.agree(value, proof=proof)
        self.last_receipt = receipt.to_dict()
        self.seq = receipt.seq
        if not receipt.decided:
            raise ConsensusError("local replica quorum failed")
        return value


# ══════════════════════════════════════════════════════════════
# 7. Async Queue Manager
# ══════════════════════════════════════════════════════════════
class AsyncQueueManager:
    def __init__(self, maxsize: int = 2048):
        self.q = {
            "context": asyncio.Queue(maxsize=maxsize),
            "response": asyncio.Queue(maxsize=maxsize),
            "audit": asyncio.Queue(maxsize=maxsize),
        }

    async def put(self, name: str, item: Any):
        try:
            self.q[name].put_nowait(item)
        except asyncio.QueueFull:
            raise QueueOverflowError(f"{name} queue full")

    async def get(self, name: str, timeout: float = 0.3) -> Any:
        try:
            return await asyncio.wait_for(self.q[name].get(), timeout)
        except asyncio.TimeoutError:
            return None


# ══════════════════════════════════════════════════════════════
# 8. Progress Bar
# ══════════════════════════════════════════════════════════════
class ProgressBar:
    def __init__(self, width: int = 42):
        self.width = width

    def render(self, pct: float, label: str = "") -> str:
        pct = max(0.0, min(100.0, pct))
        filled = int(round(pct / 100 * self.width))
        bar = "█" * filled + " " * (self.width - filled)
        return f"{label}[{bar}] {pct:6.2f}%"


# ══════════════════════════════════════════════════════════════
# 9. Invariant Guardian
# ══════════════════════════════════════════════════════════════
class InvariantGuardian:
    def __init__(self):
        self.checks = 0
        self.violations = 0

    async def run(self, cond: "OmegaUltraConductor"):
        while cond._active:
            self.checks += 1
            valid = (
                cond.global_seq == len(cond.dag.nodes) == len(cond.merkle.leaves) == len(cond._seen)
                and bool(cond.merkle.root)
                and all(c is not None and 0 <= c.current <= c.total
                        for c in (cond.clicker_ctx, cond.clicker_rsp))
            )
            if not valid:
                self.violations += 1
                cond._record_anomaly("invariant_failed")
                cond._active = False
                return
            await asyncio.sleep(0.25)


# ══════════════════════════════════════════════════════════════
# 10. MAIN ENGINE — Ω-ULTRA CONDUCTOR
# ══════════════════════════════════════════════════════════════
class OmegaUltraConductor:
    def __init__(self, node_id: str = "ai-node-0", n_nodes: int = 7, keep_full: int = 5):
        if not isinstance(node_id, str) or not 1 <= len(node_id) <= 160:
            raise ValueError("invalid conductor node identity")
        if type(keep_full) is not int or not 0 <= keep_full <= 8:
            raise ValueError("invalid full-content retention")
        self.node_id = node_id
        self.keep_full = keep_full
        self._active = False
        self._lock = asyncio.Lock()

        self.clock = HybridClock()
        self.dag = CausalDAG()
        self.merkle = MerkleTree()
        self.bloom = BloomFilter()
        self.hll = HyperLogLog()
        self.kalman = KalmanProgress()
        self.consensus = ByzantineConsensus(node_id, n=n_nodes)
        self.queues = AsyncQueueManager()
        self.guardian = InvariantGuardian()
        self.bar = ProgressBar()

        self.clicker_ctx: Optional[TMRClicker] = None
        self.clicker_rsp: Optional[TMRClicker] = None
        self.mode = "pages"
        self.total = 100.0
        self.global_seq = 0
        self._anomaly: List[str] = []
        self._tasks: List[asyncio.Task] = []
        self.superposition: List[float] = []
        self._seen: Set[str] = set()
        self._generation = 0

    def _record_anomaly(self, code: str) -> None:
        self._anomaly.append(code)
        del self._anomaly[:-64]

    async def _stop_guardian(self) -> None:
        self._active = False
        tasks, self._tasks = self._tasks, []
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    # ── Lifecycle ─────────────────────────────────────────────
    async def begin(self, mode: str = "pages", total: float = 100.0, fresh: bool = True) -> Dict:
        async with self._lock:
            if not isinstance(mode, str) or mode.lower() not in ("pages", "percent", "bar"):
                raise ValueError("mode must be pages | percent | bar")
            mode = mode.lower()
            if type(total) not in (int, float) or not math.isfinite(total) or not 0 < total <= 1e9:
                raise ValueError("invalid conductor total")
            total = 100.0 if mode == "bar" else float(total)
            if not fresh and self.clicker_ctx is not None:
                if (mode, total) != (self.mode, self.total):
                    raise ValueError("resume cannot change session parameters")
                if self.guardian.violations:
                    raise IntegrityError("session has invariant violations")
                if not self._active:
                    await self._stop_guardian()
                    self._active = True
                    self._tasks = [asyncio.create_task(self.guardian.run(self))]
                return self.snapshot("RESUMED")
            await self._stop_guardian()
            self.dag = CausalDAG()
            self.merkle = MerkleTree()
            self.bloom = BloomFilter()
            self.hll = HyperLogLog()
            self.kalman = KalmanProgress()
            self.clock = HybridClock()
            self.queues = AsyncQueueManager()
            self.guardian = InvariantGuardian()
            self.consensus = ByzantineConsensus(self.node_id, self.consensus.n, self.consensus.f)
            self._seen.clear()
            self._anomaly.clear()
            self.superposition.clear()
            self.mode, self.total = mode, total
            self.clicker_ctx = TMRClicker(total)
            self.clicker_rsp = TMRClicker(total)
            self.global_seq = 0
            self._generation += 1
            self._active = True
            self._tasks = [asyncio.create_task(self.guardian.run(self))]
            return self.snapshot("SESSION_ARMED")

    async def deliver_context(self, content: str, progress: Optional[float] = None,
                              depth: float = 0.0, branch: float = 0.0,
                              page_id: Optional[str] = None) -> Dict:
        return await self._deliver("context", content, progress, depth, branch, page_id)

    async def deliver_response(self, content: str, progress: Optional[float] = None,
                               depth: float = 0.0, branch: float = 0.0,
                               page_id: Optional[str] = None) -> Dict:
        return await self._deliver("response", content, progress, depth, branch, page_id)

    async def _deliver(self, side: str, content: str,
                       progress: Optional[float], depth: float, branch: float,
                       page_id: Optional[str]) -> Dict:
        async with self._lock:
            if not self._active:
                raise MarathonStateError("Call begin() first")
            if not isinstance(content, str) or not content or len(content.encode("utf-8")) > MAX_CONTENT_BYTES:
                raise ValueError("invalid emission content")
            if page_id is not None and (not isinstance(page_id, str) or not 1 <= len(page_id) <= 256):
                raise ValueError("invalid page identity")
            if any(type(value) not in (int, float) or not math.isfinite(value) or abs(value) > 1e9
                   for value in (depth, branch)):
                raise ValueError("invalid spatial coordinate")
            chash = sha3(content)
            if chash in self._seen:
                raise RepetitionError("duplicate content in this session generation")
            if self.global_seq >= MAX_SESSION_COMMITS:
                raise QueueOverflowError("session history capacity reached")
            if self.queues.q[side].full() or self.queues.q["audit"].full():
                raise QueueOverflowError("event queue backpressured")
            clicker = self.clicker_ctx if side == "context" else self.clicker_rsp
            assert clicker is not None
            if progress is None:
                candidate = min(self.total, clicker.current + 1.0)
            elif (type(progress) not in (int, float) or not math.isfinite(progress)
                  or not clicker.current <= progress <= self.total):
                raise ValueError("progress must be finite, monotonic and within total")
            else:
                candidate = float(progress)
            ent = -sum((count / len(content)) * math.log2(count / len(content))
                       for count in Counter(content).values())
            # Consensus refusal cannot mutate deduplication, clock, queues or
            # progress. It is not silently substituted with an unvoted value.
            committed = await self.consensus.agree(candidate, proof=chash)
            if committed != candidate:
                raise ConsensusError("local quorum returned an unexpected value")
            next_clock = HybridClock(**asdict(self.clock)).tick(self.node_id, ent)
            next_seq = self.global_seq + 1
            node_id = f"{self.node_id}-{self._generation}-{side}-{next_seq}"
            node = CausalNode(
                id=node_id, parents=sorted(self.dag.heads) or ["GENESIS"], clock=next_clock,
                progress=committed, spatial=(committed, depth, branch, ent),
                content_hash=chash, full_content=content, page_id=page_id or node_id,
            )
            # No suspension point after successful admission. Both queues have
            # been checked while the session lock is held.
            self.dag.add(node)
            self.dag.purge_old_content(self.keep_full)
            self.clock = next_clock
            self._seen.add(chash)
            self.bloom.add(chash)
            self.hll.add(chash)
            clicker.advance(force=committed)
            self.kalman.predict()
            self.kalman.update(committed)
            root = self.merkle.append(chash)
            self.queues.q[side].put_nowait({"node": node_id, "progress": committed, "seq": next_seq})
            self.queues.q["audit"].put_nowait({"side": side, "hash": chash, "merkle": root, "seq": next_seq})
            self.global_seq = next_seq
            return self.snapshot(f"{side.upper()} COMMITTED", last_node=node_id)

    async def drain(self, queue: str, limit: int = 128) -> List[dict]:
        if queue not in self.queues.q or type(limit) is not int or not 1 <= limit <= 256:
            raise ValueError("invalid drain request")
        async with self._lock:
            q = self.queues.q[queue]
            result = []
            for _ in range(limit):
                try:
                    item = q.get_nowait()
                except asyncio.QueueEmpty:
                    break
                q.task_done()
                result.append(item)
            return result

    async def proof(self, index: int) -> dict:
        async with self._lock:
            return {"generation": self._generation, **self.merkle.proof(index)}

    async def wipe_and_restart(self, mode: Optional[str] = None, total: Optional[float] = None) -> Dict:
        return await self.begin(mode if mode is not None else self.mode,
                                total if total is not None else self.total, fresh=True)

    async def end(self) -> Dict:
        async with self._lock:
            await self._stop_guardian()
            return self.snapshot("SESSION_ENDED")

    # ── Views ─────────────────────────────────────────────────
    def get_progress_bar(self, side: str = "context", width: int = 50) -> str:
        if side not in ("context", "response") or type(width) is not int or not 1 <= width <= 200:
            raise ValueError("invalid progress bar request")
        clicker = self.clicker_ctx if side == "context" else self.clicker_rsp
        return ProgressBar(width).render(clicker.percent() if clicker else 0.0, f"{side[:3].upper()} ")

    def snapshot(self, event: str = "STATUS", last_node: Optional[str] = None) -> Dict:
        """JSON-friendly state for API responses."""
        c, r = self.clicker_ctx, self.clicker_rsp
        eta = self.kalman.eta(self.total)
        return {
            "event": event,
            "node_id": self.node_id,
            "active": self._active,
            "mode": self.mode,
            "total": self.total,
            "last_node": last_node,
            "clock": {"logical": self.clock.logical, "entropy": round(self.clock.entropy, 4)},
            "causal_nodes": len(self.dag.nodes),
            "heads": len(self.dag.heads),
            "merkle_root": self.merkle.root,
            "unique_estimate": len(self._seen),
            "generation": self._generation,
            "session_capacity": MAX_SESSION_COMMITS,
            "queue_depths": {name: queue.qsize() for name, queue in self.queues.q.items()},
            "consensus_scope": "in_process_replica_simulation",
            "durable_session": False,
            "merkle_scope": "content_digest_inclusion",
            "kalman_eta": "∞" if eta == float("inf") else format_ns(int(eta * 1e9)),
            "context": {
                "current": round(c.current, 3) if c else 0.0,
                "percent": round(c.percent(), 2) if c else 0.0,
                "clicks": c.click_count if c else 0,
                "bar": self.get_progress_bar("context"),
            },
            "response": {
                "current": round(r.current, 3) if r else 0.0,
                "percent": round(r.percent(), 2) if r else 0.0,
                "clicks": r.click_count if r else 0,
                "bar": self.get_progress_bar("response"),
            },
            "global_seq": self.global_seq,
            "guardian": {"checks": self.guardian.checks, "violations": self.guardian.violations},
            "anomalies": list(self._anomaly[-10:]),
            "guarantees": [
                "session-local-exact-deduplication", "causal-order", "local-quorum-simulation",
                "bounded-content-retention", "monotonic-progress", "generation-isolation",
                "bounded-queues", "kalman-prediction", "content-inclusion-proofs",
            ],
        }


# ══════════════════════════════════════════════════════════════
# Specialised AI-ready wrappers
# ══════════════════════════════════════════════════════════════
class AgentToAgentConductor(OmegaUltraConductor):
    """Pure agent ↔ agent context exchange."""
    async def handoff(self, content: str, **kwargs) -> Dict:
        return await self.deliver_context(content, **kwargs)


class OrchestratorConductor(OmegaUltraConductor):
    """Central coordinator that can attach sub-conductors (mastermap/agent-map)."""
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.subs: Dict[str, OmegaUltraConductor] = {}

    def attach(self, name: str, conductor: OmegaUltraConductor):
        if not isinstance(name, str) or not 1 <= len(name) <= 160:
            raise ValueError("invalid attachment identity")
        if name in self.subs or len(self.subs) >= _MAX_SUBS or conductor is self:
            raise ValueError("attachment conflict or capacity reached")
        self.subs[name] = conductor

    def sub_summary(self) -> Dict:
        return {name: sub.snapshot("SUB") for name, sub in self.subs.items()}


class UserToJeevesConductor(OmegaUltraConductor):
    """Natural-language user requests + long-form Jeeves generation."""
    async def interpret_and_begin(self, user_text: str) -> Dict:
        text = user_text.lower()
        mode = ("bar" if any(w in text for w in ("bar", "progress bar", "visual"))
                else "percent" if "%" in text or "percent" in text
                else "pages")
        total = 100.0 if mode != "pages" else 12.0
        nums = re.findall(r"\d+", text)
        if nums and mode == "pages":
            total = float(nums[0])
        return await self.begin(mode, total, fresh=True)

    async def user_message(self, content: str, **kw) -> Dict:
        return await self.deliver_context(content, **kw)

    async def jeeves_reply(self, content: str, **kw) -> Dict:
        return await self.deliver_response(content, **kw)


# ══════════════════════════════════════════════════════════════
# Session Registry — in-process, role-aware
# ══════════════════════════════════════════════════════════════
_ROLE_MAP = {
    "context": OmegaUltraConductor,
    "agent": OmegaUltraConductor,
    "agent2agent": AgentToAgentConductor,
    "orchestrator": OrchestratorConductor,
    "mastermap": OrchestratorConductor,
    "agentmap": OrchestratorConductor,
    "jeeves": UserToJeevesConductor,
}


@dataclass
class _Session:
    session_id: str
    role: str
    conductor: OmegaUltraConductor
    created_at: float


class ConductorRegistry:
    def __init__(self):
        self._sessions: Dict[str, _Session] = {}

    @staticmethod
    def roles() -> List[str]:
        return sorted(_ROLE_MAP.keys())

    def create(self, role: str, node_id: Optional[str] = None) -> _Session:
        role = role.lower()
        cls = _ROLE_MAP.get(role)
        if cls is None:
            raise ValueError(f"unknown role '{role}' — valid: {self.roles()}")
        if len(self._sessions) >= MAX_SESSIONS:
            raise QueueOverflowError("session registry capacity reached")
        sid = uuid.uuid4().hex
        node = node_id or f"{role}-{sid}"
        sess = _Session(sid, role, cls(node_id=node), time.time())
        self._sessions[sid] = sess
        return sess

    def get(self, session_id: str) -> Optional[_Session]:
        return self._sessions.get(session_id)

    def list(self) -> List[Dict]:
        return [
            {"session_id": s.session_id, "role": s.role, "node_id": s.conductor.node_id,
             "active": s.conductor._active, "global_seq": s.conductor.global_seq,
             "created_at": s.created_at}
            for s in sorted(self._sessions.values(), key=lambda x: -x.created_at)
        ]

    def drop(self, session_id: str) -> bool:
        session = self._sessions.get(session_id)
        if session is None:
            return False
        if session.conductor._active:
            raise MarathonStateError("end session before removal")
        for other in self._sessions.values():
            if isinstance(other.conductor, OrchestratorConductor):
                for name, child in list(other.conductor.subs.items()):
                    if child is session.conductor:
                        other.conductor.subs.pop(name)
        self._sessions.pop(session_id)
        return True


conductor_registry = ConductorRegistry()
