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

    # ── lifecycle ─────────────────────────────────────────────
    async def ensure_started(self):
        if self._started:
            return
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
            "jeeves": self.jeeves.snapshot("jeeves-mastermap") if self._started else None,
            "agent_map": self.agent_map.snapshot("agent-map") if self._started else None,
            "agents": self.list_agents(),
            "recent_growth": self.growth_log[-15:],
            "topology": "jeeves(mastermap) → agent-map(map) → agents(sub-conductors)",
        }


omega_fabric = OmegaFabric()
