"""Local-only authenticated Jeeves Docker chat and durable replay source tests.

These are injectable transport tests only. Production acceptance requires a
REAL owner-authenticated backend, native licensed GGUF, exact running images
and durable Mongo. No network, Docker daemon, model, user transcript or actual
bearer token is accessed by this source test suite.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
import stat

import pytest

from scripts import local_ai_chat_acceptance as chat
from scripts import local_ai_offline_compose as binding
from scripts import local_ai_offline_launch as launch
from scripts import local_ai_docker as host

_ARCHIVE = Path("/unused/archive")
_OVERLAY = Path("/unused/binding")
_TOKEN_FILE = Path("/unused/token-file")
_SHA = "a" * 64
_NONCE = "abcd" * 8
_MARKER = "SKL_OFFLINE_" + _NONCE


def _ready():
    return {
        "schema_version": "backend.ai.chat-readiness.v1",
        "available": True,
        "checks": {
            name: {"available": True, "code": "ready"}
            for name in ("conversation_storage", "engine", "models")
        },
    }


def _providers():
    return {
        "engine": "skeleton-engine", "active": "local",
        "llm_available": True, "availability_observed": True,
        "providers": [{
            "id": "local", "model": "jeeves", "available": True,
            "ownership": "engine-process",
        }],
    }


def _identity():
    return {
        "ok": True, "enforced": True, "authenticated": True,
        "user": {"email": "operator@example.invalid",
                 "tenant_id": "default", "role": "viewer"},
    }


def _response():
    return {
        "success": True,
        "ai_generated": True,
        "provider": "skeleton-engine",
        "engine_runtime_provider": "local",
        "replayed": False,
        "response": _MARKER,
        "engine_provider_receipts": ["provider:local:exact-head-gguf"],
        "engine_execution_id": "execution-001",
        "engine_operation_id": "operation-001",
        "operation_id": "operation-001",
        "turn_state": "complete",
        "assistant_message": {
            "message_id": "assistant-message", "content": _MARKER,
            "causal_user_message_id": "user-message",
        },
        "user_message": {"message_id": "user-message"},
    }


def _replay():
    return {
        "success": True,
        "accepted": True,
        "terminal": True,
        "state": "completed",
        "provider": "replayed",
        "replayed": True,
        "ai_generated": True,
        "engine_runtime_provider": "local",
        "engine_execution_id": "execution-001",
        "operation_id": "operation-001",
        "engine_provider_receipts": ["provider:local:exact-head-gguf"],
        "response": _MARKER,
    }


def _mock(monkeypatch, *, status=None, provider=None, identity=None, original=None,
          replay=None, model=True, change_runtime=False):
    calls = []
    counters = {"model": 0, "attest": 0}
    report = {
        "source_receipt_file_sha256": _SHA,
        "containers_observed": 4,
        "containers": [
            {"role": name, "image_id": "sha256:" + str(n) * 64}
            for n, name in enumerate(("mongo", "skeleton", "backend", "frontend"), 1)
        ],
    }

    def attested(mode, archive, overlay, *, expected_receipt_sha256, root):
        counters["attest"] += 1
        assert (mode, archive, overlay, expected_receipt_sha256) == (
            "cpu", _ARCHIVE, _OVERLAY, _SHA,
        )
        new = copy.deepcopy(report)
        if change_runtime and counters["attest"] >= 6:
            new["containers"][0]["image_id"] = "sha256:" + "f" * 64
        return new

    def native(mode, archive, overlay, *, expected_receipt_sha256, root):
        counters["model"] += 1
        if not model:
            raise host.LocalDockerError("GGUF unavailable")
        return {"model_turn_executed": True,
                "model_sha256": "b" * 64, "executable_sha256": "c" * 64}

    def request(base, token, method, path, *, payload=None):
        assert base == "http://127.0.0.1:8001"
        assert token == "token-" + "X" * 64
        calls.append((method, path, copy.deepcopy(payload)))
        if path == "/api/auth/me":
            assert method == "GET"
            return copy.deepcopy(_identity() if identity is None else identity)
        if path == "/api/ai/chat/readiness":
            return copy.deepcopy(_ready() if status is None else status)
        if path == "/api/ai/providers":
            return copy.deepcopy(_providers() if provider is None else provider)
        if path == "/api/ai/chat":
            assert method == "POST" and payload is not None
            assert payload["message"].endswith(_MARKER)
            assert payload["provider_id"] == "local"
            assert payload["model_id"] == "jeeves"
            assert payload["response_mode"] == "wait"
            assert payload["max_output_tokens"] <= 128
            assert payload["thread_id"] == "thread-001"
            assert payload["expected_thread_version"] == 2
            return copy.deepcopy(_response() if original is None else original)
        if path.startswith("/api/ai/chat/turns/"):
            assert method == "GET" and "idempotency_key=" in path
            return copy.deepcopy(_replay() if replay is None else replay)
        raise AssertionError("unexpected request path")

    monkeypatch.setattr(chat.launch, "attest_running_offline", attested)
    monkeypatch.setattr(chat.binding, "qualify_offline_model", native)
    monkeypatch.setattr(chat, "_http", request)
    monkeypatch.setattr(chat, "_token", lambda path: "token-" + "X" * 64)
    monkeypatch.setattr(chat, "_endpoint",
                        lambda mode, root: "http://127.0.0.1:8001")
    monkeypatch.setattr(chat.secrets, "token_hex", lambda length: _NONCE)
    return calls, counters


def _observe():
    return chat.observe_local_chat(
        "cpu", _ARCHIVE, _OVERLAY, _TOKEN_FILE,
        expected_receipt_sha256=_SHA,
    )


def _qualify(allow=True, *, thread="thread-001", version=2):
    return chat.qualify_local_chat(
        "cpu", _ARCHIVE, _OVERLAY, _TOKEN_FILE,
        expected_receipt_sha256=_SHA,
        thread_id=thread, expected_thread_version=version,
        allow_durable_chat_turn=allow,
    )


def test_readiness_is_read_only_even_with_local_provider(tmp_path, monkeypatch):
    calls, counters = _mock(monkeypatch)
    result = _observe()
    assert result["exclusive_local_backend_provider_observed"] is True
    assert result["enforced_authenticated_owner_observed"] is True
    assert result["native_model_turn_executed"] is False
    assert result["durable_chat_turn_written"] is False
    assert result["protected_chat_qualified"] is False
    assert result["independent_reviewer_attested"] is False
    assert result["release_qualified"] is False
    assert counters["model"] == 0
    assert not any(method == "POST" for method, _, _ in calls)


def test_real_chat_submits_one_turn_and_verifies_durable_replay(
    tmp_path, monkeypatch,
):
    calls, counters = _mock(monkeypatch)
    result = _qualify()
    assert result["status"] == (
        "real_local_chat_and_durable_replay_observed_not_full_guard_authority"
    )
    assert result["authenticated_backend_local_chat_executed"] is True
    assert result["enforced_authenticated_owner_observed"] is True
    assert result["durable_canonical_replay_verified"] is True
    assert result["native_model_one_shot_executed"] is True
    assert result["engine_execution_id_sha256"] != "execution-001"
    assert result["answer_sha256"] != _MARKER
    assert result["credentials_exposed"] is False
    assert result["prompt_or_response_text_in_receipt"] is False
    assert result["independent_reviewer_attested"] is False
    assert result["majority_durable_writer_epoch_attested"] is False
    assert result["protected_chat_qualified"] is False
    assert result["release_qualified"] is False
    assert counters["model"] == 1
    assert len([c for c in calls if c[0] == "POST"]) == 1
    assert len([c for c in calls if "/chat/turns/" in c[1]]) == 1
    assert "token-" not in json.dumps(result)
    assert _MARKER not in json.dumps(result)
    assert "thread-001" not in json.dumps(result)


def test_mutation_must_be_explicit_before_any_backend_access(monkeypatch):
    calls, counters = _mock(monkeypatch)
    with pytest.raises(chat.LocalChatProbeError, match="approval"):
        _qualify(False)
    assert not calls and not counters["attest"] and not counters["model"]


@pytest.mark.parametrize("thread,version", [
    ("", 2), ("bad/thread", 2), ("../evil", 2),
    ("thread-001", 0), ("thread-001", True), ("thread-001", None),
    ("thread-001", 2**40), ("thread-001", "2"),
])
def test_invalid_owned_thread_identity_denied_before_network(
    monkeypatch, thread, version,
):
    calls, counters = _mock(monkeypatch)
    with pytest.raises(chat.LocalChatProbeError, match="thread/version"):
        _qualify(thread=thread, version=version)
    assert calls == [] and counters["attest"] == 0



@pytest.mark.parametrize("mutate", [
    lambda d: d.update({"enforced": False}),
    lambda d: d.update({"authenticated": False}),
    lambda d: d.update({"ok": False}),
    lambda d: d["user"].update({"dev_mode": True}),
    lambda d: d["user"].update({"role": "anonymous"}),
    lambda d: d["user"].update({"email": ""}),
    lambda d: d["user"].update({"disabled": True}),
    lambda d: d.update({"user": None}),
])
def test_real_user_and_enforced_auth_required_before_model_or_durable_write(
    monkeypatch, mutate,
):
    identity = _identity()
    mutate(identity)
    calls, counters = _mock(monkeypatch, identity=identity)
    with pytest.raises(chat.LocalChatProbeError, match="authenticated owner"):
        _qualify()
    assert counters["model"] == 0
    assert not any(method == "POST" for method, _, _ in calls)
    assert calls[0][1] == "/api/auth/me"
    assert not any(path == "/api/ai/providers" for _, path, _ in calls)


def test_readonly_authentication_probe_is_first_and_only_observes(monkeypatch):
    calls, counters = _mock(monkeypatch)
    report = _observe()
    assert calls[0][:2] == ("GET", "/api/auth/me")
    assert report["enforced_authenticated_owner_observed"] is True
    assert not any(method == "POST" for method, _, _ in calls)
    assert counters["model"] == 0


@pytest.mark.parametrize("change", [
    lambda x: x.update({"available": False}),
    lambda x: x.update({"schema_version": "foreign"}),
    lambda x: x["checks"]["conversation_storage"].update({"available": False}),
    lambda x: x["checks"]["models"].update({"available": False}),
    lambda x: x["checks"]["engine"].update({"available": False}),
])
def test_auth_storage_model_or_engine_readiness_missing_denied(monkeypatch, change):
    row = _ready()
    change(row)
    calls, counters = _mock(monkeypatch, status=row)
    with pytest.raises(chat.LocalChatProbeError, match="readiness"):
        _observe()
    assert counters["model"] == 0
    assert all(c[0] != "POST" for c in calls)


@pytest.mark.parametrize("change", [
    lambda x: x.update({"active": "hosted"}),
    lambda x: x.update({"llm_available": False}),
    lambda x: x.update({"availability_observed": False}),
    lambda x: x["providers"][0].update({"model": "wrong-model"}),
    lambda x: x["providers"][0].update({"available": False}),
    lambda x: x["providers"].append({"id": "openai", "available": True}),
])
def test_nonexclusive_or_hosted_provider_denied_before_chat(monkeypatch, change):
    row = _providers()
    change(row)
    calls, counters = _mock(monkeypatch, provider=row)
    with pytest.raises(chat.LocalChatProbeError):
        _qualify()
    assert counters["model"] == 0
    assert all(c[0] != "POST" for c in calls)


@pytest.mark.parametrize("change", [
    lambda x: x.update({"success": False}),
    lambda x: x.update({"ai_generated": False}),
    lambda x: x.update({"provider": "openai"}),
    lambda x: x.update({"engine_runtime_provider": "remote"}),
    lambda x: x.update({"replayed": True}),
    lambda x: x.update({"response": "model did not obey"}),
    lambda x: x.update({"engine_execution_id": None}),
    lambda x: x.update({"turn_state": "failed"}),
    lambda x: x["assistant_message"].update({"causal_user_message_id": "other-user"}),
    lambda x: x.update({"engine_provider_receipts": []}),
    lambda x: x.update({"engine_provider_receipts": ["provider:hosted:other"]}),
    lambda x: x["assistant_message"].update({"content": "changed"}),
])
def test_durable_original_turn_must_have_exact_local_custody(
    monkeypatch, change,
):
    row = _response()
    change(row)
    calls, counters = _mock(monkeypatch, original=row)
    with pytest.raises(chat.LocalChatProbeError):
        _qualify()
    assert counters["model"] == 1
    assert len([c for c in calls if c[0] == "POST"]) == 1
    assert all("/chat/turns/" not in c[1] for c in calls)


@pytest.mark.parametrize("change", [
    lambda x: x.update({"success": False}),
    lambda x: x.update({"terminal": False}),
    lambda x: x.update({"state": "in_progress"}),
    lambda x: x.update({"provider": "skeleton-engine"}),
    lambda x: x.update({"engine_execution_id": "different"}),
    lambda x: x.update({"operation_id": "different"}),
    lambda x: x.update({"response": "different"}),
    lambda x: x.update({"engine_runtime_provider": "openai"}),
    lambda x: x.update({"engine_provider_receipts": ["provider:local:changed"]}),
])
def test_durable_replay_must_match_committed_original(monkeypatch, change):
    row = _replay()
    change(row)
    calls, _ = _mock(monkeypatch, replay=row)
    with pytest.raises(chat.LocalChatProbeError):
        _qualify()
    assert len([c for c in calls if c[0] == "POST"]) == 1
    assert len([c for c in calls if "/chat/turns/" in c[1]]) == 1


def test_model_preflight_failure_does_not_start_backend_chat(monkeypatch):
    calls, counters = _mock(monkeypatch, model=False)
    with pytest.raises(host.LocalDockerError):
        _qualify()
    assert counters["model"] == 1
    assert all(method == "GET" for method, _, _ in calls)


def test_runtime_image_changes_after_chat_denies_qualification(monkeypatch):
    calls, counters = _mock(monkeypatch, change_runtime=True)
    with pytest.raises(chat.LocalChatProbeError, match="runtime changed"):
        _qualify()
    assert len([c for c in calls if c[0] == "POST"]) == 1


def test_readonly_token_file_requires_owner_and_no_symlink(tmp_path):
    secret = tmp_path / "owned-token"
    secret.write_text("a" * 60)
    secret.chmod(0o600)
    assert chat._token(secret) == "a" * 60
    secret.chmod(0o644)
    with pytest.raises(chat.LocalChatProbeError):
        chat._token(secret)
    secret.chmod(0o600)
    link = tmp_path / "link"
    link.symlink_to(secret)
    with pytest.raises(chat.LocalChatProbeError):
        chat._token(link)


def test_loopback_backend_url_from_admitted_compose_only(tmp_path, monkeypatch):
    monkeypatch.setattr(host, "compose_command", lambda mode, root: [
        "docker", "compose", "-f", "canonical.yml",
    ])
    monkeypatch.setattr(host, "_validate_config",
                        lambda mode, config: {"image": "offline"})
    topology = {"services": {"backend": {"ports": [{
        "target": 8001, "published": "8001", "host_ip": "127.0.0.1",
        "protocol": "tcp",
    }]}}}
    monkeypatch.setattr(host, "_run",
                        lambda args, *, root, capture: json.dumps(topology))
    assert chat._endpoint("cpu", tmp_path) == "http://127.0.0.1:8001"
    topology["services"]["backend"]["ports"][0]["host_ip"] = "0.0.0.0"
    with pytest.raises(chat.LocalChatProbeError, match="loopback"):
        chat._endpoint("cpu", tmp_path)


def test_http_refuses_foreign_backend_and_untrusted_paths():
    for base in ("http://localhost:8001", "https://127.0.0.1:8001",
                 "http://198.51.100.10:8001", "http://127.0.0.1:8001@remote"):
        with pytest.raises(chat.LocalChatProbeError):
            chat._http(base, "a" * 32, "GET", "/api/ai/providers")
    for path in ("https://provider.example", "/api/config", "\r\n/api/ai/chat"):
        with pytest.raises(chat.LocalChatProbeError):
            chat._http("http://127.0.0.1:8001", "a" * 32, "GET", path)


def test_live_http_uses_no_redirect_or_proxy_classes():
    from urllib.request import HTTPRedirectHandler, ProxyHandler
    assert issubclass(chat._NoRedirect, HTTPRedirectHandler)
    import inspect
    code = inspect.getsource(chat._http)
    assert "ProxyHandler({})" in code
    assert "timeout=" in code
    assert "MAX_HTTP_BYTES + 1" in code
    assert "Authorization" in code


def test_no_repeated_post_on_backend_failure(monkeypatch):
    calls, counters = _mock(monkeypatch)
    original = chat._http

    def reject_submit(base, token, method, path, *, payload=None):
        if method == "POST":
            calls.append((method, path, payload))
            raise chat.LocalChatProbeError("backend unavailable")
        return original(base, token, method, path, payload=payload)

    monkeypatch.setattr(chat, "_http", reject_submit)
    with pytest.raises(chat.LocalChatProbeError):
        _qualify()
    assert len([c for c in calls if c[0] == "POST"]) == 1
