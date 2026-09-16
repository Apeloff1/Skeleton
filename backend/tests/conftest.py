"""
Pytest Configuration and Fixtures for Tutolage Backend Tests.

The backend test tree contains two classes of tests:

* hermetic tests that exercise the FastAPI app directly; and
* live/integration probes that target a separately running backend stack.

Generic CI must never fabricate an external deployment merely to collect the latter.
When no live backend is configured we therefore exclude files that explicitly bind
to that contract before Python imports them. Supplying a supported backend URL (or
explicitly opting into live tests) collects the full live suite normally.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Generator

import httpx
import pytest
from starlette.testclient import TestClient

# Starlette's in-process TestClient identifies itself as ``testclient``. Keep the
# production limiter unchanged while preventing one session-scoped synthetic client
# from exhausting a single token bucket across thousands of hermetic assertions.
_rate_limit_exempt = [
    value.strip()
    for value in os.environ.get("RATE_LIMIT_EXEMPT", "127.0.0.1,::1,localhost").split(",")
    if value.strip()
]
if "testclient" not in _rate_limit_exempt:
    _rate_limit_exempt.append("testclient")
os.environ["RATE_LIMIT_EXEMPT"] = ",".join(_rate_limit_exempt)

# Import the FastAPI app only after the test-only environment boundary above is set.
sys.path.insert(0, "/app/backend")
from server import app


_LIVE_ENV_KEYS = (
    "EXPO_PUBLIC_BACKEND_URL",
    "EXPO_BACKEND_URL",
    "BACKEND_TEST_URL",
    "RUN_LIVE_BACKEND_TESTS",
)
_LIVE_SOURCE_SENTINELS = (
    "EXPO_PUBLIC_BACKEND_URL",
    "EXPO_BACKEND_URL",
    "/app/frontend/.env",
)
# These suites intentionally make real HTTP requests instead of using the shared
# TestClient fixture. Running them without a separately started backend produces
# connection-refused/remote-preview failures that say nothing about hermetic CI.
_LIVE_TEST_FILES = frozenset(
    {
        "test_galaxy_build_pipeline_regression.py",
        "test_galaxy_manifest_constants.py",
        "test_iteration_5_codegen_refactor.py",
        "test_governance.py",
    }
)


def _live_backend_configured() -> bool:
    """Return True only when live backend testing is explicitly configured."""
    return any(os.environ.get(key, "").strip() for key in _LIVE_ENV_KEYS)


def pytest_ignore_collect(collection_path: Path, config: pytest.Config) -> bool | None:
    """Keep external-live probes out of hermetic CI before module import.

    Historical integration suites resolve deployment URLs at module import time or
    hard-code a live backend. Without this collection boundary those modules fail
    before pytest can skip them, producing misleading failures in ordinary backend
    CI. Live CI/local environments remain available through the explicit opt-in.
    """
    del config
    if _live_backend_configured():
        return None

    path = Path(collection_path)
    if path.suffix != ".py" or not path.name.startswith("test_"):
        return None

    if path.name in _LIVE_TEST_FILES:
        return True

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
