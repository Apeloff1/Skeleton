"""
Pytest Configuration and Fixtures for Tutolage Backend Tests.

The backend test tree contains two classes of tests:

* hermetic tests that exercise the FastAPI app directly; and
* live/integration probes that target an externally running Expo/backend stack.

Generic CI must never fabricate an external deployment merely to collect the latter.
When no Expo backend URL is configured we therefore exclude files that explicitly
bind to that live contract before Python imports them. Supplying either supported
backend URL opts the full live suite back in automatically.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Generator

import httpx
import pytest
from starlette.testclient import TestClient

# Import the FastAPI app.
sys.path.insert(0, "/app/backend")
from server import app


_LIVE_ENV_KEYS = ("EXPO_PUBLIC_BACKEND_URL", "EXPO_BACKEND_URL")
_LIVE_SOURCE_SENTINELS = (
    "EXPO_PUBLIC_BACKEND_URL",
    "EXPO_BACKEND_URL",
    "/app/frontend/.env",
)


def _live_backend_configured() -> bool:
    """Return True only when a non-empty external backend URL is configured."""
    return any(os.environ.get(key, "").strip() for key in _LIVE_ENV_KEYS)


def pytest_ignore_collect(collection_path: Path, config: pytest.Config) -> bool | None:
    """Keep external-live probes out of hermetic CI before module import.

    A large historical integration suite resolves its deployment URL at module import
    time. Without this collection boundary those modules fail before pytest can skip
    them, producing dozens of misleading collection errors in ordinary backend CI.
    Live CI/local environments remain unchanged: configuring either supported URL
    collects every file normally.
    """
    del config
    if _live_backend_configured():
        return None

    path = Path(collection_path)
    if path.suffix != ".py" or not path.name.startswith("test_"):
        return None

    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return None

    if any(sentinel in source for sentinel in _LIVE_SOURCE_SENTINELS):
        return True
    return None


# ============================================================================
# Client Fixtures
# ============================================================================

@pytest.fixture(scope="session")
def client() -> Generator[TestClient, None, None]:
    """Create a synchronous test client with session scope."""
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
        "complexity_level": "moderate",
    }


@pytest.fixture
def sample_combat_request() -> dict:
    """Sample combat system generation request."""
    return {
        "style": "turn_based",
        "include_magic": True,
        "include_status_effects": True,
        "party_based": True,
        "enemy_ai_complexity": "moderate",
    }


@pytest.fixture
def sample_animation_request() -> dict:
    """Sample animation generation request."""
    return {
        "description": "humanoid character walking",
        "looping": True,
        "include_root_motion": True,
    }


@pytest.fixture
def sample_cocoding_request() -> dict:
    """Sample co-coding session request."""
    return {
        "user_id": "test_user_123",
        "pipeline": "npc",
        "initial_prompt": "Create a friendly merchant NPC",
        "skill_level": "intermediate",
    }


@pytest.fixture
def sample_user_state() -> dict:
    """Sample learner state for matrix application."""
    return {
        "retention_rate": 0.65,
        "cognitive_load": 0.72,
        "time_since_review_hours": 48,
        "skill_level": "intermediate",
    }


# ============================================================================
# Utility Fixtures
# ============================================================================

@pytest.fixture
def api_base_url() -> str:
    """Base URL for API endpoints."""
    return "/api"
