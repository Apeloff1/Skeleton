"""Compatibility tests for the public and provider-backed Jeeves mode boundary."""

import pytest

from skeleton.jeeves.core import SessionMode as PublicSessionMode
from skeleton.jeeves.llm_core import JeevesCore, MemoryManager, SessionMode


class RecordingProvider:
    name = "recording"
    supports_system_prompt = True

    def __init__(self):
        self.systems = []

    def complete(self, prompt, context=None, max_tokens=512, system=None):
        self.systems.append(system)
        return "ok"


@pytest.mark.parametrize("public_mode", list(PublicSessionMode))
def test_public_session_modes_normalize_by_value(public_mode):
    provider = RecordingProvider()
    core = JeevesCore(provider=provider)

    session = core.open_session("u", mode=public_mode)

    assert isinstance(session.mode, SessionMode)
    assert session.mode.value == public_mode.value


@pytest.mark.parametrize(
    "public_mode",
    [
        PublicSessionMode.CO_CODING,
        PublicSessionMode.TACTICAL,
        PublicSessionMode.BUILDER,
        PublicSessionMode.CORTEX,
        PublicSessionMode.DEBUG,
    ],
)
def test_normalized_modes_preserve_system_policy(public_mode):
    provider = RecordingProvider()
    core = JeevesCore(provider=provider)
    session = core.open_session("u", mode=public_mode)

    result = core.ask(session.session_id, "hello")

    assert result["provider_failed"] is False
    assert result["mode"] == public_mode.value
    assert provider.systems[-1]


def test_unknown_mode_fails_closed_before_session_creation():
    core = JeevesCore(provider=RecordingProvider())

    with pytest.raises(ValueError, match="invalid session mode"):
        core.open_session("u", mode="not-a-mode")

    assert core.stats()["active_sessions"] == 0


@pytest.mark.parametrize("value", [True, False, 1.0, 2.5, "2", None])
def test_memory_capacity_requires_exact_positive_integer(value):
    with pytest.raises(ValueError, match="positive integer"):
        MemoryManager(max_sessions=value)  # type: ignore[arg-type]


def test_memory_capacity_accepts_positive_integer():
    manager = MemoryManager(max_sessions=1)
    assert manager.stats()["active_sessions"] == 0
