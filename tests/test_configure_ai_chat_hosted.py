"""Secret-safe hosted model activation and protected local configuration regression."""

from __future__ import annotations

import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from scripts.configure_ai_chat_hosted import (
    ActivationError, activate_hosted_ai, checked_key,
    checked_model, main, private_provider_key,
)

EXAMPLE_KEY = "sk-" + "A" * 48
NEW_KEY = "sk-" + "B" * 48


def setup_root(root, text="AI_PROVIDER=local\nMONGO_INITDB_ROOT_PASSWORD=private-other-secret\n"):
    path = root / ".env"
    path.write_text(text)
    if os.name == "posix":
        path.chmod(0o600)
    return path


@pytest.mark.parametrize("model", ["", "../escape", "hello world", "model\nAI_PROVIDER=local", "a" * 129, "YOUR_APPROVED_MODEL", "YOUR_MODEL", "MODEL_ID", "EXAMPLE"])
def test_model_selection_is_bounded_and_noninjectable(model):
    with pytest.raises(ActivationError):
        checked_model(model)


@pytest.mark.parametrize("key", ["", "plain-token", "sk-short", "sk-" + "a" * 30 + "\nMONGO_URL=bad", "sk-" + "a" * 600])
def test_secrets_are_validated_before_file_write(key):
    with pytest.raises(ActivationError):
        checked_key(key)


def test_refuses_missing_setup_env():
    with TemporaryDirectory() as d:
        with pytest.raises(ActivationError, match="Run the canonical"):
            activate_hosted_ai(Path(d), model="gpt-4.1-mini", key=EXAMPLE_KEY)


def test_configures_only_provider_fields_and_is_idempotent():
    with TemporaryDirectory() as d:
        path = setup_root(Path(d))
        result = activate_hosted_ai(Path(d), model="gpt-4.1-mini", key=EXAMPLE_KEY)
        assert result["ok"] and result["configuration_changed"]
        assert result["real_inference_verified"] is False
        assert result["local_guard_bypassed"] is False
        assert EXAMPLE_KEY not in json.dumps(result)
        text = path.read_text()
        assert "MONGO_INITDB_ROOT_PASSWORD=private-other-secret" in text
        assert "AI_PROVIDER=openai" in text
        assert "AI_MODEL=gpt-4.1-mini" in text
        assert "OPENAI_API_KEY=" + EXAMPLE_KEY in text
        unchanged = activate_hosted_ai(Path(d), model="gpt-4.1-mini")
        assert unchanged["configuration_changed"] is False
        if os.name == "posix":
            assert path.stat().st_mode & 0o077 == 0


def test_never_silently_overrides_a_configured_local_model():
    with TemporaryDirectory() as d:
        path = setup_root(Path(d), "AI_PROVIDER=local\nAI_LOCAL_DEPLOYMENT_PATH=/app/local-ai/verified.json\n")
        original = path.read_bytes()
        with pytest.raises(ActivationError, match="--allow-switch-from-local"):
            activate_hosted_ai(Path(d), model="gpt-4.1-mini", key=EXAMPLE_KEY)
        assert path.read_bytes() == original
        result = activate_hosted_ai(Path(d), model="gpt-4.1-mini", key=EXAMPLE_KEY, allow_switch_from_local=True)
        assert result["ok"]
        assert "AI_LOCAL_DEPLOYMENT_PATH=/app/local-ai/verified.json" in path.read_text()


def test_hosted_mode_cannot_silently_disable_required_local_guard():
    with TemporaryDirectory() as d:
        path = setup_root(Path(d), "AI_PROVIDER=local\nAI_LOCAL_GUARD_REQUIRED=1\n")
        before = path.read_bytes()
        with pytest.raises(ActivationError, match="will not disable or silently bypass"):
            activate_hosted_ai(Path(d), model="gpt-4.1-mini", key=EXAMPLE_KEY)
        assert path.read_bytes() == before


def test_existing_hosted_key_is_preserved_without_explicit_rotation():
    with TemporaryDirectory() as d:
        path = setup_root(Path(d), "AI_PROVIDER=openai\nOPENAI_API_KEY=" + EXAMPLE_KEY + "\n")
        original = path.read_bytes()
        with pytest.raises(ActivationError, match="--replace-existing-key"):
            activate_hosted_ai(Path(d), model="gpt-4.1-mini", key=NEW_KEY)
        assert path.read_bytes() == original
        activate_hosted_ai(Path(d), model="gpt-4.1-mini", key=NEW_KEY, replace_existing_key=True)
        assert NEW_KEY in path.read_text()
        assert EXAMPLE_KEY not in path.read_text()


def test_rejects_symlinked_env_and_secret_input():
    with TemporaryDirectory() as d:
        root = Path(d)
        original = root / "original"
        original.write_text("AI_PROVIDER=local\n")
        (root / ".env").symlink_to(original)
        with pytest.raises(ActivationError, match="safely read"):
            activate_hosted_ai(root, model="gpt-4.1-mini", key=EXAMPLE_KEY)
        assert original.read_text() == "AI_PROVIDER=local\n"
        secret = root / "key"
        secret.write_text(EXAMPLE_KEY)
        if os.name == "posix":
            secret.chmod(0o600)
        (root / "key-link").symlink_to(secret)
        with pytest.raises(ActivationError, match="symlink"):
            private_provider_key(root / "key-link")


def test_key_file_permission_fence():
    with TemporaryDirectory() as d:
        path = Path(d) / "key"
        path.write_text(EXAMPLE_KEY)
        if os.name == "posix":
            path.chmod(0o644)
            with pytest.raises(ActivationError, match="private"):
                private_provider_key(path)
        path.chmod(0o600)
        assert private_provider_key(path) == EXAMPLE_KEY


def test_cli_defaults_to_no_configuration_write(capsys):
    assert main(["--model", "gpt-4.1-mini"]) == 0
    content = capsys.readouterr().out
    assert '"applied": false' in content
    assert EXAMPLE_KEY not in content



def test_headless_provider_prompt_never_falls_back_to_echo(monkeypatch):
    from scripts import configure_ai_chat_hosted as config

    class HeadlessInput:
        def isatty(self):
            return False

    monkeypatch.setattr(config.sys, "stdin", HeadlessInput())
    monkeypatch.setattr(config, "getpass", lambda _: pytest.fail("a key must never be requested from headless stdin"))
    with pytest.raises(ActivationError, match="requires a terminal"):
        config.prompted_provider_key()


def test_interactive_provider_prompt_cancellation_is_safe(monkeypatch):
    from scripts import configure_ai_chat_hosted as config

    class PrivateTerminal:
        def isatty(self):
            return True

    monkeypatch.setattr(config.sys, "stdin", PrivateTerminal())

    def cancelled(_):
        raise EOFError("sensitive-transport-path")

    monkeypatch.setattr(config, "getpass", cancelled)
    with pytest.raises(ActivationError, match="was cancelled") as result:
        config.prompted_provider_key()
    assert "sensitive-transport-path" not in str(result.value)
