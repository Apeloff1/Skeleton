"""Operator hosted-AI installer contracts, with mocked *external* services.

These tests qualify command ordering and fail-closed release semantics only.
They never represent a real provider response, device install, or model test.
"""
from __future__ import annotations

from argparse import Namespace
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts import install_ai_chat
from skeleton.app.installer import InstallPhase, InstallReceipt


def options(**overrides):
    values = {
        "root": Path("/tmp/skeleton-chat-test-root"),
        "model": "gpt-4.1-mini",
        "key_file": None,
        "prompt_key": False,
        "apply": False,
        "start": False,
        "skip_python": True,
        "admin_email": None,
        "admin_password_file": None,
        "allow_switch_from_local": False,
        "replace_existing_key": False,
        "exercise": False,
        "base_url": None,
        "login_email": None,
        "token_file": None,
        "allow_loopback_http": False,
        "timeout": 180,
    }
    values.update(overrides)
    return Namespace(**values)


def receipt(*, ok=True):
    return InstallReceipt(
        root=Path("/tmp/skeleton-chat-test-root"),
        phases=(InstallPhase("preload", ok, "source only"),),
    )


def fake_setup(events):
    def impl(root, **kwargs):
        events.append(("setup", root, kwargs))
    return impl


def fake_configure(events, *, guard=False):
    def impl(root, **kwargs):
        events.append(("configure", root, kwargs))
        return {
            "provider": "openai",
            "configuration_changed": True,
            "local_guard_bypassed": guard,
        }
    return impl


def fake_installer(events, *, ok=True):
    def impl(root, **kwargs):
        events.append(("install", root, kwargs))
        return receipt(ok=ok)
    return impl


def test_dry_run_never_mutates_or_claims_a_model_responded(capsys):
    def reject(*_args, **_kwargs):
        raise AssertionError("no host mutations or network calls in dry run")
    assert install_ai_chat.configure_and_start(
        options(), setup=reject, configure=reject, installer=reject, client_factory=reject,
    ) == 0
    output = capsys.readouterr().out
    assert '"applied":false' in output
    assert '"inference_verified":false' in output


@pytest.mark.parametrize("changes", [
    {"start": True},
    {"exercise": True},
    {"key_file": Path("/private/key")},
    {"prompt_key": True},
    {"admin_email": "owner@example.org"},
    {"admin_password_file": Path("/private/owner")},
    {"allow_switch_from_local": True},
    {"replace_existing_key": True},
])
def test_dry_run_never_accepts_live_or_secret_action(changes):
    with pytest.raises(install_ai_chat.InstallationBlocked, match="require --apply"):
        install_ai_chat._validate_options(options(**changes))


@pytest.mark.parametrize("changes,phrase", [
    ({"exercise": True}, "needs --start"),
    ({"exercise": True, "start": True}, "needs --base-url"),
    ({"exercise": True, "start": True, "base_url": "https://api.example.org"}, "needs --login-email"),
    ({"base_url": "https://api.example.org"}, "only accompany"),
    ({"login_email": "owner@example.org"}, "only accompany"),
    ({"admin_email": "owner@example.org"}, "requires --admin-password-file"),
    ({"admin_password_file": Path("/private/pass")}, "requires --admin-email"),
    ({"timeout": 601}, "between 10 and 600"),
    ({"model": "YOUR_APPROVED_MODEL"}, "real approved model"),
    ({"exercise": True, "start": True, "base_url": "http://example.org", "login_email": "owner@example.org"}, "HTTPS"),
])
def test_incoherent_or_untrusted_arguments_do_not_start(changes, phrase):
    with pytest.raises((install_ai_chat.InstallationBlocked, install_ai_chat.ActivationError, install_ai_chat.ProbeFailure), match=phrase):
        install_ai_chat._validate_options(options(apply=True, **changes))


def test_real_install_orders_setup_secret_activation_and_canonical_installer(capsys):
    events = []
    assert install_ai_chat.configure_and_start(
        options(apply=True, start=True),
        setup=fake_setup(events),
        configure=fake_configure(events),
        installer=fake_installer(events),
    ) == 0
    assert [stage[0] for stage in events] == ["setup", "configure", "install"]
    assert events[1][2]["model"] == "gpt-4.1-mini"
    assert events[1][2]["allow_switch_from_local"] is False
    assert events[1][2]["replace_existing_key"] is False
    assert events[2][2]["production"] is True
    assert events[2][2]["start"] is True
    assert '"inference_verified":false' in capsys.readouterr().out


def test_do_not_start_if_hosted_activation_does_not_preserve_guard():
    events = []
    with pytest.raises(install_ai_chat.InstallationBlocked, match="guarded runtime contract"):
        install_ai_chat.configure_and_start(
            options(apply=True, start=True),
            setup=fake_setup(events), configure=fake_configure(events, guard=True),
            installer=fake_installer(events),
        )
    assert [stage[0] for stage in events] == ["setup", "configure"]


def test_canonical_installer_failure_cannot_be_called_success():
    events = []
    with pytest.raises(install_ai_chat.InstallationBlocked, match="canonical installer"):
        install_ai_chat.configure_and_start(
            options(apply=True, start=True),
            setup=fake_setup(events), configure=fake_configure(events),
            installer=fake_installer(events, ok=False),
        )


def test_bad_key_cannot_mutate_private_setup():
    events = []
    with patch.object(install_ai_chat, "_hosted_key", side_effect=install_ai_chat.ActivationError("test key invalid")):
        with pytest.raises(install_ai_chat.ActivationError):
            install_ai_chat.configure_and_start(
                options(apply=True, start=True),
                setup=fake_setup(events), configure=fake_configure(events),
                installer=fake_installer(events),
            )
    assert not events


class FakeApi:
    def __init__(self, origin, token):
        self.origin = origin
        self.token = token


def _run_live_mock(capsys, *, ready, proof=None):
    events = []
    state = {
        "ready": ready,
        "checks": {
            name: {"ready": ready, "code": "ready" if ready else "engine_unavailable"}
            for name in ("conversation_storage", "engine", "models")
        },
        "model_count": 1 if ready else 0,
    }
    calls = []
    def real_readiness(api):
        calls.append("readiness")
        return state
    def real_exercise(api, verdict, **kwargs):
        calls.append("exercise")
        return proof
    with patch.object(install_ai_chat, "private_bearer_token", return_value="x" * 64), patch.object(
        install_ai_chat, "readiness", side_effect=real_readiness,
    ), patch.object(install_ai_chat, "exercise", side_effect=real_exercise):
        args = options(
            apply=True, start=True, exercise=True,
            base_url="https://api.example.org",
            token_file=Path("/private/auth-token"),
        )
        try:
            code = install_ai_chat.configure_and_start(
                args,
                setup=fake_setup(events), configure=fake_configure(events),
                installer=fake_installer(events), client_factory=FakeApi,
            )
        except install_ai_chat.InstallationBlocked:
            code = 2
    return code, calls, capsys.readouterr().out


def test_unready_model_is_never_sent_a_synthetic_or_duplicate_turn(capsys):
    code, calls, output = _run_live_mock(capsys, ready=False)
    assert code == 2
    assert calls == ["readiness"]
    assert '"inference_verified":true' not in output


def test_missing_provider_and_persistence_proofs_block_acceptance(capsys):
    code, calls, output = _run_live_mock(capsys, ready=True, proof={
        "persisted": True, "replay_verified": False,
        "model_receipts": 1, "thread_id": "t-1", "answer_characters": 12,
    })
    assert code == 2 and calls == ["readiness", "exercise"]
    assert '"inference_verified":true' not in output


def test_injected_acceptance_contract_reports_proof_only_after_authority(capsys):
    code, calls, output = _run_live_mock(capsys, ready=True, proof={
        "persisted": True, "replay_verified": True,
        "model_receipts": 1, "thread_id": "t-1", "answer_characters": 12,
    })
    assert code == 0 and calls == ["readiness", "exercise"]
    assert '"inference_verified":true' in output
    assert '"provider_receipts":1' in output
    assert '"model_receipts"' not in output
