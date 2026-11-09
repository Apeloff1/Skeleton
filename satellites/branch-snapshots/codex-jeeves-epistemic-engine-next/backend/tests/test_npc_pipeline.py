"""
Tests for Text-to-NPC Pipeline
"""

import pytest
from fastapi.testclient import TestClient


class TestNPCPipeline:
    """Test suite for NPC Pipeline endpoints."""

    @pytest.mark.unit
    def test_npc_pipeline_overview(self, client: TestClient):
        """Test NPC pipeline overview endpoint."""
        response = client.get("/api/npc-pipeline/overview")
        assert response.status_code == 200
        data = response.json()
        
        assert "pipeline" in data
        assert "capabilities" in data
        assert "archetypes" in data
        assert data["co_coding_enabled"] is True

    @pytest.mark.unit
    def test_get_archetypes(self, client: TestClient):
        """Test getting all NPC archetypes."""
        response = client.get("/api/npc-pipeline/archetypes")
        assert response.status_code == 200
        data = response.json()
        
        assert "archetypes" in data
        assert len(data["archetypes"]) > 0

    @pytest.mark.unit
    def test_generate_npc_basic(self, client: TestClient, sample_npc_request: dict):
        """Test generating an NPC with basic request."""
        response = client.post("/api/npc-pipeline/generate", json=sample_npc_request)
        assert response.status_code == 200
        data = response.json()
        
        assert data["success"] is True
        assert "npc" in data
        
        npc = data["npc"]
        assert "id" in npc
        assert "archetype" in npc
        assert "personality" in npc
        assert "stats" in npc
        assert "dialogue_tree" in npc  # Because include_dialogue=True
        assert "quest_hooks" in npc  # Because include_quests=True

    @pytest.mark.unit
    def test_generate_npc_minimal(self, client: TestClient):
        """Test generating an NPC with minimal request."""
        response = client.post(
            "/api/npc-pipeline/generate",
            json={"description": "a simple guard"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    @pytest.mark.unit
    def test_generate_npc_with_archetype(self, client: TestClient):
        """Test generating an NPC with specified archetype."""
        response = client.post(
            "/api/npc-pipeline/generate",
            json={
                "description": "a cunning figure",
                "archetype": "merchant"
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["npc"]["archetype"] == "merchant"

    @pytest.mark.unit
    def test_npc_personality_structure(self, client: TestClient, sample_npc_request: dict):
        """Test that NPC personality has correct structure."""
        response = client.post("/api/npc-pipeline/generate", json=sample_npc_request)
        data = response.json()
        
        personality = data["npc"]["personality"]
        # Big 5 personality traits
        assert "openness" in personality
        assert "conscientiousness" in personality
        assert "extraversion" in personality
        assert "agreeableness" in personality
        assert "neuroticism" in personality
        assert "personality_summary" in personality
