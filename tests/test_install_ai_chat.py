"""Jeeves-first local installer qualification (external services injected in tests).

No source-only test is allowed to claim that a real GGUF model ran. The actual
local subprocess and guarded product API are separate explicit acceptance
checks on an operator-owned installation.
"""
from __future__ import annotations

from argparse import Namespace
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import install_ai_chat as install


def args(**overrides):
    values = dict(
        deployment=Path("/private/jeeves.json"),
        env_file=Path("/private/.env.jeeves"),
        apply=False, force=False, start=False, live_local=False,
        admin_email=None, admin_password_file=None,
        exercise=False, base_url=None, token_file=None, login_email=None,
        allow_loopback_http=False, timeout=180,
    )
    values.update(overrides)
    return Namespace(**values)


def model(**overrides):
    values = {
        "runtime_kind": "llama.cpp-cli",
        "model_id": "jeeves",
        "model_sha256": "a" * 64,
        "executable_sha256": "b" * 64,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def owned_model(_path):
    return model()


def good_qualifier(*args, **kwargs):
    return {
        "schema_version": "skeleton.local_model.qualification.v1",
        "status": "qualified", "model_id": "jeeves", "provider": "local",
        "network_required": False, "model_sha256": "a" * 64,
        "executable_sha256": "b" * 64, "receipt_digest": "c" * 64,
    }


def test_non_mutating_dryrun_uses_existing_pinned_local_deployment(monkeypatch, capsys):
    events = []
    monkeypatch.setattr(Path, "resolve", lambda self, strict=True: self)
    status = install.build(
        args(),
        deployment_loader=owned_model,
        configurator=lambda argv: events.append(argv) or 0,
        local_qualifier=lambda *_a, **_kw: pytest.fail("no inference on dry-run"),
        runner=lambda *_a, **_kw: pytest.fail("no Docker on dry-run"),
    )
    assert status == 0
    assert "--provider" in events[0] and "local" in events[0]
    assert "--jeeves-primary" in events[0]
    assert "--dry-run" in events[0]
    assert "openai" not in events[0]
    assert '"application_chat_verified":false' in capsys.readouterr().out


@pytest.mark.parametrize("invalid,phrase", [
    ({"start": True}, "--apply"),
    ({"force": True}, "--apply"),
    ({"exercise": True}, "--apply"),
    ({"admin_email": "owner@example.org"}, "--apply"),
    ({"admin_password_file": Path("/private/admin")}, "--apply"),
    ({"apply": True, "exercise": True}, "requires --start"),
    ({"apply": True, "exercise": True, "start": True}, "requires --start"),
    ({"apply": True, "exercise": True, "start": True, "base_url": "https://api.example.org"}, "requires --token-file"),
    ({"apply": True, "base_url": "https://api.example.org"}, "require explicit --exercise"),
    ({"apply": True, "token_file": Path("/private/token")}, "require explicit --exercise"),
    ({"apply": True, "admin_email": "owner@example.org"}, "both email"),
    ({"apply": True, "admin_password_file": Path("/private/admin")}, "both email"),
    ({"timeout": 601}, "10 to 600"),
    ({"env_file": Path("/private/actual_credentials.txt")}, "private .env"),
])
def test_invalid_invocations_fail_before_any_side_effect(invalid, phrase):
    with pytest.raises(install.InstallationBlocked, match=phrase):
        install._validate(args(**invalid))


def test_malicious_http_host_is_never_accepted():
    with pytest.raises(install.ProbeFailure):
        install._validate(args(
            apply=True, start=True, exercise=True, token_file=Path("/private/token"),
            base_url="http://remote.example.org",
        ))


@pytest.mark.parametrize("bad", [
    {"runtime_kind": "openai-responses"},
    {"model_id": "qwen3-0.6b"},
    {"model_id": "gpt-5.5"},
    {"model_id": "Jeeves"},
])
def test_model_id_and_runtime_are_real_and_exact_before_configuring(monkeypatch, bad):
    monkeypatch.setattr(Path, "resolve", lambda self, strict=True: self)
    with pytest.raises(install.InstallationBlocked, match="genuine digest-pinned"):
        install.build(
            args(), deployment_loader=lambda _p: model(**bad),
            configurator=lambda _args: pytest.fail("rejected model before config"),
        )


def test_live_local_invokes_actual_qualifier_contract_without_hosted_sdk(monkeypatch, capsys):
    monkeypatch.setattr(Path, "resolve", lambda self, strict=True: self)
    calls = []
    def live(path, **kwargs):
        calls.append((path, kwargs))
        return good_qualifier()
    assert install.build(
        args(live_local=True), deployment_loader=owned_model,
        configurator=lambda _args: 0, local_qualifier=live,
    ) == 0
    assert len(calls) == 1
    assert calls[0][1]["max_output_tokens"] == 32
    out = capsys.readouterr().out
    assert '"inference_verified":true' in out
    assert '"application_chat_verified":false' in out


@pytest.mark.parametrize("bad", [
    {"provider": "openai"},
    {"model_id": "other"},
    {"network_required": True},
    {"status": "incomplete"},
    {"model_sha256": "f" * 64},
    {"receipt_digest": ""},
])
def test_no_completion_without_actual_local_bound_result(monkeypatch, bad):
    monkeypatch.setattr(Path, "resolve", lambda self, strict=True: self)
    receipt = {**good_qualifier(), **bad}
    with pytest.raises(install.InstallationBlocked, match="no bound"):
        install.build(
            args(live_local=True), deployment_loader=owned_model,
            configurator=lambda _args: 0, local_qualifier=lambda *_a, **_kw: receipt,
        )


def test_local_configuration_failure_has_no_docker_fallback(monkeypatch):
    monkeypatch.setattr(Path, "resolve", lambda self, strict=True: self)
    with pytest.raises(install.InstallationBlocked, match="was rejected"):
        install.build(args(apply=True), deployment_loader=owned_model,
                      configurator=lambda _args: 2,
                      runner=lambda *_a, **_kw: pytest.fail("Docker must not be touched"))


def test_compose_never_passes_provider_keys_or_model_payloads_in_argv(tmp_path):
    env_file = tmp_path / ".env.jeeves"
    env_file.write_text("JEEVES_LOCAL_ONLY=1\nAI_PROVIDER=local\n", encoding="utf-8")
    env_file.chmod(0o600)
    calls = []
    def runner(command, **kwargs):
        calls.append((command, kwargs))
        return SimpleNamespace(returncode=0)
    install._run_compose(env_file, runner=runner)
    assert len(calls) == 2
    assert calls[0][0][-2:] == ["config", "--quiet"]
    assert calls[1][0][-5:] == ["--build", "mongo", "skeleton", "backend", "frontend"]
    assert all("OPENAI_API_KEY" not in " ".join(argv) for argv, _ in calls)
    assert all(kwargs["stdout"] is not None and kwargs["stderr"] is not None for _, kwargs in calls)
    assert all(kwargs["env"]["COMPOSE_REMOVE_ORPHANS"] == "0" for _, kwargs in calls)


def test_compose_rejects_mutation_between_validation_and_start(tmp_path):
    env_file = tmp_path / ".env.jeeves"
    env_file.write_text("AI_PROVIDER=local\n", encoding="utf-8")
    env_file.chmod(0o600)
    calls = []
    def runner(command, **kwargs):
        calls.append(command)
        env_file.write_text("AI_PROVIDER=openai\n", encoding="utf-8")
        return SimpleNamespace(returncode=0)
    with pytest.raises(install.InstallationBlocked, match="changed"):
        install._run_compose(env_file, runner=runner)
    assert len(calls) == 1


def test_canonical_engine_requires_verified_protected_jeeves_host_config(tmp_path):
    from skeleton.ai.jeeves_local_policy import JeevesLocalPolicyError
    env_file = tmp_path / ".env.jeeves"
    env_file.write_text(
        "JEEVES_LOCAL_ONLY=1\nJEEVES_PRIMARY_MODEL_ID=jeeves\n"
        "AI_PROVIDER=local\nAI_LOCAL_DEPLOYMENT_PATH=/app/model.json\n"
        "AI_LOCAL_GUARD_REQUIRED=1\nOPENAI_API_KEY=\n",
        encoding="utf-8",
    )
    env_file.chmod(0o600)
    install._private_configured(env_file)
    env_file.write_text(env_file.read_text().replace("AI_PROVIDER=local", "AI_PROVIDER=openai"))
    with pytest.raises(install.InstallationBlocked, match="AI_PROVIDER=local"):
        install._private_configured(env_file)
    env_file.write_text(env_file.read_text().replace("AI_PROVIDER=openai", "AI_PROVIDER=local").replace("AI_LOCAL_GUARD_REQUIRED=1", "AI_LOCAL_GUARD_REQUIRED=0"))
    with pytest.raises(install.InstallationBlocked, match="protected"):
        install._private_configured(env_file)


def test_source_only_does_not_claim_application_inference_at_docker_start(monkeypatch, capsys):
    monkeypatch.setattr(Path, "resolve", lambda self, strict=True: self)
    monkeypatch.setattr(install, "_private_configured", lambda *_args: None)
    monkeypatch.setattr(install, "_run_compose", lambda *_args, **_kw: None)
    assert install.build(
        args(apply=True, start=True),
        deployment_loader=owned_model, configurator=lambda _args: 0,
        api_factory=lambda *_args: pytest.fail("no product API acceptance without --exercise"),
    ) == 0
    out = capsys.readouterr().out
    assert '"application_chat_verified":false' in out
    assert '"inference_verified":false' in out


class FakeApi:
    def __init__(self, origin, token):
        self.origin = origin
        self.token = token


def test_live_application_verification_honors_real_local_provider_and_durable_proof(monkeypatch, capsys):
    monkeypatch.setattr(Path, "resolve", lambda self, strict=True: self)
    monkeypatch.setattr(install, "_private_configured", lambda *_args: None)
    monkeypatch.setattr(install, "_run_compose", lambda *_args, **_kw: None)
    monkeypatch.setattr(install, "private_bearer_token", lambda _path: "t" * 64)
    events = []
    def ready(api):
        events.append("readiness")
        return {"ready": True, "model_count": 1, "selected": {"provider_id": "local", "model_id": "jeeves"}}
    def complete(api, state, **kwargs):
        events.append("exercise")
        assert state["selected"]["model_id"] == "jeeves"
        return {"thread_id": "thread-1", "persisted": True, "replay_verified": True, "model_receipts": 1}
    monkeypatch.setattr(install, "readiness", ready)
    monkeypatch.setattr(install, "exercise", complete)
    assert install.build(
        args(apply=True, start=True, exercise=True,
             base_url="https://api.example.org", token_file=Path("/private/token")),
        deployment_loader=owned_model, configurator=lambda _args: 0,
        api_factory=FakeApi,
    ) == 0
    assert events == ["readiness", "exercise"]
    out = capsys.readouterr().out
    assert '"application_chat_verified":true' in out
    assert '"provider":"local"' in out


def test_unready_canonical_storage_never_admits_a_model_turn(monkeypatch):
    monkeypatch.setattr(Path, "resolve", lambda self, strict=True: self)
    monkeypatch.setattr(install, "_private_configured", lambda *_args: None)
    monkeypatch.setattr(install, "_run_compose", lambda *_args, **_kw: None)
    monkeypatch.setattr(install, "private_bearer_token", lambda _path: "t" * 64)
    monkeypatch.setattr(install, "readiness", lambda _api: {"ready": False, "model_count": 0})
    monkeypatch.setattr(install, "exercise", lambda *_args, **_kwargs: pytest.fail("no canonical admission"))
    with pytest.raises(install.InstallationBlocked, match="Trusted local model"):
        install.build(
            args(apply=True, start=True, exercise=True,
                 base_url="https://api.example.org", token_file=Path("/private/token")),
            deployment_loader=owned_model, configurator=lambda _args: 0,
            api_factory=FakeApi,
        )
