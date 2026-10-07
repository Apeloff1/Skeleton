#!/usr/bin/env python3
"""
Forge Orchestrator
Coordinates multiple forges and ensures they work together during Snowball steps.
"""

from gameforge.forges.forge_logging import get_forge_logger
from gameforge.forges.asset_forge import asset_forge
from gameforge.forges.mechanic_forge import mechanic_forge
from gameforge.forges.world_forge import world_forge
from gameforge.forges.code_forge import code_forge
from gameforge.forges.ui_forge import ui_forge
from gameforge.forges.balance_forge import balance_forge

class ForgeOrchestrator:
    def __init__(self):
        self.logger = get_forge_logger("forge_orchestrator")
        self.forges = {
            "asset": asset_forge,
            "mechanic": mechanic_forge,
            "world": world_forge,
            "code": code_forge,
            "ui": ui_forge,
            "balance": balance_forge
        }

    def run_full_pipeline(self, game_concept: dict) -> dict:
        """Run a coordinated pass across all forges based on game concept."""
        self.logger.log_action(
            action="run_full_pipeline",
            input_data=game_concept,
            output_data={},
            success=True,
            notes="Starting coordinated forge pass"
        )

        results = {}

        # Example orchestration
        if "art_style" in game_concept:
            results["asset"] = self.forges["asset"].generate_sprite(
                game_concept.get("core_loop", "game"), 
                game_concept.get("art_style", "pixel")
            )

        if "core_mechanic" in game_concept:
            results["mechanic"] = self.forges["mechanic"].design_core_mechanic(
                game_concept.get("core_mechanic", "core_loop"),
                game_concept.get("description", "")
            )

        results["world"] = self.forges["world"].generate_world_lore(
            game_concept.get("genre", "fantasy")
        )

        results["code"] = self.forges["code"].generate_game_script(
            game_concept.get("core_mechanic", "core_loop")
        )

        results["ui"] = self.forges["ui"].design_menu("main_menu", game_concept.get("art_style", "pixel"))

        results["balance"] = self.forges["balance"].balance_game(
            game_concept.get("game_name", "Untitled"), 
            {"difficulty": "medium"}
        )

        self.logger.log_action(
            action="full_pipeline_complete",
            input_data=game_concept,
            output_data=results,
            success=True
        )

        return results

forge_orchestrator = ForgeOrchestrator()