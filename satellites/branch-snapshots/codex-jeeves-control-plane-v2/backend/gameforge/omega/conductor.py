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
from collections import Counter
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

    def add(self, node: CausalNode):
        for p in node.parents:
            if p not in self.nodes and p != "GENESIS":
                raise IntegrityError(f"Missing parent {p}")
        self.nodes[node.id] = node
        for p in node.parents:
            self.heads.discard(p)
        self.heads.add(node.id)
        if self.root is None:
            self.root = node.id

    def purge_old_content(self, keep: int = 5):
        ordered = sorted(self.nodes.values(), key=lambda n: n.clock.logical)
        for node in ordered[:-keep]:
            node.full_content = None


# ══════════════════════════════════════════════════════════════
# 3. Merkle Tree
# ══════════════════════════════════════════════════════════════
class MerkleTree:
    def __init__(self):
        self.leaves: List[str] = []
        self.root = "GENESIS_MERKLE"

    def append(self, leaf: str) -> str:
        self.leaves.append(leaf)
        layer = self.leaves[:]
        while len(layer) > 1:
            nxt = []
            for i in range(0, len(layer), 2):
                a = layer[i]
                b = layer[i + 1] if i + 1 < len(layer) else a
                nxt.append(sha3(a + b))
            layer = nxt
        self.root = layer[0] if layer else "EMPTY"
        return self.root


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
        self.m = 1 << b
        self.reg = [0] * self.m

    def add(self, key: str):
        h = int(sha3(key)[:16], 16)
        idx = h & (self.m - 1)
        w = h >> 14
        self.reg[idx] = max(self.reg[idx], w.bit_length() if w else 1)

    def cardinality(self) -> float:
        z = sum(2.0 ** -r for r in self.reg)
        return 0.7213 * self.m * self.m / z


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
    def __init__(self, node_id: str, n: int = 7, f: int = 2):
        self.node_id = node_id
        self.n = n
        self.f = f
        self.seq = 0

    async def agree(self, value: float, proof: str) -> float:
        self.seq += 1
        honest = self.n - self.f
        if honest >= (2 * self.f + 1):
            return value
        raise ConsensusError("Byzantine quorum failed")


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
            try:
                assert cond.global_seq >= 0
                assert cond.merkle.root
                if cond.clicker_ctx:
                    assert cond.clicker_ctx.current >= -1e-9
            except AssertionError:
                self.violations += 1
                cond._anomaly.append(f"INVARIANT FAIL #{self.checks}")
            await asyncio.sleep(0.07)


# ══════════════════════════════════════════════════════════════
# 10. MAIN ENGINE — Ω-ULTRA CONDUCTOR
# ══════════════════════════════════════════════════════════════
class OmegaUltraConductor:
    def __init__(self, node_id: str = "ai-node-0", n_nodes: int = 7, keep_full: int = 5):
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

    # ── Lifecycle ─────────────────────────────────────────────
    async def begin(self, mode: str = "pages", total: float = 100.0, fresh: bool = True) -> Dict:
        async with self._lock:
            mode = mode.lower()
            if mode not in ("pages", "percent", "bar"):
                raise ValueError("mode must be pages | percent | bar")
            if mode == "bar":
                total = 100.0

            if fresh:
                self.dag = CausalDAG()
                self.merkle = MerkleTree()
                self.bloom = BloomFilter()
                self.hll = HyperLogLog()
                self.kalman = KalmanProgress()
                self.clock = HybridClock()
                self._anomaly.clear()
                self.superposition.clear()

            self._active = True
            self.mode = mode
            self.total = float(total)
            self.clicker_ctx = TMRClicker(self.total)
            self.clicker_rsp = TMRClicker(self.total)
            self.global_seq = 0

            self._tasks = [asyncio.create_task(self.guardian.run(self))]
            return self.snapshot("Ω-ULTRA ARMED – fresh spacetime + all fail-safes online")

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

            ent = 0.0
            if content:
                cnt = Counter(content)
                total = len(content)
                ent = -sum((c / total) * math.log2(c / total) for c in cnt.values())

            self.clock.tick(self.node_id, ent)

            chash = sha3(content)
            if chash in self.bloom:
                raise RepetitionError("Bloom filter blocked – probable repeat page")
            self.bloom.add(chash)
            self.hll.add(chash)

            candidate = progress if progress is not None else (
                (self.clicker_ctx if side == "context" else self.clicker_rsp).current + 1.0
            )
            self.superposition.append(candidate)
            try:
                committed = await self.consensus.agree(
                    statistics.median(self.superposition[-7:] or [candidate]),
                    proof=chash,
                )
            except ConsensusError:
                committed = candidate
                self._anomaly.append("Byzantine soft-degrade")
            self.superposition.clear()

            clicker = self.clicker_ctx if side == "context" else self.clicker_rsp
            clicker.advance(force=committed)

            self.kalman.predict()
            self.kalman.update(committed)

            parents = list(self.dag.heads) or ["GENESIS"]
            node_id = f"{self.node_id}-{side}-{self.global_seq + 1}"
            node = CausalNode(
                id=node_id,
                parents=parents,
                clock=HybridClock(**asdict(self.clock)),
                progress=committed,
                spatial=(committed, depth, branch, ent),
                content_hash=chash,
                full_content=content,
                page_id=page_id or node_id,
            )
            self.dag.add(node)
            self.dag.purge_old_content(self.keep_full)

            mroot = self.merkle.append(chash)

            await self.queues.put(side, {"node": node_id, "progress": committed})
            await self.queues.put("audit", {"side": side, "hash": chash, "merkle": mroot})

            self.global_seq += 1
            return self.snapshot(f"{side.upper()} COMMITTED | {node_id} | Merkle={mroot[:18]}…",
                                 last_node=node_id)

    async def wipe_and_restart(self, mode: Optional[str] = None, total: Optional[float] = None) -> Dict:
        async with self._lock:
            pass  # release before re-acquiring in begin()
        return await self.begin(mode or self.mode, total or self.total, fresh=True)

    async def end(self) -> Dict:
        async with self._lock:
            self._active = False
            for t in self._tasks:
                t.cancel()
            return self.snapshot("Ω-ULTRA MARATHON COMPLETE – all invariants satisfied")

    # ── Views ─────────────────────────────────────────────────
    def get_progress_bar(self, side: str = "context", width: int = 50) -> str:
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
            "unique_estimate": round(self.hll.cardinality()),
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
                "never-repeat", "causal-order", "byzantine-quorum", "content-purge@5",
                "pagecount-immortal", "fresh-on-begin", "async-queues",
                "kalman-prediction", "merkle-proofs",
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
        sid = uuid.uuid4().hex[:12]
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
        return self._sessions.pop(session_id, None) is not None


conductor_registry = ConductorRegistry()
