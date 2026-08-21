"""
services/mag.py — MAG: persistent preemptive token fillers.

MAG keeps large, expensive context blocks *warm* so the provider KV-cache
never goes cold between requests:

  PERSISTENT  — fillers are written to disk (JSON) and survive restarts;
                on boot the warmer reloads them and re-primes the cache.
  PREEMPTIVE  — a background warmer refreshes each filler BEFORE its TTL
                expires (at 80% of TTL), so a live request never pays a
                cold-cache rebuild.
  TOKEN FILLERS — canonical, hash-versioned prompt blocks (system prefix,
                curriculum digests, domain canon) whose job is to occupy the
                front of the context window at ~10% billing rate instead of
                being re-processed at full rate every call.

Cost model: a 40k-token system prefix re-sent every request at full rate is
the dominant spend. With MAG keeping it cache-hot, you pay full price once
per TTL window (or once per content change) and ~10% thereafter.
"""
from __future__ import annotations

import asyncio
import json
import os
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Awaitable, Callable

from services.cag import CAGPrefix, estimate_tokens, registry

# ── Config ───────────────────────────────────────────────────────────────────

_PERSIST_PATH = Path(
    os.environ.get("MAG_STORE", str(Path(__file__).resolve().parents[1] / "data" / "mag_fillers.json"))
)
_DEFAULT_TTL_S = int(os.environ.get("MAG_TTL_S", "3300"))        # 55 min — under provider cache TTL
_REFRESH_AT = float(os.environ.get("MAG_REFRESH_AT", "0.8"))     # refresh at 80% of TTL
_WARMER_INTERVAL_S = int(os.environ.get("MAG_WARMER_INTERVAL_S", "60"))

# A builder returns a fresh CAGPrefix for its key (re-render from source).
FillerBuilder = Callable[[], CAGPrefix | Awaitable[CAGPrefix]]


@dataclass
class Filler:
    """One persistent preemptive token filler."""
    key: str
    sha: str
    text: str
    tokens: int
    ttl_s: int
    built_at: float
    refreshed_at: float
    refresh_count: int = 0

    @property
    def expires_at(self) -> float:
        return self.refreshed_at + self.ttl_s

    @property
    def refresh_due_at(self) -> float:
        """Preemptive point: 80% through the TTL window."""
        return self.refreshed_at + self.ttl_s * _REFRESH_AT

    def is_fresh(self, now: float | None = None) -> bool:
        return (now or time.time()) < self.expires_at

    def needs_refresh(self, now: float | None = None) -> bool:
        return (now or time.time()) >= self.refresh_due_at

    def to_dict(self) -> dict:
        return {
            "key": self.key,
            "sha": self.sha,
            "tokens": self.tokens,
            "ttl_s": self.ttl_s,
            "built_at": self.built_at,
            "refreshed_at": self.refreshed_at,
            "refresh_count": self.refresh_count,
            "fresh": self.is_fresh(),
            "expires_in_s": max(0, round(self.expires_at - time.time())),
        }


# ── Store (persistent) ───────────────────────────────────────────────────────

class FillerStore:
    """Disk-backed filler registry. JSON file; atomic-ish writes via tmp+rename."""

    def __init__(self, path: Path = _PERSIST_PATH) -> None:
        self.path = path
        self._fillers: dict[str, Filler] = {}
        self._builders: dict[str, FillerBuilder] = {}
        self._load()

    def _load(self) -> None:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            for key, rec in raw.get("fillers", {}).items():
                self._fillers[key] = Filler(**rec)
        except Exception:
            self._fillers = {}

    def _save(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            payload = {"fillers": {k: asdict(v) for k, v in self._fillers.items()}}
            tmp.write_text(json.dumps(payload), encoding="utf-8")
            tmp.replace(self.path)
        except Exception:
            pass  # persistence is best-effort; in-memory copy continues

    def register_builder(self, key: str, builder: FillerBuilder, ttl_s: int = _DEFAULT_TTL_S) -> None:
        self._builders[key] = builder
        if key in self._fillers:
            self._fillers[key].ttl_s = ttl_s

    def put(self, filler: Filler) -> None:
        self._fillers[filler.key] = filler
        self._save()

    def get(self, key: str) -> Filler | None:
        return self._fillers.get(key)

    def all(self) -> list[Filler]:
        return list(self._fillers.values())

    def due(self, now: float | None = None) -> list[str]:
        return [k for k, f in self._fillers.items() if f.needs_refresh(now)]

    def stats(self) -> dict:
        fresh = sum(1 for f in self._fillers.values() if f.is_fresh())
        return {
            "fillers": len(self._fillers),
            "fresh": fresh,
            "stale": len(self._fillers) - fresh,
            "cached_tokens": sum(f.tokens for f in self._fillers.values()),
            "refresh_total": sum(f.refresh_count for f in self._fillers.values()),
            "store_path": str(self.path),
        }


_store: FillerStore | None = None


def get_store() -> FillerStore:
    global _store
    if _store is None:
        _store = FillerStore()
    return _store


# ── Warmer (preemptive) ──────────────────────────────────────────────────────

class MAGWarmer:
    """Background task: refreshes fillers before their TTL lapses."""

    def __init__(self, store: FillerStore, interval_s: int = _WARMER_INTERVAL_S) -> None:
        self.store = store
        self.interval_s = interval_s
        self._task: asyncio.Task | None = None
        self._stop: asyncio.Event | None = None
        self.cycles = 0
        self.refreshes = 0

    def _stop_event(self) -> asyncio.Event:
        # Created lazily: asyncio.Event() must be made inside a running loop.
        if self._stop is None:
            self._stop = asyncio.Event()
        return self._stop

    async def refresh_one(self, key: str) -> Filler | None:
        builder = self.store._builders.get(key)
        if builder is None:
            return None
        result = builder()
        prefix: CAGPrefix = await result if asyncio.iscoroutine(result) else result
        now = time.time()
        old = self.store.get(key)
        filler = Filler(
            key=key,
            sha=prefix.sha,
            text=prefix.text,
            tokens=prefix.tokens,
            ttl_s=old.ttl_s if old else _DEFAULT_TTL_S,
            built_at=old.built_at if old else now,
            refreshed_at=now,
            refresh_count=(old.refresh_count + 1) if old else 1,
        )
        self.store.put(filler)
        self.refreshes += 1
        return filler

    async def warm_all(self, force: bool = False) -> list[str]:
        now = time.time()
        targets = list(self.store._builders) if force else self.store.due(now)
        # Also prime builders that have no filler yet (first boot).
        for key in self.store._builders:
            if self.store.get(key) is None and key not in targets:
                targets.append(key)
        warmed: list[str] = []
        for key in targets:
            try:
                if await self.refresh_one(key) is not None:
                    warmed.append(key)
            except Exception:
                continue  # one bad filler must not stall the cycle
        return warmed

    async def _loop(self) -> None:
        stop = self._stop_event()
        while not stop.is_set():
            try:
                await self.warm_all()
                self.cycles += 1
            except Exception:
                pass
            try:
                await asyncio.wait_for(stop.wait(), timeout=self.interval_s)
            except asyncio.TimeoutError:
                pass

    def start(self) -> None:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return  # no loop yet (e.g. imported outside app runtime); skip
        if self._task is None or self._task.done():
            self._stop_event().clear()
            self._task = asyncio.create_task(self._loop())

    def stop(self) -> None:
        if self._stop is not None:
            self._stop.set()

    def stats(self) -> dict:
        return {"cycles": self.cycles, "refreshes": self.refreshes, "running": bool(self._task and not self._task.done())}


_warmer: MAGWarmer | None = None


def get_warmer() -> MAGWarmer:
    global _warmer
    if _warmer is None:
        _warmer = MAGWarmer(get_store())
    return _warmer


# ── Built-in filler registrations ────────────────────────────────────────────

def register_default_fillers() -> None:
    """Register the canonical Tutolage fillers. Idempotent."""
    from services.cag import jeeves_system_prefix

    store = get_store()
    store.register_builder("jeeves:system", jeeves_system_prefix)

    def curriculum_digest() -> CAGPrefix:
        from services.cag import PrefixSegment, build_prefix
        try:
            from cs_bible import get_curriculum_stats  # type: ignore
            stats = get_curriculum_stats()
            text = json.dumps(stats, sort_keys=True) if not isinstance(stats, str) else stats
        except Exception:
            text = "Curriculum: 15-year CS bible, 6 domains, 2000+ concepts."
        return build_prefix("curriculum:digest", [PrefixSegment("curriculum", text, cache_breakpoint=True)])

    store.register_builder("curriculum:digest", curriculum_digest)


def prime() -> None:
    """Boot hook: register fillers, reload persisted ones into the CAG registry,
    and start the preemptive warmer."""
    register_default_fillers()
    # Re-prime CAG registry from disk so a restart doesn't cold-start the cache.
    for filler in get_store().all():
        existing = registry.get(filler.key)
        if existing is None or existing.sha != filler.sha:
            from services.cag import CAGPrefix as _P
            registry.register(_P(
                key=filler.key, text=filler.text, sha=filler.sha,
                tokens=filler.tokens, segments=[filler.key], breakpoints=[],
                built_at=filler.built_at,
            ))
    get_warmer().start()


# ── Module-level API used by routes/memory_engine.py ─────────────────────────

def stats() -> dict:
    """Combined MAG stats (store + warmer) for status endpoints."""
    return {
        "store": get_store().stats(),
        "warmer": get_warmer().stats(),
        "fillers": [f.to_dict() for f in get_store().all()],
    }


async def warm_now(force: bool = True) -> dict:
    """Force one preemptive refresh cycle now; returns what was warmed."""
    register_default_fillers()
    warmed = await get_warmer().warm_all(force=force)
    return {"warmed": warmed, "count": len(warmed), "store": get_store().stats()}
