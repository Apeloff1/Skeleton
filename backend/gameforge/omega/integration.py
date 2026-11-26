"""
gameforge.omega.integration — OmegaFabric.

Wires the Ω-Ultra Conductor INTO Jeeves and ALL agents so the fail-safe
guarantees (never-repeat, causal order, progress, Merkle proofs) apply to the
real multi-agent runtime — not just standalone sessions.

Topology (as requested):
    JEEVES            = OrchestratorConductor   ← mastermap-equivalent
      └─ AGENT-MAP    = OrchestratorConductor   ← map-equivalent, attached to Jeeves
           └─ agent_X = OmegaUltraConductor      ← one per agent, attached to the map

Every validated (non-repeated) emission raises the System-IQ, mirroring the
Jeeves→Jury "growing intelligence" loop.
"""
from __future__ import annotations

import asyncio
import math
import time
from typing import Dict, List, Optional

from gameforge.omega.conductor import (
    OmegaUltraConductor, OrchestratorConductor,
    RepetitionError, QueueOverflowError,
)

_MAX_AGENTS = 250          # soft cap → evict oldest to bound background guardians
_IQ_MAX = 200.0

# ── Durable persistence (Stage A1) ────────────────────────────────────
# The fabric's accumulated intelligence (System-IQ, total emissions, blocked
# repeats and the recent growth log) is the ONLY state that must survive a
# pod restart / fork — the conductors themselves rebuild fresh on boot. We
# persist ONLY these scalar/log fields to Mongo (collection below), throttled
# so a hot emission path never blocks on a DB round-trip.
_PERSIST_COLLECTION = "omega_persistence"
_PERSIST_ID = "fabric"


class OmegaFabric:
    def __init__(self):
        self.jeeves = OrchestratorConductor(node_id="jeeves-mastermap")
        self.agent_map = OrchestratorConductor(node_id="agent-map")
        self.agents: Dict[str, OmegaUltraConductor] = {}
        self._agent_order: List[str] = []
        self._started = False

        self.system_iq = 100.0
        self.total_emissions = 0
        self.blocked_repeats = 0
        self.growth_log: List[Dict] = []

        self._loaded = False
        self._last_persist = 0.0
        self._flush_scheduled = False
        self._lifecycle_lock = asyncio.Lock()
        self._persist_lock = asyncio.Lock()
        self._flush_task: asyncio.Task | None = None
        self._revision = 0
        self._had_document = False
        self._legacy_revision = False
        self._dirty = 0
        self._saved = 0
        self._restore_status = "not_attempted"
        self._write_status = "not_attempted"
        self._growth_queue: asyncio.Queue = asyncio.Queue(maxsize=256)
        self._growth_task: asyncio.Task | None = None
        self._growth_telemetry_failures = 0

    # ── durable state helpers (A1) ────────────────────────────
    def _persist_enabled(self) -> bool:
        try:
            from core.settings import get_settings
            return get_settings().omega_persist
        except Exception:  # noqa: BLE001
            return True

    def _persist_interval(self) -> float:
        try:
            from core.settings import get_settings
            return float(get_settings().omega_persist_interval_s)
        except Exception:  # noqa: BLE001
            return 5.0

    async def _load_state(self):
        if self._loaded:
            return
        if not self._persist_enabled():
            self._restore_status = "disabled"
            return
        # An unavailable durable baseline becomes an explicit volatile session.
        # Never overwrite it with zero-based counters after a failed load.
        if self._dirty:
            self._restore_status = "volatile_unrestored"
            return
        try:
            from core.databases import core_db
            doc = await core_db[_PERSIST_COLLECTION].find_one({"_id": _PERSIST_ID})
            if doc:
                iq = float(doc.get("system_iq", 100.0))
                emissions = doc.get("total_emissions", 0)
                blocked = doc.get("blocked_repeats", 0)
                revision = doc.get("revision", 0)
                raw_log = doc.get("growth_log", [])
                if (not math.isfinite(iq) or not 100 <= iq <= _IQ_MAX or
                        any(type(n) is not int or not 0 <= n < 2**63-1
                            for n in (emissions, blocked, revision)) or
                        not isinstance(raw_log, list) or len(raw_log) > 500 or
                        any(not isinstance(entry, dict) for entry in raw_log)):
                    raise ValueError("invalid persisted Omega counters")
                dm = doc.get("delta_memory")
                if dm is not None:
                    from gameforge.omega.delta_memory import delta_memory as memory
                    memory.load(dm)
                self.system_iq, self.total_emissions, self.blocked_repeats = iq, emissions, blocked
                self.growth_log = raw_log[-500:]
                self._revision = revision
                self._had_document = True
                self._legacy_revision = "revision" not in doc
            self._loaded = True
            self._restore_status = "restored" if doc else "empty"
        except Exception:
            self._restore_status = "unavailable"

    def persistence_status(self) -> Dict:
        return {
            "configured": self._persist_enabled(),
            "restore": self._restore_status,
            "write": self._write_status,
            "revision": self._revision,
            "dirty": self._dirty != self._saved,
            "scope": "counters_and_delta_snapshot_only",
            "session_durable": False,
        }

    def mark_dirty(self):
        self._dirty += 1
        self._schedule_trailing_flush()

    async def _persist_state(self, force: bool = False):
        async with self._persist_lock:
            if not self._persist_enabled():
                self._write_status = "disabled"
                return False
            if not self._loaded:
                self._write_status = "restore_required"
                return False
            if self._write_status == "revision_conflict":
                return False
            if not force and self._dirty == self._saved:
                return True
            if not force and time.monotonic() - self._last_persist < self._persist_interval():
                self._schedule_trailing_flush()
                return False
            try:
                from core.databases import core_db
                from gameforge.omega.delta_memory import delta_memory as memory
                collection = core_db[_PERSIST_COLLECTION]
                saved = self._dirty
                doc = {
                    "system_iq": self.system_iq,
                    "total_emissions": self.total_emissions,
                    "blocked_repeats": self.blocked_repeats,
                    "growth_log": self.growth_log[-50:],
                    "delta_memory": memory.to_persist(),
                    "updated_at": time.time(),
                    "revision": self._revision + 1,
                }
                if self._had_document:
                    selector = {"_id": _PERSIST_ID, "revision": (
                        {"$exists": False} if self._legacy_revision else self._revision)}
                    result = await collection.update_one(selector, {"$set": doc})
                    if result.matched_count != 1:
                        self._write_status = "revision_conflict"
                        return False
                else:
                    try:
                        await collection.insert_one({"_id": _PERSIST_ID, **doc})
                    except Exception as exc:
                        from pymongo.errors import DuplicateKeyError
                        if isinstance(exc, DuplicateKeyError):
                            self._write_status = "revision_conflict"
                            return False
                        raise
                self._had_document = True
                self._legacy_revision = False
                self._revision += 1
                self._saved = saved
                self._last_persist = time.monotonic()
                self._write_status = "saved"
                return True
            except Exception:
                self._write_status = "unavailable"
                return False

    def _schedule_trailing_flush(self):
        if not self._persist_enabled() or not self._loaded or self._write_status == "revision_conflict":
            return
        if self._flush_task and not self._flush_task.done():
            return
        async def trailing():
            # At most one worker, bounded retry cadence. Dirty generations
            # remain dirty until the exact snapshot is acknowledged.
            try:
                while self._dirty != self._saved and self._write_status != "revision_conflict":
                    await asyncio.sleep(max(0.1, min(self._persist_interval(), 60.0)))
                    await self._persist_state(force=True)
            finally:
                self._flush_scheduled = False
        self._flush_scheduled = True
        self._flush_task = asyncio.create_task(trailing())

    async def close(self):
        async with self._lifecycle_lock:
            telemetry, self._growth_task = self._growth_task, None
            if telemetry is not None:
                telemetry.cancel()
                await asyncio.gather(telemetry, return_exceptions=True)
            while not self._growth_queue.empty():
                self._growth_queue.get_nowait()
                self._growth_queue.task_done()
                self._growth_telemetry_failures += 1
            task, self._flush_task = self._flush_task, None
            if task is not None:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
            if self._dirty != self._saved:
                await self._persist_state(force=True)
            for agent in self.agents.values():
                await agent.end()
            self.agents.clear()
            self._agent_order.clear()
            self.agent_map.subs.clear()
            self.jeeves.subs.clear()
            await self.agent_map.end()
            await self.jeeves.end()
            self._started = False

    # ── lifecycle ─────────────────────────────────────────────
    async def _ensure_started_locked(self):
        if self._started:
            return
        await self._load_state()
        await self.jeeves.begin("percent", 100.0, fresh=True)
        await self.agent_map.begin("percent", 100.0, fresh=True)
        self.jeeves.attach("agent-map", self.agent_map)
        self._started = True

    async def ensure_started(self):
        async with self._lifecycle_lock:
            await self._ensure_started_locked()

    async def _register_agent_locked(self, agent_id: str) -> OmegaUltraConductor:
        if not isinstance(agent_id, str) or not 1 <= len(agent_id) <= 128:
            raise ValueError("invalid agent identity")
        await self._ensure_started_locked()
        if agent_id in self.agents:
            return self.agents[agent_id]
        if len(self.agents) >= _MAX_AGENTS:
            raise QueueOverflowError("agent capacity requires explicit retirement")
        cond = OmegaUltraConductor(node_id=f"agent::{agent_id}")
        await cond.begin("pages", 1000.0, fresh=True)
        try:
            self.agent_map.attach(agent_id, cond)
        except Exception:
            await cond.end()
            raise
        self.agents[agent_id] = cond
        self._agent_order.append(agent_id)
        return cond

    async def register_agent(self, agent_id: str) -> OmegaUltraConductor:
        async with self._lifecycle_lock:
            return await self._register_agent_locked(agent_id)

    async def retire_agent(self, agent_id: str) -> bool:
        async with self._lifecycle_lock:
            agent = self.agents.get(agent_id)
            if agent is None:
                return False
            await agent.end()
            self.agents.pop(agent_id)
            self._agent_order.remove(agent_id)
            self.agent_map.subs.pop(agent_id, None)
            return True

    async def drain_agent(self, agent_id: str, queue: str, limit: int):
        async with self._lifecycle_lock:
            return await self.agents[agent_id].drain(queue, limit)

    async def _drain_growth_telemetry(self):
        from gameforge.prood import event_bus
        while not self._growth_queue.empty():
            item = self._growth_queue.get_nowait()
            try:
                result = await asyncio.wait_for(event_bus.publish("iq.grow", item), timeout=5)
                if result.get("persistence") == "unavailable":
                    self._growth_telemetry_failures += 1
            except asyncio.CancelledError:
                self._growth_telemetry_failures += 1
                raise
            except Exception:
                self._growth_telemetry_failures += 1
            finally:
                self._growth_queue.task_done()

    def _enqueue_growth(self, event: str, agent_id: str):
        try:
            self._growth_queue.put_nowait({"event": event, "agent": agent_id,
                                           "iq": self.system_iq,
                                           "basis": "heuristic_emission_counter"})
        except asyncio.QueueFull:
            self._growth_telemetry_failures += 1
            return
        if self._growth_task is None or self._growth_task.done():
            self._growth_task = asyncio.create_task(self._drain_growth_telemetry())

    def _grow(self, event: str, agent_id: str):
        self.total_emissions += 1
        self.system_iq = min(_IQ_MAX, self.system_iq + 1.0)
        self.growth_log.append({"event": event, "agent": agent_id,
                                "iq": self.system_iq, "ts": time.time()})
        if len(self.growth_log) > 500:
            self.growth_log = self.growth_log[-500:]
        self.mark_dirty()
        self._enqueue_growth(event, agent_id)

    def _lafs_remember(self, author: str, content: str, topic: str):
        """Best-effort: persist emission into the LAFS knowledge ledger AND fold
        it into the fixed-size Delta (KDA) associative memory (topic → content)."""
        try:
            from gameforge.lafs import lafs as _lafs
            domain = "Agent" if author != "jeeves" else "Meta"
            log_type = "Handoff" if author != "jeeves" else "Reflection"
            _lafs.add_sheet(domain, log_type,
                            {"content": content[:2000], "topic": topic, "author": author},
                            author=author, tags=[topic])
        except Exception:  # noqa: BLE001 — ledger must never break emissions
            pass
        try:
            from gameforge.omega.delta_memory import delta_memory as _dm
            _dm.write(f"{author}:{topic}", content[:2000], modality="text")
        except Exception:  # noqa: BLE001
            pass

    # ── emissions ─────────────────────────────────────────────
    async def agent_emit(self, agent_id: str, content: str,
                         topic: str = "general") -> Dict:
        async with self._lifecycle_lock:
            try:
                if not isinstance(topic, str) or not 1 <= len(topic) <= 128:
                    raise ValueError("invalid topic")
                cond = await self._register_agent_locked(agent_id)
                snap = await cond.deliver_context(content, page_id=f"{agent_id}:{topic}"[:256])
                self._grow("agent_emit", agent_id)
                self._lafs_remember(agent_id, content, topic)
                return {"accepted": True, "blocked": False, "system_iq": self.system_iq,
                        "progress": snap["context"]["percent"], "merkle": snap["merkle_root"][:16],
                        "seq": snap["global_seq"], "persistence": self.persistence_status()}
            except RepetitionError:
                self.blocked_repeats += 1
                self.mark_dirty()
                return {"accepted": False, "blocked": True, "reason": "duplicate",
                        "system_iq": self.system_iq}
            except QueueOverflowError:
                return {"accepted": False, "blocked": True, "reason": "capacity",
                        "system_iq": self.system_iq}
            except Exception:
                return {"accepted": False, "blocked": False, "error": "omega_emit_failed",
                        "system_iq": self.system_iq}

    async def jeeves_emit(self, content: str, topic: str = "jeeves") -> Dict:
        async with self._lifecycle_lock:
            try:
                if not isinstance(topic, str) or not 1 <= len(topic) <= 128:
                    raise ValueError("invalid topic")
                await self._ensure_started_locked()
                snap = await self.jeeves.deliver_response(content, page_id=f"jeeves:{topic}")
                self._grow("jeeves_emit", "jeeves")
                self._lafs_remember("jeeves", content, topic)
                return {"accepted": True, "blocked": False, "system_iq": self.system_iq,
                        "progress": snap["response"]["percent"], "merkle": snap["merkle_root"][:16],
                        "seq": snap["global_seq"], "persistence": self.persistence_status()}
            except RepetitionError:
                self.blocked_repeats += 1
                self.mark_dirty()
                return {"accepted": False, "blocked": True, "reason": "duplicate",
                        "system_iq": self.system_iq}
            except QueueOverflowError:
                return {"accepted": False, "blocked": True, "reason": "capacity",
                        "system_iq": self.system_iq}
            except Exception:
                return {"accepted": False, "blocked": False, "error": "omega_emit_failed",
                        "system_iq": self.system_iq}

    # ── views ─────────────────────────────────────────────────
    def _delta_stats(self):
        try:
            from gameforge.omega.delta_memory import delta_memory as _dm
            return _dm.stats()
        except Exception:  # noqa: BLE001
            return None

    def agent_status(self, agent_id: str) -> Optional[Dict]:
        c = self.agents.get(agent_id)
        return c.snapshot(f"agent::{agent_id}") if c else None

    def list_agents(self) -> List[Dict]:
        return [
            {"agent_id": aid,
             "seq": c.global_seq,
             "percent": round(c.clicker_ctx.percent(), 2) if c.clicker_ctx else 0.0,
             "unique": round(c.hll.cardinality()),
             "anomalies": len(c._anomaly)}
            for aid, c in self.agents.items()
        ]

    def overview(self) -> Dict:
        return {
            "started": self._started,
            "system_iq": self.system_iq,
            "total_emissions": self.total_emissions,
            "blocked_repeats": self.blocked_repeats,
            "agents_tracked": len(self.agents),
            "persisted": self._loaded and self._write_status == "saved" and self._dirty == self._saved,
            "restored": self._restore_status == "restored",
            "persistence": self.persistence_status(),
            "system_iq_basis": "heuristic_emission_counter_not_intelligence_measurement",
            "delta_memory": self._delta_stats(),
            "jeeves": self.jeeves.snapshot("jeeves-mastermap") if self._started else None,
            "agent_map": self.agent_map.snapshot("agent-map") if self._started else None,
            "agents": self.list_agents(),
            "recent_growth": self.growth_log[-15:],
            "growth_telemetry": {"pending": self._growth_queue.qsize(),
                                 "failures": self._growth_telemetry_failures},
            "topology": "jeeves(mastermap) → agent-map(map) → agents(sub-conductors)",
        }


omega_fabric = OmegaFabric()
