"""Second-wave adversarial regression tests for Jeeves trust boundaries."""

import pytest

from skeleton.jeeves.llm_core import JeevesCore, MemoryManager, _MAX_PROVIDER_OUTPUT_CHARS
from skeleton.jeeves.providers import (
    _MAX_PROVIDER_RESPONSE_BYTES,
    _read_provider_json,
    get_provider,
)


class RecordingProvider:
    name = "recording"
    supports_system_prompt = True

    def complete(self, prompt, context=None, max_tokens=512, system=None):
        return "provider-ok"


class _FakeResponse:
    def __init__(self, payload: bytes):
        self.payload = payload
        self.read_limit = None

    def read(self, limit: int) -> bytes:
        self.read_limit = limit
        return self.payload[:limit]


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
        allowed_tools=["lookup"],
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

    core.ask(
        session.session_id,
        "run lookup",
        context=context,
        allowed_tools=["lookup"],
    )

    assert session.turns[0].metadata == {"trace_id": "trace-1"}
    assert context["tool_calls"][0]["arguments"]["nested"]["secret"] == "do-not-store"
    assert seen[0]["arguments"]["nested"]["secret"] == "mutated"


def test_non_object_context_fails_before_session_mutation():
    core = _core()
    session = core.open_session("u")

    with pytest.raises(ValueError, match="context"):
        core.ask(session.session_id, "hello", context=["bad"])  # type: ignore[arg-type]

    assert session.turns == []


def test_allowed_tools_must_be_a_bounded_name_list():
    core = _core()
    session = core.open_session("u")
    core.register_tool("lookup", lambda _payload: None)

    with pytest.raises(ValueError, match="allowed_tools"):
        core.ask(
            session.session_id,
            "run lookup",
            context={"tool_calls": [{"name": "lookup", "arguments": {}}]},
            allowed_tools="lookup",  # type: ignore[arg-type]
        )

    assert session.turns == []


def test_allowed_tools_budget_fails_before_session_mutation():
    core = _core()
    session = core.open_session("u")
    core.register_tool("lookup", lambda _payload: None)

    with pytest.raises(ValueError, match="allowed_tools budget"):
        core.ask(
            session.session_id,
            "run lookup",
            context={"tool_calls": [{"name": "lookup", "arguments": {}}]},
            allowed_tools=["lookup"] * 5,
        )

    assert session.turns == []
    assert core.stats()["tool_calls"] == 0


def test_provider_response_reader_enforces_hard_byte_budget():
    response = _FakeResponse(b"x" * (_MAX_PROVIDER_RESPONSE_BYTES + 1))

    with pytest.raises(RuntimeError, match="size limit"):
        _read_provider_json(response)

    assert response.read_limit == _MAX_PROVIDER_RESPONSE_BYTES + 1


def test_provider_response_reader_redacts_malformed_payload_contents():
    response = _FakeResponse(b'{"secret":"do-not-echo"')

    with pytest.raises(RuntimeError, match="malformed JSON") as excinfo:
        _read_provider_json(response)

    assert "do-not-echo" not in str(excinfo.value)


def test_provider_response_reader_accepts_bounded_json():
    response = _FakeResponse(b'{"ok":true}')

    assert _read_provider_json(response) == {"ok": True}
    assert response.read_limit == _MAX_PROVIDER_RESPONSE_BYTES + 1


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



class OversizedProvider:
    name = "oversized"
    supports_system_prompt = True

    def complete(self, prompt, context=None, max_tokens=512, system=None):
        return "x" * (_MAX_PROVIDER_OUTPUT_CHARS + 1)


class InvalidNameProvider:
    name = {"secret": "provider-name-must-not-be-coerced"}
    supports_system_prompt = True

    def complete(self, prompt, context=None, max_tokens=512, system=None):
        return "ok"


def test_zero_context_window_does_not_expand_to_full_history():
    memory = MemoryManager()
    session = memory.create_session("u")
    session.add_turn("user", "one")
    session.add_turn("assistant", "two")

    with pytest.raises(ValueError, match="max_turns"):
        session.context_window(0)

    with pytest.raises(ValueError, match="max_turns"):
        session.context_window(False)


def test_zero_history_limit_does_not_return_all_sessions():
    memory = MemoryManager()
    memory.create_session("u")
    memory.create_session("u")

    with pytest.raises(ValueError, match="limit"):
        memory.get_user_history("u", limit=0)

    with pytest.raises(ValueError, match="limit"):
        memory.get_user_history("u", limit=False)


@pytest.mark.parametrize("user_id", ["", "   ", "x" * 257])
def test_memory_rejects_invalid_user_identifiers(user_id):
    memory = MemoryManager()

    with pytest.raises(ValueError, match="user_id"):
        memory.create_session(user_id)


def test_public_identifiers_are_canonicalized_before_storage_and_lookup():
    memory = MemoryManager(max_sessions=1)

    session = memory.create_session(" learner ")
    same_history = memory.get_user_history("learner", limit=1)

    assert session.user_id == "learner"
    assert same_history == [session]

    core = _core()
    bound = core.bind_era(" bronze ")
    assert bound["era"] == "bronze"


def test_oversized_provider_output_fails_closed_before_memory_growth():
    core = JeevesCore(provider=OversizedProvider())
    session = core.open_session("u")

    result = core.ask(session.session_id, "hello")

    assert result["provider_failed"] is True
    assert result["content"] == "[provider unavailable]"
    assert session.turns[-1].content == "[provider unavailable]"
    assert max(len(turn.content) for turn in session.turns) < _MAX_PROVIDER_OUTPUT_CHARS


def test_non_string_provider_name_is_never_coerced_into_results():
    core = JeevesCore(provider=InvalidNameProvider())
    session = core.open_session("u")

    result = core.ask(session.session_id, "hello")

    assert result["provider"] == "unknown"
    assert "secret" not in str(result)


def test_public_helper_inputs_fail_closed_on_wrong_shapes():
    core = _core()
    session = core.open_session("u")

    with pytest.raises(ValueError, match="session_id"):
        core.ask([], "hello")  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="code"):
        core.review_code(session.session_id, object())  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="code too large"):
        core.review_code(session.session_id, "x" * 262_145)

    with pytest.raises(ValueError, match="era"):
        core.bind_era("   ")

    with pytest.raises(ValueError, match="telemetry"):
        core.advise(session.session_id, [])  # type: ignore[arg-type]


def test_advise_validates_nested_telemetry_before_inspection():
    core = _core()
    session = core.open_session("u")
    nested = {}
    cursor = nested
    for _ in range(10):
        cursor["next"] = {}
        cursor = cursor["next"]

    with pytest.raises(ValueError, match="deep"):
        core.advise(session.session_id, nested)
