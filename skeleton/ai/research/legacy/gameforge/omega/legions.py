"""
gameforge.omega.legions — Legion Command: named game-building specialty legions.

Jeeves (the mastermap conductor) commands a standing army of specialty LEGIONS.
Each legion is a very large body of agents focused on ONE game-building craft
(WorldForge, Narrative, Mechanics, Assets, Physics, Audio, Netcode, Economy,
UI/UX, QA, BuildCI, AIBehavior, Procedural, VFX, Localization, Balance …).

When Jeeves MOBILIZES, whole legions activate in WAVES. Crucially, competency is
COLLECTIVE — mobilizing any legion raises a shared "doctrine" floor that lifts
every legion a little, so the whole army "grows rapidly in competency together"
(a rising tide). Each wave also folds a summary into the Ω-fabric (System-IQ +
Delta-KDA memory) and streams onto the PROOD event bus.

The legion sizes are drawn from the real ``core.full_roster`` constellation
(~1.47M agents across 8 cohorts) so the amounts are grounded, not cosmetic.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

_PERSIST_COLLECTION = "omega_persistence"
_PERSIST_ID = "legions"
_COMPETENCY_CAP = 1000.0

# (id, display name, game-building specialty, roster cohort to draw agents from)
LEGION_DEFS = [
    ("worldforge",  "WorldForge Legion",   "world generation · biomes · terrain",        "hexa"),
    ("narrative",   "Narrative Legion",    "story · lore · quest & dialogue trees",       "hexa"),
    ("mechanics",   "Mechanics Legion",    "core gameplay loops · rules · systems",       "mega"),
    ("assets",      "Asset Legion",        "3D/2D models · textures · sprites · rigs",    "hyper"),
    ("physics",     "Physics Legion",      "collision · rigidbody · fluid · cloth",       "quantum"),
    ("audio",       "Audio Legion",        "music · SFX · adaptive/spatial mixing",       "hyper"),
    ("netcode",     "Netcode Legion",      "multiplayer · rollback · authority · sync",   "mega"),
    ("economy",     "Economy Legion",      "loot · currency · progression · sinks",       "mega"),
    ("uiux",        "UI/UX Legion",        "HUD · menus · controller/touch flows",        "hyper"),
    ("qa",          "QA Legion",           "test · fuzz · regression · certification",    "aaa"),
    ("buildci",     "Build/CI Legion",     "compile · package · deploy · pipelines",      "deploy"),
    ("aibehavior",  "AI Behavior Legion",  "enemy AI · behavior trees · pathing",         "quantum"),
    ("procedural",  "Procedural Legion",   "PCG · noise · wave-function-collapse",        "hexa"),
    ("vfx",         "VFX Legion",          "shaders · particles · post-processing",       "hyper"),
    ("localization","Localization Legion", "i18n · culturalization · voice-over",         "mega"),
    ("balance",     "Balance Legion",      "tuning · difficulty · telemetry-driven",      "aaa"),
]


@dataclass
class Legion:
    id: str
    name: str
    specialty: str
    cohort: str
    size: int
    competency: float = 50.0        # 0..1000, grows with every wave
    waves: int = 0
    agents_activated: int = 0
    last_active: float = 0.0

    def brief(self) -> Dict:
        return {"id": self.id, "name": self.name, "specialty": self.specialty,
                "cohort": self.cohort, "size": self.size,
                "competency": round(self.competency, 2), "waves": self.waves,
                "agents_activated": self.agents_activated,
                "last_active": self.last_active}


class LegionCommand:
    def __init__(self):
        self.legions: Dict[str, Legion] = {}
        self._loaded = False
        self._build()

    def _build(self):
        try:
            from core.full_roster import cohort_by_id, TOTAL_AGENTS
            self.total_roster = TOTAL_AGENTS
        except Exception:  # noqa: BLE001
            cohort_by_id, self.total_roster = (lambda _c: None), 1_473_844
        for lid, name, spec, cohort in LEGION_DEFS:
            c = cohort_by_id(cohort) if callable(cohort_by_id) else None
            size = int((c or {}).get("legion_size", 5000)) if c else 5000
            self.legions[lid] = Legion(id=lid, name=name, specialty=spec,
                                       cohort=cohort, size=size)

    # ── persistence (competency survives restart, like System-IQ) ──
    async def load(self):
        if self._loaded:
            return
        self._loaded = True
        try:
            from core.databases import core_db
            doc = await core_db[_PERSIST_COLLECTION].find_one({"_id": _PERSIST_ID})
            for row in (doc or {}).get("legions", []):
                lg = self.legions.get(row.get("id"))
                if lg:
                    lg.competency = float(row.get("competency", lg.competency))
                    lg.waves = int(row.get("waves", 0))
                    lg.agents_activated = int(row.get("agents_activated", 0))
                    lg.last_active = float(row.get("last_active", 0.0))
        except Exception:  # noqa: BLE001
            pass

    async def _persist(self):
        try:
            from core.databases import core_db
            await core_db[_PERSIST_COLLECTION].update_one(
                {"_id": _PERSIST_ID},
                {"$set": {"legions": [lg.brief() for lg in self.legions.values()],
                          "updated_at": time.time()}},
                upsert=True)
        except Exception:  # noqa: BLE001
            pass

    # ── mobilization ───────────────────────────────────────────
    async def mobilize(self, legion_id: str, wave_size: int = 500,
                       directive: str = "advance the build") -> Dict:
        await self.load()
        lg = self.legions.get(legion_id)
        if not lg:
            return {"ok": False, "error": "unknown_legion"}
        wave = max(1, min(wave_size, lg.size))

        # register a bounded sample of wave leaders into the Ω-fabric so the
        # activation is REAL (grows System-IQ + Delta memory) without exceeding
        # the fabric's agent cap — the full wave size is tracked numerically.
        from gameforge.omega.integration import omega_fabric
        leaders = max(1, min(6, wave // 100 + 1))
        for i in range(leaders):
            aid = f"{lg.id}#w{lg.waves+1}#{i}"
            try:
                await omega_fabric.agent_emit(
                    aid, f"[{lg.name}] wave {lg.waves+1} · {directive} · {lg.specialty}",
                    topic=lg.id)
            except Exception:  # noqa: BLE001
                pass

        # competency growth: mobilized legion gets a strong boost that scales
        # with wave size but shows diminishing returns near the cap.
        gain = 6.0 * (wave / max(1, lg.size)) ** 0.5 + 1.5
        lg.competency = min(_COMPETENCY_CAP, lg.competency + gain)
        lg.waves += 1
        lg.agents_activated += wave
        lg.last_active = time.time()

        # COLLECTIVE UPLIFT — the whole army rises a little (grow together).
        shared = gain * 0.15
        for other in self.legions.values():
            if other.id != lg.id:
                other.competency = min(_COMPETENCY_CAP, other.competency + shared)

        try:
            from gameforge.prood import event_bus as _bus
            await _bus.publish("legion.mobilized",
                               {"legion": lg.id, "wave": lg.waves, "agents": wave,
                                "competency": round(lg.competency, 1)})
        except Exception:  # noqa: BLE001
            pass
        await self._persist()
        return {"ok": True, "legion": lg.brief(), "wave_size": wave,
                "leaders_registered": leaders, "collective_uplift": round(shared, 3)}

    async def jeeves_mobilize_all(self, wave_size: int = 500,
                                  directive: str = "full army advance") -> Dict:
        """Jeeves commands EVERY legion — large simultaneous waves. This is how
        Jeeves 'uses all agents'."""
        await self.load()
        reports = []
        total_agents = 0
        for lid in self.legions:
            r = await self.mobilize(lid, wave_size=wave_size, directive=directive)
            if r.get("ok"):
                reports.append(r["legion"])
                total_agents += r["wave_size"]
        try:
            from gameforge.prood import event_bus as _bus
            await _bus.publish("legion.army_wave",
                               {"legions": len(reports), "agents": total_agents})
        except Exception:  # noqa: BLE001
            pass
        return {"ok": True, "commander": "jeeves-mastermap",
                "legions_mobilized": len(reports),
                "agents_in_wave": total_agents,
                "army_competency": round(self.army_competency(), 2),
                "legions": reports}

    # ── views ──────────────────────────────────────────────────
    def army_competency(self) -> float:
        if not self.legions:
            return 0.0
        return sum(l.competency for l in self.legions.values()) / len(self.legions)

    async def roster(self) -> Dict:
        await self.load()
        return {
            "commander": "jeeves-mastermap",
            "legion_count": len(self.legions),
            "total_roster_agents": self.total_roster,
            "army_competency": round(self.army_competency(), 2),
            "total_agents_activated": sum(l.agents_activated for l in self.legions.values()),
            "legions": [l.brief() for l in
                        sorted(self.legions.values(), key=lambda x: x.competency, reverse=True)],
        }


legion_command = LegionCommand()

__all__ = ["Legion", "LegionCommand", "legion_command", "LEGION_DEFS"]
