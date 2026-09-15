"""
Tests for Text-to-Game-Logic Pipeline
"""

import pytest
from fastapi.testclient import TestClient


class TestGameLogicPipeline:
    """Test suite for Game Logic Pipeline endpoints."""

    @pytest.mark.unit
    def test_game_logic_overview(self, client: TestClient):
        """Test game logic pipeline overview endpoint."""
        response = client.get("/api/game-logic-pipeline/overview")
        assert response.status_code == 200
        data = response.json()
        
        assert "pipeline" in data
        assert "capabilities" in data
        assert "mechanic_types" in data
        assert "combat_styles" in data

    @pytest.mark.unit
    def test_generate_combat_system(self, client: TestClient, sample_combat_request: dict):
        """Test generating a combat system."""
        response = client.post(
            "/api/game-logic-pipeline/combat/generate",
            json=sample_combat_request
        )
        assert response.status_code == 200
        data = response.json()
        
        assert data["success"] is True
        assert "combat_system" in data
        
        combat = data["combat_system"]
        assert "style" in combat
        assert combat["style"] == "turn_based"
        assert "damage_types" in combat
        assert "magical" in combat["damage_types"]  # include_magic=True
        assert "magic_system" in combat
        assert "party_mechanics" in combat  # party_based=True

    @pytest.mark.unit
    def test_generate_progression_system(self, client: TestClient):
        """Test generating a progression system."""
        response = client.post(
            "/api/game-logic-pipeline/progression/generate",
            json={
                "style": "skill_tree",
                "max_level": 50,
                "skill_tree_branches": 3,
                "include_prestige": True
            }
        )
        assert response.status_code == 200
        data = response.json()
        
        assert data["success"] is True
        progression = data["progression_system"]
        assert progression["level_cap"] == 50
        assert "skill_tree" in progression
        assert "prestige" in progression
        assert len(progression["xp_table"]) == 50

    @pytest.mark.unit
    def test_generate_economy_system(self, client: TestClient):
        """Test generating an economy system."""
        response = client.post(
            "/api/game-logic-pipeline/economy/generate",
            json={
                "currencies": ["gold", "gems"],
                "include_trading": True,
                "include_crafting": True
            }
        )
        assert response.status_code == 200
        data = response.json()
        
        assert data["success"] is True
        economy = data["economy_system"]
        assert "currencies" in economy
        assert "gold" in economy["currencies"]
        assert "trading" in economy
        assert "crafting" in economy

    @pytest.mark.unit
    def test_generate_ai_behavior(self, client: TestClient):
        """Test generating AI behavior tree."""
        response = client.post(
            "/api/game-logic-pipeline/ai/generate",
            json={
                "entity_type": "enemy_soldier",
                "behaviors": ["patrol", "chase", "attack"],
                "aggression_level": 0.8,
                "intelligence_level": 0.6
            }
        )
        assert response.status_code == 200
        data = response.json()
        
        assert data["success"] is True
        assert "behavior_tree" in data
        assert "states" in data["behavior_tree"]
        assert "parameters" in data["behavior_tree"]
