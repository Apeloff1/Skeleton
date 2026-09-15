"""Second-wave adversarial regression tests for Jeeves trust boundaries."""

import pytest

from skeleton.jeeves.llm_core import JeevesCore
from skeleton.jeeves.providers import get_provider


class RecordingProvider:
    name = "recording"
    supports_system_prompt = True

    def complete(self, prompt, context=None, max_tokens=512, system=None):
        return "provider-ok"


def _core():
    return JeevesCore(provider=RecordingProvider())


def test_duplicate_canonical_tool_registration_is_rejected():
    core = _core()
    original_calls = []
    replacement_calls = []
    core.register_tool("lookup", lambda payload: original_calls.append(payload))

    with pytest.raises(ValueError, match="already registered"):
        core.register_tool(" LOOKUP ", lambda payload: replacement_calls.append(payload))

    session = core.open_session("u")
    core.ask(
        session.session_id,
        "look this up",
        context={"tool_calls": [{"name": "lookup", "arguments": {}}]},
    )

    assert len(original_calls) == 1
    assert replacement_calls == []


def test_tool_capability_requests_are_not_persisted_or_aliased():
    core = _core()
    session = core.open_session("u")
    seen = []

    def mutate(payload):
        payload["arguments"]["nested"]["secret"] = "mutated"
        seen.append(payload)

    core.register_tool("lookup", mutate)
    context = {
        "trace_id": "trace-1",
        "tool_calls": [
            {
                "name": "lookup",
                "arguments": {"nested": {"secret": "do-not-store"}},
            }
        ],
    }

    core.ask(session.session_id, "run lookup", context=context)

    assert session.turns[0].metadata == {"trace_id": "trace-1"}
    assert context["tool_calls"][0]["arguments"]["nested"]["secret"] == "do-not-store"
    assert seen[0]["arguments"]["nested"]["secret"] == "mutated"


def test_non_object_context_fails_before_session_mutation():
    core = _core()
    session = core.open_session("u")

    with pytest.raises(ValueError, match="context"):
        core.ask(session.session_id, "hello", context=["bad"])  # type: ignore[arg-type]

    assert session.turns == []


@pytest.mark.parametrize("preferred", ["", "   "])
def test_explicit_blank_provider_fails_closed(monkeypatch, preferred):
    monkeypatch.delenv("SKELETON_LLM_PROVIDER", raising=False)

    with pytest.raises(ValueError, match="empty"):
        get_provider(preferred=preferred)


def test_blank_provider_environment_fails_closed(monkeypatch):
    monkeypatch.setenv("SKELETON_LLM_PROVIDER", "   ")

    with pytest.raises(ValueError, match="empty"):
        get_provider()


def test_whitespace_only_provider_key_is_unavailable(monkeypatch):
    monkeypatch.setenv("SKELETON_OPENAI_API_KEY", "   ")
    monkeypatch.delenv("SKELETON_LLM_PROVIDER", raising=False)

    with pytest.raises(RuntimeError, match="unavailable"):
        get_provider(preferred="openai")
