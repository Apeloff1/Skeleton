"""Launch-ready session orchestrator.

Ties the conductor, turn engine, asset pipeline, economy, and combat
into a single operational session the app can run at launch.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional
import time
import uuid

from ..ai.conductor import AIGameStudioConductor
from ..content.pipeline import AssetPipeline
from ..runtime.turn_engine import TurnEngine, AgentCoordinator
from ..systems.economy_combat import EconomySystem, CombatSystem


class LaunchSessionOrchestrator:
    """
    Full operational session for autonomous game construction and play.

    Flow:
      1. Parse brief via conductor
      2. Generate assets via pipeline
      3. Register agents and run construction ticks
      4. Wire economy and combat
      5. Return playable session state
    """

    def __init__(self, brief: str, seed: int = 0, era: str = "HOUSE_ERA") -> None:
        self.session_id = str(uuid.uuid4())[:8]
        self.brief = brief
        self.seed = seed
        self.era = era
        self.created_at = time.time()
        self.conductor = AIGameStudioConductor(era=era)
        self.pipeline = AssetPipeline(seed=seed)
        self.economy = EconomySystem()
        self.combat = CombatSystem()
        self.engine = TurnEngine(seed=seed)
        self.coordinator = AgentCoordinator()
        self.result: Optional[Dict[str, Any]] = None

    def run_construction(self) -> Dict[str, Any]:
        """Run the full construction pipeline and produce a playable state."""
        # 1. Conductor pipeline
        pipeline_result = self.conductor.run(self.brief)
        if not pipeline_result.get("ok"):
            return {"ok": False, "stage": "conductor", "result": pipeline_result}

        # 2. Asset generation
        title = pipeline_result.get("stages", [{}])[0].get("artifacts", {}).get("spec", {}).get("title", self.brief[:40])
        assets = self.pipeline.full_pack(title, room_count=10)

        # 3. Economy seed
        self.economy.add_funds(100)
        if assets.get("items"):
            self.economy.register_vendor("vendor_0", assets["items"][:4])

        # 4. Agent registration and construction ticks
        self.coordinator.register_agent("builder", ["build", "layout"])
        self.coordinator.register_agent("narrative", ["dialogue", "quest"])
        self.coordinator.register_agent("economy", ["loot", "vendor"])

        assign1 = self.coordinator.assign("build", {"rooms": len(assets["rooms"])})
        assign2 = self.coordinator.assign("dialogue", {"title": title})
        if assign1.get("ok"):
            self.coordinator.complete(assign1["task_id"], {"rooms": assets["rooms"]})
        if assign2.get("ok"):
            self.coordinator.complete(assign2["task_id"], {"dialogue": assets["dialogue"]})

        # 5. Sample combat resolution
        player = {"id": "player", "health": 100, "damage": 12, "armor": 2}
        enemies = [{"id": f"e_{i}", "health": 20 + i * 5, "damage": 4 + i, "armor": 0} for i in range(3)]
        combat_result = self.combat.resolve_wave(player, enemies)

        self.result = {
            "ok": True,
            "session_id": self.session_id,
            "brief": self.brief,
            "era": self.era,
            "pipeline": pipeline_result,
            "assets": assets,
            "economy": self.economy.snapshot(),
            "combat_sample": combat_result,
            "coordinator": self.coordinator.status(),
            "ready_for_launch": pipeline_result.get("ready_for_launch", False),
            "fidelity": pipeline_result.get("fidelity"),
        }
        return self.result

    def status(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "brief": self.brief[:60],
            "ran": self.result is not None,
            "ok": bool(self.result and self.result.get("ok")),
            "ready": bool(self.result and self.result.get("ready_for_launch")),
            "fidelity": self.result.get("fidelity") if self.result else None,
        }


def run_operational_session(brief: str, seed: int = 0) -> Dict[str, Any]:
    """One-line operational entry point."""
    orch = LaunchSessionOrchestrator(brief, seed=seed)
    return orch.run_construction()
