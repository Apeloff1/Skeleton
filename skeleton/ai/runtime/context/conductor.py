"""Fail-safe context-progress conductor for long-form AI delivery.

Tracks pages / percent / bar progress with:
- TMR clickers on context and response sides
- SHA3 exact + Bloom anti-repetition
- Merkle append + causal parent list
- full_content purge after keep_full deliveries
- immortal pagecount log
- async lock + side queues
- wipe-and-restart for a fresh marathon

Cards always ship stored_prose=0.
"""
from __future__ import annotations

import asyncio
import hashlib
import statistics
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Literal

CONDUCTOR_VERSION = "omega-ultra-1.1"

Mode = Literal["pages", "percent", "bar"]
Side = Literal["context", "response"]


class ConductorError(Exception):
    """Base conductor failure."""


class RepetitionError(ConductorError):
    """Exact or probable repeated page blocked."""


class MarathonStateError(ConductorError):
    """Lifecycle violation."""


def _sha3(data: str | bytes) -> str:
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha3_256(data).hexdigest()


def _card(**fields: Any) -> dict[str, Any]:
    out = {"kind": "conductor", "hit": True, "law": "context-progress", "stored_prose": 0}
    out.update(fields)
    return out


class TMRClicker:
    def __init__(self, total: float) -> None:
        self.total = float(total)
        self.vals = [0.0, 0.0, 0.0]
        self.clicks = [0, 0, 0]

    def advance(self, force: float | None = None) -> float:
        target = min(self.total, force if force is not None else self.vals[0] + 1.0)
        if target + 1e-12 < self.vals[0]:
            raise ConductorError("progress regression")
        self.vals = [target, target, target]
        self.clicks = [c + 1 for c in self.clicks]
        return target

    @property
    def current(self) -> float:
        return float(statistics.median(self.vals))

    @property
    def click_count(self) -> int:
        return int(statistics.median(self.clicks))

    def percent(self) -> float:
        return 0.0 if self.total <= 0 else (self.current / self.total) * 100.0

    def reset(self) -> None:
        self.vals = [0.0, 0.0, 0.0]
        self.clicks = [0, 0, 0]


class BloomFilter:
    def __init__(self, size: int = 1 << 18, hashes: int = 5) -> None:
        self.size = size
        self.hashes = hashes
        self.bits = bytearray(size // 8)

    def _idx(self, key: str) -> list[int]:
        h = _sha3(key)
        return [int(h[i : i + 8], 16) % self.size for i in range(0, self.hashes * 8, 8)]

    def add(self, key: str) -> None:
        for i in self._idx(key):
            self.bits[i // 8] |= 1 << (i % 8)

    def __contains__(self, key: str) -> bool:
        return all(self.bits[i // 8] & (1 << (i % 8)) for i in self._idx(key))


class MerkleTree:
    def __init__(self) -> None:
        self.leaves: list[str] = []
        self.root = "GENESIS_MERKLE"

    def append(self, leaf: str) -> str:
        self.leaves.append(leaf)
        layer = list(self.leaves)
        while len(layer) > 1:
            nxt: list[str] = []
            for i in range(0, len(layer), 2):
                a = layer[i]
                b = layer[i + 1] if i + 1 < len(layer) else a
                nxt.append(_sha3(a + b))
            layer = nxt
        self.root = layer[0] if layer else "EMPTY"
        return self.root


@dataclass
class Delivery:
    seq: int
    side: Side
    progress: float
    percent: float
    clicks: int
    content_hash: str
    page_id: str
    ts_ns: int
    full_content: str | None = None


@dataclass
class OmegaUltraConductor:
    node_id: str = "ai-node-0"
    keep_full: int = 5
    _active: bool = False
    mode: Mode = "pages"
    total: float = 100.0
    global_seq: int = 0
    clicker_ctx: TMRClicker | None = None
    clicker_rsp: TMRClicker | None = None
    bloom: BloomFilter = field(default_factory=BloomFilter)
    merkle: MerkleTree = field(default_factory=MerkleTree)
    exact: set[str] = field(default_factory=set)
    deliveries: list[Delivery] = field(default_factory=list)
    pagecount: list[dict[str, Any]] = field(default_factory=list)
    queues: dict[str, deque] = field(default_factory=lambda: {
        "context": deque(maxlen=2048),
        "response": deque(maxlen=2048),
        "audit": deque(maxlen=2048),
    })
    start_ns: int = 0
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    async def begin(self, mode: Mode = "pages", total: float = 100.0, *, fresh: bool = True) -> dict[str, Any]:
        async with self._lock:
            if mode not in ("pages", "percent", "bar"):
                raise ValueError("mode must be pages|percent|bar")
            if mode == "bar":
                total = 100.0
            if total <= 0:
                raise ValueError("total must be positive")
            if fresh:
                self.bloom = BloomFilter()
                self.merkle = MerkleTree()
                self.exact.clear()
                self.deliveries.clear()
                self.pagecount.clear()
                for q in self.queues.values():
                    q.clear()
            self._active = True
            self.mode = mode
            self.total = float(total)
            self.clicker_ctx = TMRClicker(self.total)
            self.clicker_rsp = TMRClicker(self.total)
            self.global_seq = 0
            self.start_ns = time.perf_counter_ns()
            return self._status("begin")

    async def deliver_context(self, content: str, progress: float | None = None, page_id: str | None = None) -> dict[str, Any]:
        return await self._deliver("context", content, progress, page_id)

    async def deliver_response(self, content: str, progress: float | None = None, page_id: str | None = None) -> dict[str, Any]:
        return await self._deliver("response", content, progress, page_id)

    async def _deliver(self, side: Side, content: str, progress: float | None, page_id: str | None) -> dict[str, Any]:
        async with self._lock:
            if not self._active:
                raise MarathonStateError("call begin() first")
            if not content or not content.strip():
                raise RepetitionError("empty content")
            digest = _sha3(content)
            if digest in self.exact or digest in self.bloom:
                raise RepetitionError("repeat page blocked")
            clicker = self.clicker_ctx if side == "context" else self.clicker_rsp
            assert clicker is not None
            committed = clicker.advance(force=progress)
            self.exact.add(digest)
            self.bloom.add(digest)
            self.merkle.append(digest)
            self.global_seq += 1
            entry = Delivery(
                seq=self.global_seq,
                side=side,
                progress=committed,
                percent=clicker.percent(),
                clicks=clicker.click_count,
                content_hash=digest,
                page_id=page_id or f"{self.node_id}-{side}-{self.global_seq}",
                ts_ns=time.perf_counter_ns(),
                full_content=content,
            )
            self.deliveries.append(entry)
            self.pagecount.append({
                "seq": entry.seq,
                "side": side,
                "progress": committed,
                "page_id": entry.page_id,
                "hash": digest,
            })
            overflow = len(self.deliveries) - self.keep_full
            if overflow > 0:
                for old in self.deliveries[:overflow]:
                    old.full_content = None
            self.queues[side].append(entry.page_id)
            self.queues["audit"].append(digest)
            return self._status("deliver", side=side, page_id=entry.page_id, content_hash=digest[:24])

    async def wipe_and_restart(self, mode: Mode | None = None, total: float | None = None) -> dict[str, Any]:
        return await self.begin(mode or self.mode, total or self.total, fresh=True)

    async def end(self) -> dict[str, Any]:
        async with self._lock:
            card = self._status("end")
            self._active = False
            return card

    def progress_bar(self, side: Side = "context", width: int = 24) -> str:
        clicker = self.clicker_ctx if side == "context" else self.clicker_rsp
        pct = clicker.percent() if clicker else 0.0
        filled = int(round(max(0.0, min(100.0, pct)) / 100.0 * width))
        return f"[{'#' * filled}{'-' * (width - filled)}] {pct:6.2f}%"

    def _status(self, event: str, **extra: Any) -> dict[str, Any]:
        c = self.clicker_ctx
        r = self.clicker_rsp
        return _card(
            event=event,
            version=CONDUCTOR_VERSION,
            node=self.node_id,
            mode=self.mode,
            total=self.total,
            active=self._active,
            seq=self.global_seq,
            context_progress=c.current if c else 0.0,
            response_progress=r.current if r else 0.0,
            context_clicks=c.click_count if c else 0,
            response_clicks=r.click_count if r else 0,
            live_content=sum(1 for d in self.deliveries if d.full_content is not None),
            pagecount=len(self.pagecount),
            merkle=self.merkle.root[:24],
            unique=len(self.exact),
            citation="https://github.com/Apeloff1/Skeleton",
            **extra,
        )


class AgentToAgentConductor(OmegaUltraConductor):
    async def handoff(self, content: str, **kwargs: Any) -> dict[str, Any]:
        return await self.deliver_context(content, **kwargs)


class OrchestratorConductor(OmegaUltraConductor):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.subs: dict[str, OmegaUltraConductor] = {}

    def attach(self, name: str, conductor: OmegaUltraConductor) -> None:
        self.subs[name] = conductor


class UserToJeevesConductor(OmegaUltraConductor):
    async def interpret_and_begin(self, user_text: str) -> dict[str, Any]:
        text = user_text.lower()
        mode: Mode = "pages"
        total = 12.0
        if any(w in text for w in ("bar", "progress bar", "visual")):
            mode, total = "bar", 100.0
        elif "%" in text or "percent" in text:
            mode, total = "percent", 100.0
        digits = "".join(ch if ch.isdigit() else " " for ch in text).split()
        if digits and mode == "pages":
            total = float(digits[0])
        return await self.begin(mode, total, fresh=True)

    async def user_message(self, content: str, **kwargs: Any) -> dict[str, Any]:
        return await self.deliver_context(content, **kwargs)

    async def jeeves_reply(self, content: str, **kwargs: Any) -> dict[str, Any]:
        return await self.deliver_response(content, **kwargs)


__all__ = [
    "CONDUCTOR_VERSION",
    "ConductorError",
    "RepetitionError",
    "MarathonStateError",
    "TMRClicker",
    "OmegaUltraConductor",
    "AgentToAgentConductor",
    "OrchestratorConductor",
    "UserToJeevesConductor",
]
