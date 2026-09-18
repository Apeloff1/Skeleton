"""Offline contract tests for the unified API/CLI invoke envelope (#953)."""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from skeleton.__main__ import main
from skeleton.api import command_routes
from skeleton.application import (
    SCHEMA_VERSION,
    CommandError,
    CommandService,
    invoke_unified,
    normalize_request,
    parity_matrix,
)
from skeleton.application.contract_safety import MAX_OUTPUT_STRING_CHARS, REDACTED
from skeleton.observability.redaction import REDACTED as OBS_REDACTED


class _FakeHit:
    fragment_id = "frag-1"
    plane = "rag"
    content = "alpha"
    score = 0.42
    provenance = "fixture"


class _FakeRetriever:
    def __init__(self) -> None:
        self.calls: list[tuple[str, int, bool]] = []

    def retrieve(self, query: str, k: int = 8, use_cache: bool = True):
        self.calls.append((query, k, use_cache))
        return [_FakeHit()]


class _FakePlanner:
    def plan_build(self, vision: str = ""):
        return {"era": "extraction_now", "seed": "abc", "briefing": vision, "authored": "local"}


class _FakeLearning:
    def snapshot(self, weakest: int = 3):
        return SimpleNamespace(ready_lesson_ids=("lesson-1",), weakest_skill_ids=("skill-1",)[:weakest])

    def mastery(self, skill_id: str):
        return 0.5 if skill_id == "skill-1" else None


class _FakeLedger:
    def stats(self):
        return {"entries": 1, "queries": 0}

    def trace(self, entry_id: str):
        return [SimpleNamespace(to_dict=lambda: {"entry_id": entry_id, "source": "fixture"})]


class _BrokenRetriever:
    def retrieve(self, query: str, k: int = 8, use_cache: bool = True):
        raise RuntimeError("plane exploded token=super-secret-token")


class _FakeState:
    def __init__(self) -> None:
        self.retriever = _FakeRetriever()
        self.genesis = SimpleNamespace(handles={"quad": self.retriever})
        self.jeeves = _FakePlanner()
        self.learning = _FakeLearning()
        self.ledger = _FakeLedger()
        self.memory_trinity = None
        self.registry = None
        self.gameforge = None

    def is_healthy(self):
        return {"overall": True, "checks": {"fake": {"status": "ok"}}}


def _envelope(command: str, arguments: dict | None = None, **extra) -> dict:
    body = {
        "schema_version": SCHEMA_VERSION,
        "command": command,
        "arguments": arguments or {},
        "correlation_id": "corr-fixture-1",
        "mode": "sync",
    }
    body.update(extra)
    return body


def test_normalize_request_is_deterministic_and_aliases_arguments():
    left = normalize_request(
        {
            "schema_version": 1,
            "command": " Retrieve ",
            "arguments": {"Q": "hello", "Top-K": 2},
            "correlation_id": "corr-a",
        }
    )
    right = normalize_request(
        {
            "schema_version": 1,
            "command": "retrieve",
            "arguments": {"search": "hello", "limit": 2},
            "correlation_id": "corr-a",
        }
    )
    assert left == right
    assert left.command == "retrieve"
    assert dict(left.arguments) == {"k": 2, "query": "hello"}
    assert left.mode == "sync"


def test_malformed_input_and_unknown_envelope_fields_fail_closed():
    missing = invoke_unified(_FakeState(), ["not", "an", "object"])
    assert missing.ok is False
    assert missing.to_payload()["error"]["code"] == "invalid_argument"

    unknown = invoke_unified(_FakeState(), _envelope("status", extra_field=True))
    payload = unknown.to_payload()
    assert unknown.ok is False
    assert payload["error"]["code"] == "invalid_argument"
    assert "extra_field" in json.dumps(payload)


def test_unknown_schema_version_fails_closed():
    result = invoke_unified(_FakeState(), _envelope("status") | {"schema_version": 99})
    payload = result.to_payload()
    assert result.ok is False
    assert result.exit_code == 2
    assert result.http_status == 422
    assert payload["error"]["code"] == "unknown_version"
    assert payload["correlation_id"] == "corr-fixture-1"
    assert payload["schema_version"] == SCHEMA_VERSION


def test_async_mode_is_explicitly_unsupported():
    result = invoke_unified(_FakeState(), _envelope("status") | {"mode": "async"})
    payload = result.to_payload()
    assert result.ok is False
    assert result.exit_code == 3
    assert result.http_status == 501
    assert payload["error"]["code"] == "async_unsupported"
    assert payload["mode"] == "sync"


def test_secret_bearing_arguments_are_rejected_without_echoing_values():
    result = invoke_unified(
        _FakeState(),
        _envelope("retrieve", {"query": "hello", "api_key": "super-secret-token"}),
    )
    dumped = json.dumps(result.to_payload())
    assert result.ok is False
    assert result.to_payload()["error"]["code"] == "invalid_argument"
    assert "super-secret-token" not in dumped
    assert "secret-bearing" in result.to_payload()["error"]["message"]


def test_subsystem_failure_is_stable_and_redacted():
    state = _FakeState()
    state.retriever = _BrokenRetriever()
    state.genesis = SimpleNamespace(handles={"quad": state.retriever})
    result = invoke_unified(state, _envelope("retrieve", {"query": "hello"}))
    payload = result.to_payload()
    dumped = json.dumps(payload)
    assert result.ok is False
    assert payload["error"]["code"] == "unavailable"
    assert payload["error"]["details"]["exception"] == "RuntimeError"
    assert "super-secret-token" not in dumped
    assert payload["correlation_id"] == "corr-fixture-1"


def test_correlation_id_propagates_from_envelope_and_header():
    envelope = _envelope("status")
    envelope.pop("correlation_id")
    from_header = invoke_unified(_FakeState(), envelope, correlation_id="header-corr-1")
    assert from_header.ok is True
    assert from_header.correlation_id == "header-corr-1"
    assert from_header.to_payload()["correlation_id"] == "header-corr-1"

    body_wins = invoke_unified(
        _FakeState(),
        _envelope("status") | {"correlation_id": "body-corr-1"},
        correlation_id="header-corr-1",
    )
    assert body_wins.correlation_id == "body-corr-1"

    malformed = invoke_unified(_FakeState(), _envelope("status") | {"correlation_id": "bad id"})
    assert malformed.ok is False
    assert malformed.to_payload()["error"]["code"] == "invalid_argument"


def test_retrieve_plan_and_evidence_adapters_are_thin_and_offline():
    state = _FakeState()
    retrieve = invoke_unified(state, _envelope("retrieve", {"query": "hello", "k": 2}))
    assert retrieve.ok is True
    assert retrieve.data["results"][0]["id"] == "frag-1"
    assert state.retriever.calls == [("hello", 2, True)]

    plan = invoke_unified(state, _envelope("plan", {"era": "extraction_now"}))
    assert plan.ok is True
    assert plan.data["vision"] == "extraction_now"
    assert plan.data["plan"]["authored"] == "local"

    evidence = invoke_unified(state, _envelope("evidence", {"action": "snapshot"}))
    assert evidence.ok is True
    assert evidence.data["ready_lesson_ids"] == ["lesson-1"]

    mastery = invoke_unified(state, _envelope("evidence", {"action": "mastery", "skill_id": "skill-1"}))
    assert mastery.data["mastery"] == 0.5

    provenance = invoke_unified(state, _envelope("evidence", {"action": "provenance"}))
    assert provenance.data["stats"]["entries"] == 1


def test_uninitialized_subsystems_fail_closed_without_inventing_logic():
    empty = SimpleNamespace(
        genesis=None,
        retriever=None,
        jeeves=None,
        learning=None,
        ledger=None,
        memory_trinity=None,
        registry=None,
        gameforge=None,
        is_healthy=lambda: {"overall": False, "checks": {}},
    )
    for command, arguments in (
        ("retrieve", {"query": "hello"}),
        ("plan", {"vision": "extraction_now"}),
        ("evidence", {"action": "snapshot"}),
    ):
        result = invoke_unified(empty, _envelope(command, arguments))
        assert result.ok is False
        assert result.to_payload()["error"]["code"] == "unavailable"


def test_output_is_bounded_and_redacts_handler_secrets():
    service = CommandService()
    service.register("status", lambda _payload: {"token": "leak-me", "note": "x" * (MAX_OUTPUT_STRING_CHARS + 50)})
    result = invoke_unified(_FakeState(), _envelope("status"), service=service)
    payload = result.to_payload()
    assert payload["data"]["token"] == REDACTED == OBS_REDACTED
    assert payload["data"]["note"].endswith("…")
    assert len(payload["data"]["note"]) <= MAX_OUTPUT_STRING_CHARS + 1


def test_legacy_execute_path_remains_compatible_with_unified_payload_shape():
    from skeleton.application import build_runtime_command_service

    legacy = build_runtime_command_service(_FakeState()).execute("status")
    unified = invoke_unified(_FakeState(), _envelope("status"))
    legacy_payload = legacy.to_payload()
    unified_payload = unified.to_payload()
    assert legacy.ok is unified.ok is True
    assert legacy_payload["data"] == unified_payload["data"]
    assert legacy_payload["contract_version"] == unified_payload["contract_version"] == parity_matrix()["contract_version"]
    assert {"schema_version", "mode", "correlation_id", "ok", "command"} <= set(legacy_payload)


def test_cli_invoke_uses_the_same_envelope_as_the_contract(capsys):
    envelope = {
        "schema_version": 1,
        "command": "status",
        "arguments": {},
        "correlation_id": "cli-corr-1",
        "mode": "sync",
    }
    exit_code = main(["invoke", json.dumps(envelope)])
    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["ok"] is True
    assert payload["command"] == "status"
    assert payload["correlation_id"] == "cli-corr-1"
    assert payload["schema_version"] == 1


def test_cli_invoke_unknown_version_and_malformed_json_are_stable(capsys):
    exit_code = main(["invoke", json.dumps({"schema_version": 2, "command": "status"})])
    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 2
    assert payload["error"]["code"] == "unknown_version"

    exit_code = main(["invoke", "{not-json"])
    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 2
    assert payload["error"]["code"] == "invalid_argument"
    assert "{not-json" not in json.dumps(payload)


def test_api_invoke_matches_cli_and_requires_seal_for_protected_commands(monkeypatch):
    observed = []

    def fake_require_seal(value):
        observed.append(value)
        if value != "valid-seal":
            raise HTTPException(status_code=401, detail="invalid seal")
        return "attester"

    monkeypatch.setattr(command_routes, "require_seal", fake_require_seal)
    public = asyncio.run(
        command_routes.invoke_command(
            _envelope("status"),
            state=_FakeState(),
            x_gf_seal=None,
            x_request_id=None,
        )
    )
    assert public["ok"] is True
    assert public["correlation_id"] == "corr-fixture-1"
    assert observed == []

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            command_routes.invoke_command(
                _envelope("retrieve", {"query": "hello"}),
                state=_FakeState(),
                x_gf_seal=None,
                x_request_id=None,
            )
        )
    assert exc_info.value.status_code == 401

    protected = asyncio.run(
        command_routes.invoke_command(
            _envelope("retrieve", {"query": "hello"}),
            state=_FakeState(),
            x_gf_seal="valid-seal",
            x_request_id=None,
        )
    )
    assert observed == [None, "valid-seal"]
    assert protected["ok"] is True
    assert protected["command"] == "retrieve"
    assert protected["data"]["count"] == 1


def test_header_correlation_fills_missing_envelope_id(monkeypatch):
    monkeypatch.setattr(command_routes, "require_seal", lambda _value: "attester")
    envelope = _envelope("retrieve", {"query": "hello"})
    envelope.pop("correlation_id")
    payload = asyncio.run(
        command_routes.invoke_command(
            envelope,
            state=_FakeState(),
            x_gf_seal="valid-seal",
            x_request_id="header-from-api",
        )
    )
    assert payload["correlation_id"] == "header-from-api"


def test_normalize_request_rejects_alias_collisions():
    with pytest.raises(CommandError) as exc_info:
        normalize_request(_envelope("retrieve", {"q": "a", "query": "b"}))
    assert exc_info.value.code == "invalid_argument"
    assert "collided" in exc_info.value.message