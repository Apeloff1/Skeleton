"""
Tests for Text-to-Animation Pipeline
"""

import pytest
from fastapi.testclient import TestClient


class TestAnimationPipeline:
    """Test suite for Animation Pipeline endpoints."""

    @pytest.mark.unit
    def test_animation_overview(self, client: TestClient):
        """Test animation pipeline overview endpoint."""
        response = client.get("/api/animation-pipeline/overview")
        assert response.status_code == 200
        data = response.json()
        
        assert "pipeline" in data
        assert "capabilities" in data
        assert "rig_types" in data
        assert "animation_types" in data

    @pytest.mark.unit
    def test_generate_humanoid_rig(self, client: TestClient):
        """Test generating a humanoid skeleton."""
        response = client.post(
            "/api/animation-pipeline/rig/generate",
            json={
                "description": "humanoid character",
                "include_fingers": True,
                "include_face_rig": False
            }
        )
        assert response.status_code == 200
        data = response.json()
        
        assert data["success"] is True
        skeleton = data["skeleton"]
        assert "bones" in skeleton
        assert "ik_chains" in skeleton
        assert skeleton["type"] == "humanoid"
        assert len(skeleton["bones"]) > 20  # Humanoid has 24+ bones

    @pytest.mark.unit
    def test_generate_rig_with_fingers(self, client: TestClient):
        """Test that finger bones are added when requested."""
        response = client.post(
            "/api/animation-pipeline/rig/generate",
            json={
                "description": "human",
                "include_fingers": True
            }
        )
        data = response.json()
        
        skeleton = data["skeleton"]
        assert skeleton["metadata"]["has_fingers"] is True
        # Should have additional finger bones
        assert skeleton["metadata"]["bone_count"] > 24

    @pytest.mark.unit
    def test_generate_animation(self, client: TestClient, sample_animation_request: dict):
        """Test generating keyframe animation."""
        response = client.post(
            "/api/animation-pipeline/animation/generate",
            json=sample_animation_request
        )
        assert response.status_code == 200
        data = response.json()
        
        assert data["success"] is True
        animation = data["animation"]
        assert "keyframes" in animation
        assert "duration" in animation
        assert animation["looping"] is True
        assert len(animation["keyframes"]) > 0

    @pytest.mark.unit
    def test_generate_blend_tree(self, client: TestClient):
        """Test generating a blend tree."""
        response = client.post(
            "/api/animation-pipeline/blend-tree/generate",
            json={
                "animations": ["idle", "walk", "run"],
                "blend_parameter": "speed",
                "blend_type": "1d"
            }
        )
        assert response.status_code == 200
        data = response.json()
        
        assert data["success"] is True
        blend_tree = data["blend_tree"]
        assert blend_tree["parameter"] == "speed"
        assert len(blend_tree["nodes"]) == 3

    @pytest.mark.unit
    def test_generate_state_machine(self, client: TestClient):
        """Test generating an animation state machine."""
        response = client.post(
            "/api/animation-pipeline/state-machine/generate",
            json={
                "states": ["idle", "walk", "run", "jump"],
                "default_state": "idle",
                "transitions": []
            }
        )
        assert response.status_code == 200
        data = response.json()
        
        assert data["success"] is True
        sm = data["state_machine"]
        assert sm["default_state"] == "idle"
        assert "idle" in sm["states"]
        assert "parameters" in sm
