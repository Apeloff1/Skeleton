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

import time
from typing import Dict, List, Optional

from gameforge.omega.conductor import (
    OmegaUltraConductor, OrchestratorConductor,
    RepetitionError, MarathonStateError,
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
        """Restore accumulated IQ / counters / recent growth from Mongo once."""
        if self._loaded or not self._persist_enabled():
            self._loaded = True
            return
        self._loaded = True
        try:
            from core.databases import core_db
            doc = await core_db[_PERSIST_COLLECTION].find_one({"_id": _PERSIST_ID})
            if doc:
                self.system_iq = float(doc.get("system_iq", self.system_iq))
                self.total_emissions = int(doc.get("total_emissions", 0))
                self.blocked_repeats = int(doc.get("blocked_repeats", 0))
                gl = doc.get("growth_log")
                if isinstance(gl, list):
                    self.growth_log = gl[-500:]
                dm = doc.get("delta_memory")
                if isinstance(dm, dict):
                    try:
                        from gameforge.omega.delta_memory import delta_memory as _dm
                        _dm.load(dm)
                    except Exception:  # noqa: BLE001
                        pass
        except Exception:  # noqa: BLE001 — never block boot on a cold DB
            pass

    async def _persist_state(self, force: bool = False):
        """Throttled best-effort write of the fabric's durable state.

        Leading-edge writes happen immediately; if a write arrives inside the
        throttle window it is coalesced and a single TRAILING-edge flush is
        scheduled so the LAST state in a burst is never lost (fixes the
        bursty-emission data-loss found in Stage-A testing)."""
        if not self._persist_enabled():
            return
        now = time.time()
        if not force and (now - self._last_persist) < self._persist_interval():
            self._schedule_trailing_flush()
            return
        self._last_persist = now
        try:
            from core.databases import core_db
            dm_doc = None
            try:
                from gameforge.omega.delta_memory import delta_memory as _dm
                dm_doc = _dm.to_persist()
            except Exception:  # noqa: BLE001
                dm_doc = None
            await core_db[_PERSIST_COLLECTION].update_one(
                {"_id": _PERSIST_ID},
                {"$set": {
                    "system_iq": self.system_iq,
                    "total_emissions": self.total_emissions,
                    "blocked_repeats": self.blocked_repeats,
                    "growth_log": self.growth_log[-50:],
                    "delta_memory": dm_doc,
                    "updated_at": now,
                }},
                upsert=True,
            )
        except Exception:  # noqa: BLE001 — persistence must never break emissions
            pass

    def _schedule_trailing_flush(self):
        """Schedule ONE delayed force-persist after the throttle window so the
        latest state in a burst is durably written. Coalesces concurrent
        requests via ``_flush_scheduled``."""
        if self._flush_scheduled:
            return
        try:
            import asyncio

            async def _trailing():
                try:
                    await asyncio.sleep(self._persist_interval())
                finally:
                    self._flush_scheduled = False
                await self._persist_state(force=True)

            asyncio.get_running_loop().create_task(_trailing())
            self._flush_scheduled = True
        except Exception:  # noqa: BLE001
            self._flush_scheduled = False

    # ── lifecycle ─────────────────────────────────────────────
    async def ensure_started(self):
        if self._started:
            return
        await self._load_state()
        await self.jeeves.begin("percent", 100.0, fresh=True)
        await self.agent_map.begin("percent", 100.0, fresh=True)
        self.jeeves.attach("agent-map", self.agent_map)
        self._started = True

    async def register_agent(self, agent_id: str) -> OmegaUltraConductor:
        await self.ensure_started()
        if agent_id in self.agents:
            return self.agents[agent_id]
        # evict oldest if over cap
        if len(self.agents) >= _MAX_AGENTS:
            oldest = self._agent_order.pop(0)
            old = self.agents.pop(oldest, None)
            if old:
                await old.end()
            self.agent_map.subs.pop(oldest, None)
        cond = OmegaUltraConductor(node_id=f"agent::{agent_id}")
        await cond.begin("pages", 1000.0, fresh=True)
        self.agents[agent_id] = cond
        self._agent_order.append(agent_id)
        self.agent_map.attach(agent_id, cond)
        return cond

    def _grow(self, event: str, agent_id: str):
        self.total_emissions += 1
        self.system_iq = min(_IQ_MAX, self.system_iq + 1.0)
        self.growth_log.append({"event": event, "agent": agent_id,
                                "iq": self.system_iq, "ts": time.time()})
        if len(self.growth_log) > 500:
            self.growth_log = self.growth_log[-500:]
        # Best-effort throttled durable persistence (A1). Fire-and-forget so
        # the emission hot-path never awaits a DB round-trip.
        try:
            import asyncio
            loop = asyncio.get_running_loop()
            loop.create_task(self._persist_state())
            # B3 — stream the IQ growth onto the PROOD event bus (durable sink).
            try:
                from gameforge.prood import event_bus as _bus
                loop.create_task(_bus.publish(
                    "iq.grow", {"event": event, "agent": agent_id, "iq": self.system_iq}))
            except Exception:  # noqa: BLE001
                pass
        except Exception:  # noqa: BLE001
            pass

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
        """Route an agent's output through its conductor. Never raises into the
        caller — repetition/degrade is reported in the return dict so the live
        runtime can't be broken by the fail-safe layer."""
        try:
            cond = await self.register_agent(agent_id)
            snap = await cond.deliver_context(content, page_id=f"{agent_id}:{topic}")
            self._grow("agent_emit", agent_id)
            self._lafs_remember(agent_id, content, topic)
            return {"accepted": True, "blocked": False, "system_iq": self.system_iq,
                    "progress": snap["context"]["percent"], "merkle": snap["merkle_root"][:16],
                    "seq": snap["global_seq"]}
        except RepetitionError:
            self.blocked_repeats += 1
            return {"accepted": False, "blocked": True, "reason": "duplicate",
                    "system_iq": self.system_iq}
        except (MarathonStateError, Exception) as e:  # noqa: BLE001
            return {"accepted": False, "blocked": False, "error": f"{type(e).__name__}: {e}",
                    "system_iq": self.system_iq}

    async def jeeves_emit(self, content: str, topic: str = "jeeves") -> Dict:
        try:
            await self.ensure_started()
            snap = await self.jeeves.deliver_response(content, page_id=f"jeeves:{topic}")
            self._grow("jeeves_emit", "jeeves")
            self._lafs_remember("jeeves", content, topic)
            return {"accepted": True, "blocked": False, "system_iq": self.system_iq,
                    "progress": snap["response"]["percent"], "merkle": snap["merkle_root"][:16],
                    "seq": snap["global_seq"]}
        except RepetitionError:
            self.blocked_repeats += 1
            return {"accepted": False, "blocked": True, "reason": "duplicate",
                    "system_iq": self.system_iq}
        except Exception as e:  # noqa: BLE001
            return {"accepted": False, "blocked": False, "error": f"{type(e).__name__}: {e}",
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
            "persisted": self._persist_enabled(),
            "restored": self._loaded,
            "delta_memory": self._delta_stats(),
            "jeeves": self.jeeves.snapshot("jeeves-mastermap") if self._started else None,
            "agent_map": self.agent_map.snapshot("agent-map") if self._started else None,
            "agents": self.list_agents(),
            "recent_growth": self.growth_log[-15:],
            "topology": "jeeves(mastermap) → agent-map(map) → agents(sub-conductors)",
        }


omega_fabric = OmegaFabric()
