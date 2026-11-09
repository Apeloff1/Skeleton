"""
Pytest Configuration and Fixtures for Tutolage Backend Tests

Note: Due to the async nature of the FastAPI app's lifespan (which uses motor for MongoDB),
we need to be careful about event loop management. Using httpx.Client instead of TestClient
provides better compatibility with async lifespans.
"""

from typing import Generator
import pytest
import httpx
from starlette.testclient import TestClient

# Import the FastAPI app
import sys
sys.path.insert(0, '/app/backend')
from server import app


# ============================================================================
# Client Fixtures
# ============================================================================

@pytest.fixture(scope="session")
def client() -> Generator[TestClient, None, None]:
    """
    Create a synchronous test client with session scope.
    Session scope ensures the lifespan events run once for all tests.
    """
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


# ============================================================================
# Test Data Fixtures
# ============================================================================

@pytest.fixture
def sample_npc_request() -> dict:
    """Sample NPC generation request."""
    return {
        "description": "A wise old wizard with a mysterious past",
        "include_dialogue": True,
        "include_quests": True,
        "complexity_level": "moderate"
    }


@pytest.fixture
def sample_combat_request() -> dict:
    """Sample combat system generation request."""
    return {
        "style": "turn_based",
        "include_magic": True,
        "include_status_effects": True,
        "party_based": True,
        "enemy_ai_complexity": "moderate"
    }


@pytest.fixture
def sample_animation_request() -> dict:
    """Sample animation generation request."""
    return {
        "description": "humanoid character walking",
        "looping": True,
        "include_root_motion": True
    }


@pytest.fixture
def sample_cocoding_request() -> dict:
    """Sample co-coding session request."""
    return {
        "user_id": "test_user_123",
        "pipeline": "npc",
        "initial_prompt": "Create a friendly merchant NPC",
        "skill_level": "intermediate"
    }


@pytest.fixture
def sample_user_state() -> dict:
    """Sample learner state for matrix application."""
    return {
        "retention_rate": 0.65,
        "cognitive_load": 0.72,
        "time_since_review_hours": 48,
        "skill_level": "intermediate"
    }


# ============================================================================
# Utility Fixtures
# ============================================================================

@pytest.fixture
def api_base_url() -> str:
    """Base URL for API endpoints."""
    return "/api"
