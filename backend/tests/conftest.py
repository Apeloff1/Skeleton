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
_BACKEND_ROOT = Path(__file__).resolve().parents[1]
for _candidate in (str(_BACKEND_ROOT), "/app/backend"):
    if _candidate not in sys.path and Path(_candidate).is_dir():
        sys.path.insert(0, _candidate)
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


_AI_CHAT_ROUTE_TEST_FILES = {
    "test_ai_chat_context_idempotency.py",
    "test_ai_chat_conversation_authority.py",
    "test_ai_chat_conversation_finalization.py",
    "test_ai_chat_engine_cutover.py",
    "test_ai_chat_local_engine_e2e.py",
    "test_ai_chat_memory_policy.py",
    "test_ai_chat_turn_route_cutover.py",
}


@pytest.fixture(autouse=True)
def ai_chat_turn_test_authority(request: pytest.FixtureRequest, monkeypatch):
    """Keep route tests hermetic while exercising the real turn lifecycle."""

    if Path(str(request.path)).name not in _AI_CHAT_ROUTE_TEST_FILES:
        yield None
        return

    import routes.ai as ai
    from core.chat_turn_lifecycle import ChatTurnLifecycle
    from skeleton.persistence.chat_turn_repository import SQLiteChatTurnRepository

    class AsyncSQLiteTurnAuthority:
        def __init__(self) -> None:
            self.repo = SQLiteChatTurnRepository()

        async def create_operation(self, **kwargs):
            return self.repo.create_operation(**kwargs)

        async def get_operation(self, operation_id, **kwargs):
            return self.repo.get_operation(operation_id, **kwargs)

        async def append_event(self, event, **kwargs):
            return self.repo.append_event(event, **kwargs)

        async def list_events(self, operation_id, **kwargs):
            return self.repo.list_events(operation_id, **kwargs)

    authority = AsyncSQLiteTurnAuthority()
    monkeypatch.setattr(
        ai,
        "chat_turn_lifecycle",
        ChatTurnLifecycle(authority),
    )
    try:
        yield authority
    finally:
        authority.repo.close()
