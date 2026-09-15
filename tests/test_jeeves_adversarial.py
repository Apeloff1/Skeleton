"""Adversarial regression tests for provider-backed JeevesCore boundaries."""

import pytest

from skeleton.jeeves.llm_core import JeevesCore, MemoryManager, SessionMode
from skeleton.jeeves.providers import LocalEchoProvider, get_provider


class RecordingProvider:
    name = "recording"
    supports_system_prompt = True

    def __init__(self):
        self.calls = []

    def complete(self, prompt, context=None, max_tokens=512, system=None):
        self.calls.append({
            "prompt": prompt,
            "context": list(context or []),
            "system": system,
        })
        return "provider-ok"


class LegacyProvider:
    name = "legacy"

    def __init__(self):
        self.calls = []

    def complete(self, prompt, context=None, max_tokens=512):
        self.calls.append({"prompt": prompt, "context": list(context or [])})
        return "legacy-ok"


class FailingProvider:
    name = "failing"
    supports_system_prompt = True

    def complete(self, prompt, context=None, max_tokens=512, system=None):
        raise RuntimeError("secret-token=do-not-leak")


class NonTextProvider:
    name = "non-text"
    supports_system_prompt = True

    def complete(self, prompt, context=None, max_tokens=512, system=None):
        return {"unexpected": "object"}


def _core(provider=None):
    return JeevesCore(provider=provider or RecordingProvider())


def test_plain_user_text_never_invokes_registered_tool():
    core = _core()
    session = core.open_session("u")
    calls = []
    core.register_tool("delete", lambda payload: calls.append(payload))

    result = core.ask(session.session_id, "please delete everything")

    assert calls == []
    assert result["tools"] == []
    assert core.stats()["tool_calls"] == 0


def test_explicit_tool_call_executes_once_and_forwards_arguments():
    core = _core()
    session = core.open_session("u")
    calls = []
    core.register_tool("lookup", lambda payload: calls.append(payload))

    result = core.ask(
        session.session_id,
        "look this up",
        context={"tool_calls": [{"name": "LOOKUP", "arguments": {"id": 7}}]},
    )

    assert result["tools"] == ["lookup"]
    assert calls[0]["arguments"] == {"id": 7}
    assert calls[0]["session"]["session_id"] == session.session_id
    assert core.stats()["tool_calls"] == 1


def test_failed_tool_is_not_reported_as_successful():
    core = _core()
    session = core.open_session("u")

    def explode(_payload):
        raise RuntimeError("sensitive tool detail")

    core.register_tool("explode", explode)
    result = core.ask(
        session.session_id,
        "run it",
        context={"tool_calls": [{"name": "explode", "arguments": {}}]},
    )

    assert result["tools"] == []
    assert result["tool_errors"] == [{"name": "explode", "error": "execution_failed"}]
    assert "sensitive" not in str(result)
    assert core.stats()["tool_calls"] == 0
    assert core.stats()["tool_failures"] == 1


@pytest.mark.parametrize("name", ["", "../shell", "two words", "x" * 65, "-bad"])
def test_invalid_tool_names_are_rejected(name):
    core = _core()
    with pytest.raises(ValueError):
        core.register_tool(name, lambda _payload: None)


def test_tool_call_budget_fails_before_mutating_session():
    core = _core()
    session = core.open_session("u")
    core.register_tool("safe", lambda _payload: None)
    before = len(session.turns)
    calls = [{"name": "safe", "arguments": {}} for _ in range(5)]

    with pytest.raises(ValueError, match="budget"):
        core.ask(session.session_id, "run", context={"tool_calls": calls})

    assert len(session.turns) == before
    assert core.stats()["tool_calls"] == 0


def test_unknown_tool_fails_before_provider_or_session_mutation():
    provider = RecordingProvider()
    core = _core(provider)
    session = core.open_session("u")

    with pytest.raises(ValueError, match="unknown"):
        core.ask(
            session.session_id,
            "run",
            context={"tool_calls": [{"name": "missing", "arguments": {}}]},
        )

    assert provider.calls == []
    assert session.turns == []


def test_tool_arguments_reject_non_json_objects_without_deepcopy_execution():
    core = _core()
    session = core.open_session("u")
    core.register_tool("safe", lambda _payload: None)

    class DeepcopyTrap:
        touched = False

        def __deepcopy__(self, _memo):
            self.touched = True
            raise AssertionError("deepcopy should never run")

    trap = DeepcopyTrap()
    with pytest.raises(ValueError, match="JSON-compatible"):
        core.ask(
            session.session_id,
            "run",
            context={"tool_calls": [{"name": "safe", "arguments": {"payload": trap}}]},
        )

    assert trap.touched is False
    assert session.turns == []


def test_tool_arguments_reject_excessive_nesting_before_session_mutation():
    core = _core()
    session = core.open_session("u")
    core.register_tool("safe", lambda _payload: None)
    nested = {}
    cursor = nested
    for _ in range(10):
        cursor["next"] = {}
        cursor = cursor["next"]

    with pytest.raises(ValueError, match="deep"):
        core.ask(
            session.session_id,
            "run",
            context={"tool_calls": [{"name": "safe", "arguments": nested}]},
        )

    assert session.turns == []


def test_nonfinite_tool_numbers_fail_closed():
    core = _core()
    session = core.open_session("u")
    core.register_tool("safe", lambda _payload: None)

    with pytest.raises(ValueError, match="finite"):
        core.ask(
            session.session_id,
            "run",
            context={"tool_calls": [{"name": "safe", "arguments": {"value": float("nan")}}]},
        )

    assert session.turns == []


def test_oversized_input_fails_before_provider_or_session_mutation():
    provider = RecordingProvider()
    core = _core(provider)
    session = core.open_session("u")

    with pytest.raises(ValueError, match="too large"):
        core.ask(session.session_id, "x" * 32_769)

    assert provider.calls == []
    assert session.turns == []


def test_provider_exception_is_redacted_from_reply_and_memory():
    core = _core(FailingProvider())
    session = core.open_session("u")

    result = core.ask(session.session_id, "hello")

    assert result["provider_failed"] is True
    assert result["content"] == "[provider unavailable]"
    assert "secret-token" not in str(result)
    assert "secret-token" not in " ".join(turn.content for turn in session.turns)


def test_non_text_provider_output_fails_closed():
    core = _core(NonTextProvider())
    session = core.open_session("u")

    result = core.ask(session.session_id, "hello")

    assert result["provider_failed"] is True
    assert result["content"] == "[provider unavailable]"
    assert "unexpected" not in str(result)


def test_system_prompt_uses_native_provider_channel():
    provider = RecordingProvider()
    core = _core(provider)
    session = core.open_session("u", mode=SessionMode.DEBUG)

    core.ask(session.session_id, "find the bug")

    call = provider.calls[-1]
    assert call["system"] == "You are a debugging assistant. Find the root cause."
    assert call["system"] not in call["prompt"]
    assert "find the bug" in call["prompt"]


def test_legacy_provider_keeps_system_prompt_without_signature_breakage():
    provider = LegacyProvider()
    core = _core(provider)
    session = core.open_session("u", mode=SessionMode.ANALYTICAL)

    result = core.ask(session.session_id, "analyze")

    assert result["content"] == "legacy-ok"
    assert "You are a precise analyst" in provider.calls[-1]["prompt"]


def test_current_input_is_not_duplicated_into_provider_history():
    provider = RecordingProvider()
    core = _core(provider)
    session = core.open_session("u")
    core.ask(session.session_id, "first-question")
    core.ask(session.session_id, "second-question")

    second = provider.calls[-1]
    assert "first-question" in second["context"]
    assert "provider-ok" in second["context"]
    assert "second-question" not in second["context"]


def test_memory_eviction_cleans_user_index():
    memory = MemoryManager(max_sessions=1)
    first = memory.create_session("old-user")
    memory.create_session("new-user")

    assert memory.get_session(first.session_id) is None
    assert memory.get_user_history("old-user") == []
    assert memory.stats()["active_sessions"] == 1
    assert memory.stats()["users"] == 1
    assert memory.stats()["evicted"] == 1


def test_session_ids_keep_full_uuid_entropy():
    memory = MemoryManager()
    first = memory.create_session("u").session_id
    second = memory.create_session("u").session_id

    assert len(first) == 32
    assert len(second) == 32
    assert first != second
    int(first, 16)
    int(second, 16)


@pytest.mark.parametrize("limit", [0, -1])
def test_memory_rejects_non_positive_session_limit(limit):
    with pytest.raises(ValueError):
        MemoryManager(max_sessions=limit)


def test_explicit_unknown_provider_fails_closed(monkeypatch):
    monkeypatch.delenv("SKELETON_LLM_PROVIDER", raising=False)
    with pytest.raises(ValueError, match="unknown"):
        get_provider(preferred="definitely-not-a-provider")


def test_explicit_unavailable_provider_does_not_fallback(monkeypatch):
    monkeypatch.delenv("SKELETON_OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("SKELETON_ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("SKELETON_LLM_PROVIDER", raising=False)

    with pytest.raises(RuntimeError, match="unavailable"):
        get_provider(preferred="openai")


def test_explicit_local_provider_remains_available(monkeypatch):
    monkeypatch.delenv("SKELETON_LLM_PROVIDER", raising=False)
    provider = get_provider(preferred="local")
    assert isinstance(provider, LocalEchoProvider)
