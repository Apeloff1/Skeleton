"""
Tests for Jeeves Core - System Laws, Matrices, and RAG
"""

import pytest
from fastapi.testclient import TestClient


class TestJeevesCore:
    """Test suite for Jeeves Core endpoints."""

    @pytest.mark.unit
    def test_jeeves_core_overview(self, client: TestClient):
        """Test Jeeves Core overview endpoint."""
        response = client.get("/api/jeeves-core/overview")
        assert response.status_code == 200
        data = response.json()
        
        assert "system" in data
        assert "components" in data
        assert "system_laws" in data["components"]
        assert "self_learning_matrices" in data["components"]
        assert data["components"]["system_laws"]["count"] == 3
        assert data["components"]["self_learning_matrices"]["count"] == 3

    @pytest.mark.unit
    def test_get_all_matrices(self, client: TestClient):
        """Test getting all self-learning matrices."""
        response = client.get("/api/jeeves-core/matrices")
        assert response.status_code == 200
        data = response.json()
        
        assert data["success"] is True
        matrices = data["matrices"]
        assert "skill_acquisition_matrix" in matrices
        assert "cognitive_load_matrix" in matrices
        assert "knowledge_retention_matrix" in matrices

    @pytest.mark.unit
    def test_skill_acquisition_matrix_structure(self, client: TestClient):
        """Test SAM matrix has correct structure."""
        response = client.get("/api/jeeves-core/matrices")
        data = response.json()
        
        sam = data["matrices"]["skill_acquisition_matrix"]
        assert sam["name"] == "Skill Acquisition Matrix (SAM)"
        assert "dimensions" in sam
        assert "tracking_metrics" in sam
        assert "evolution_rules" in sam

    @pytest.mark.unit
    def test_cognitive_load_matrix_structure(self, client: TestClient):
        """Test CLOM matrix has correct structure."""
        response = client.get("/api/jeeves-core/matrices")
        data = response.json()
        
        clom = data["matrices"]["cognitive_load_matrix"]
        assert clom["name"] == "Cognitive Load Optimization Matrix (CLOM)"
        assert "load_thresholds" in clom
        assert "intervention_protocols" in clom
        assert clom["load_thresholds"]["optimal_zone"]["min"] == 0.4
        assert clom["load_thresholds"]["optimal_zone"]["max"] == 0.7

    @pytest.mark.unit
    def test_apply_matrix_rules(self, client: TestClient, sample_user_state: dict):
        """Test applying matrix rules to learner state."""
        response = client.post("/api/jeeves-core/matrices/apply", json=sample_user_state)
        assert response.status_code == 200
        data = response.json()
        
        assert data["success"] is True
        assert "recommendations" in data
        # With retention_rate=0.65 and cognitive_load=0.72
        # Should recommend increasing spaced repetition and possibly reducing complexity
        assert data["recommendations"]["practice_schedule"] == "increase_spaced_repetition"

    @pytest.mark.unit
    def test_create_cocoding_session(self, client: TestClient, sample_cocoding_request: dict):
        """Test creating a co-coding session."""
        response = client.post("/api/jeeves-core/co-coding/session", json=sample_cocoding_request)
        assert response.status_code == 200
        data = response.json()
        
        assert data["success"] is True
        session = data["session"]
        assert "id" in session
        assert session["user_id"] == "test_user_123"
        assert session["pipeline"] == "npc"
        assert session["skill_level"] == "intermediate"
        assert session["system_laws_loaded"] is True
        assert "jeeves_greeting" in session

    @pytest.mark.unit
    def test_prompt_refinement(self, client: TestClient):
        """Test prompt refinement endpoint."""
        response = client.post(
            "/api/jeeves-core/prompt/refine",
            json={
                "original_prompt": "make npc",
                "context": "game development for RPG",
                "target_pipeline": "npc"
            }
        )
        assert response.status_code == 200
        data = response.json()
        
        assert data["success"] is True
        refinement = data["refinement"]
        assert "original" in refinement
        assert "refined" in refinement
        assert "suggestions" in refinement
        assert "quality_score" in refinement
        # With context provided, quality should be higher
        assert refinement["quality_score"] >= 50

    @pytest.mark.unit
    def test_prompt_refinement_suggestions(self, client: TestClient):
        """Test that prompt refinement provides helpful suggestions."""
        response = client.post(
            "/api/jeeves-core/prompt/refine",
            json={"original_prompt": "npc"}  # Very short, no context
        )
        data = response.json()
        
        suggestions = data["refinement"]["suggestions"]
        # Should suggest adding more detail due to short prompt
        assert any("detail" in s.lower() for s in suggestions)
        # Quality score should be lower for minimal prompt
        assert data["refinement"]["quality_score"] < 70
