"""Regression contracts for the real installed-app AI chat smoke probe."""

from __future__ import annotations

import os
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from scripts import ai_chat_installed_smoke as smoke


class FakeApi:
    def __init__(self, *, receipts=True, durable=True, ready=True, replay=True):
        self.calls = []
        self.receipts = receipts
        self.durable = durable
        self.ready = ready
        self.replay = replay

    def request(self, method, path, body=None):
        self.calls.append((method, path, body))
        if path == "/api/auth/me":
            return {"authenticated": True, "user": {"email": "owner@example.invalid"}}
        if path == "/api/ai/chat/readiness":
            return {
                "schema_version": "backend.ai.chat-readiness.v1",
                "available": self.ready,
                "checks": {name: {"available": self.ready, "code": "ready" if self.ready else "local_guard_unavailable"} for name in ("conversation_storage", "engine", "models")},
                "models": {
                    "automatic_available": False,
                    "models": [{"available": self.ready, "selectable": True,
                                "provider_id": "openai", "model_id": "qualified-text",
                                "max_output_tokens": 512}],
                },
            }
        if method == "POST" and path == "/api/v1/conversations":
            return {"thread": {"thread_id": "thread-1", "version": 1}}
        if method == "POST" and path == "/api/ai/chat":
            assert body["response_mode"] == "deferred"
            assert body["expected_thread_version"] == 1
            assert body["provider_id"] == "openai"
            assert body["model_id"] == "qualified-text"
            assert body["max_output_tokens"] == 128
            self.key = body["idempotency_key"]
            return {"accepted": True}
        if path.startswith("/api/ai/chat/turns/"):
            refs = ["provider:openai:receipt"] if self.receipts else []
            response = "A real reply." if self.replay or not getattr(self, "_replayed", False) else "A different reply."
            self._replayed = True
            return {
                "terminal": True, "state": "completed", "response": response,
                "engine_provider_receipts": refs,
                "user_message": {"message_id": "user-1", "idempotency_key": self.key},
                "assistant_message": {"message_id": "answer-1", "content": response,
                                      "causal_user_message_id": "user-1"},
            }
        if path.startswith("/api/v1/conversations/"):
            return {"messages": ([{
                "message_id": "answer-1", "content": "A real reply.",
                "provider_receipt_refs": ["provider:openai:receipt"],
            }] if self.durable else [])}
        raise AssertionError((method, path))


@pytest.mark.parametrize("value", [
    "", "localhost:8001", "http://192.168.1.7:8001", "http://localhost:8001",
    "https://user:password@example.org", "https://example.org/backend",
    "https://example.org/?x=1", "https://example.org/#frag",
])
def test_rejects_untrusted_or_unusable_endpoints(value):
    with pytest.raises(smoke.ProbeFailure):
        smoke.backend_origin(value)


def test_only_explicit_loopback_can_use_plaintext():
    assert smoke.backend_origin("http://127.0.0.1:8001", allow_loopback_http=True) == "http://127.0.0.1:8001"
    assert smoke.backend_origin("https://service.example.org/") == "https://service.example.org"
    with pytest.raises(smoke.ProbeFailure):
        smoke.backend_origin("http://192.168.0.55:8001", allow_loopback_http=True)


def test_token_file_rejects_world_access_and_symlink():
    with TemporaryDirectory() as directory:
        secret = Path(directory) / "token"
        secret.write_text("a" * 80)
        if os.name == "posix":
            secret.chmod(0o644)
            with pytest.raises(smoke.ProbeFailure):
                smoke.private_bearer_token(secret)
        secret.chmod(0o600)
        assert smoke.private_bearer_token(secret) == "a" * 80
        link = Path(directory) / "link"
        link.symlink_to(secret)
        with pytest.raises(smoke.ProbeFailure):
            smoke.private_bearer_token(link)


def test_first_install_probe_requires_real_account():
    class Unauthorized(FakeApi):
        def request(self, method, path, body=None):
            if path == "/api/auth/me":
                return {"authenticated": False}
            return super().request(method, path, body)
    with pytest.raises(smoke.ProbeFailure, match="Sign in"):
        smoke.readiness(Unauthorized())


def test_inactive_model_does_not_create_or_dispatch_a_turn():
    api = FakeApi(ready=False)
    state = smoke.readiness(api)
    assert state["ready"] is False
    with pytest.raises(smoke.ProbeFailure, match="No real chat turn"):
        smoke.exercise(api, state, seconds=10, prompt="Hello")
    assert not any(path == "/api/ai/chat" for _, path, _ in api.calls)


def test_real_turn_requires_model_receipt_and_durable_replay():
    api = FakeApi()
    result = smoke.exercise(api, smoke.readiness(api), seconds=10, prompt="Hello")
    assert result["persisted"] and result["replay_verified"] and result["model_receipts"] == 1
    assert sum(path == "/api/ai/chat" for _, path, _ in api.calls) == 1
    assert sum(path.startswith("/api/ai/chat/turns/") for _, path, _ in api.calls) == 2


@pytest.mark.parametrize("kwargs,expected", [
    ({"receipts": False}, "provider receipts"),
    ({"durable": False}, "not verifiably persisted"),
    ({"replay": False}, "did not survive"),
])
def test_real_turn_fails_closed_without_proof(kwargs, expected):
    api = FakeApi(**kwargs)
    with pytest.raises(smoke.ProbeFailure, match=expected):
        smoke.exercise(api, smoke.readiness(api), seconds=10, prompt="Hello")


def test_recovery_only_reads_existing_turn_and_never_resubmits(capsys):
    api = FakeApi()
    api.key = "installed-ai-smoke-original-receipt"
    result = smoke.observe_and_verify(
        api, "thread-1", api.key, seconds=10,
    )
    assert result["persisted"] is True
    assert result["replay_verified"] is True
    assert result["model_receipts"] == 1
    assert sum(method == "POST" for method, _path, _body in api.calls) == 0
    assert sum(path.startswith("/api/ai/chat/turns/") for _, path, _ in api.calls) == 2
    assert sum(path.startswith("/api/v1/conversations/") for _, path, _ in api.calls) == 1


@pytest.mark.parametrize("identity", ["", "../other", "has spaces", "x" * 161, "t?key=evil"])
def test_recovery_rejects_invalid_saved_identity_before_network(identity):
    api = FakeApi()
    with pytest.raises(smoke.ProbeFailure, match="invalid conversation identity"):
        smoke.observe_and_verify(api, identity, "known-1", seconds=10)
    assert api.calls == []


def test_recovery_cannot_validate_missing_provider_or_fake_transcript():
    for invalid in ({"receipts": False}, {"durable": False}, {"replay": False}):
        api = FakeApi(**invalid)
        api.key = "installed-ai-smoke-recovery"
        with pytest.raises(smoke.ProbeFailure):
            smoke.observe_and_verify(api, "thread-1", api.key, seconds=10)
        assert all(method == "GET" for method, _path, _body in api.calls)


@pytest.mark.parametrize("malformed", [None, {}, "yes", ["ready"] * 17])
def test_incompatible_catalog_does_not_crash_or_claim_ai_readiness(malformed):
    class BadCatalog(FakeApi):
        def request(self, method, path, body=None):
            reply = super().request(method, path, body)
            if path == "/api/ai/chat/readiness":
                reply["models"]["models"] = malformed
            return reply
    with pytest.raises(smoke.ProbeFailure, match="bounded valid model list"):
        smoke.readiness(BadCatalog())


def test_incompatible_model_capacity_is_not_selected():
    class BadCapacity(FakeApi):
        def request(self, method, path, body=None):
            reply = super().request(method, path, body)
            if path == "/api/ai/chat/readiness":
                reply["models"]["models"][0]["max_output_tokens"] = True
            return reply
    assert smoke.readiness(BadCapacity())["ready"] is False


def test_recovery_arguments_are_both_required_before_secret_is_read(monkeypatch):
    calls = []
    monkeypatch.setattr(smoke, "private_bearer_token", lambda _path: calls.append("token") or "x" * 64)
    assert smoke.main([
        "--base-url", "https://api.example.org",
        "--token-file", "/private/unused",
        "--recover-thread", "thread-1",
    ]) == 2
    assert calls == []



def test_interactive_login_refuses_headless_password_echo(monkeypatch):
    class HeadlessInput:
        def isatty(self):
            return False

    monkeypatch.setattr(smoke.sys, "stdin", HeadlessInput())
    monkeypatch.setattr(smoke, "getpass", lambda _: pytest.fail("password prompt must not echo"))
    api = FakeApi()
    with pytest.raises(smoke.ProbeFailure, match="private terminal"):
        smoke.interactive_login(api, "owner@example.org")
    assert api.calls == []


def test_interactive_login_cancellation_is_sanitized(monkeypatch):
    class PrivateTerminal:
        def isatty(self):
            return True

    monkeypatch.setattr(smoke.sys, "stdin", PrivateTerminal())

    def cancelled(_):
        raise KeyboardInterrupt("private-account-password")

    monkeypatch.setattr(smoke, "getpass", cancelled)
    with pytest.raises(smoke.ProbeFailure, match="was cancelled") as result:
        smoke.interactive_login(FakeApi(), "owner@example.org")
    assert "private-account-password" not in str(result.value)
