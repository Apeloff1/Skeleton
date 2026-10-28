"""Operator chat bootstrap stays private, explicit and side-effect bounded."""
from __future__ import annotations

import json
import stat
from pathlib import Path

import pytest

from scripts import configure_ai_chat as config


def test_hosted_chat_setup_writes_private_outputs_without_echoing_key(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    env_file = tmp_path / ".env.chat"
    secret = "sk-private-example-not-a-real-key"
    monkeypatch.setenv("SKELETON_CHAT_TEST_KEY", secret)
    assert config.main([
        "--env-file", str(env_file), "--provider", "openai",
        "--openai-key-env", "SKELETON_CHAT_TEST_KEY",
    ]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["files_written"] is True
    assert result["hosted_credentials_present"] is True
    assert result["provider_access_verified"] is False
    assert result["service_readiness_verified"] is False
    files = [env_file, Path(str(env_file) + ".compose.json"),
             Path(str(env_file) + ".README.md")]
    assert all(path.is_file() and stat.S_IMODE(path.stat().st_mode) == 0o600
               for path in files)
    assert secret in env_file.read_text(encoding="utf-8")
    assert secret not in json.dumps(result)
    assert secret not in files[1].read_text(encoding="utf-8")
    assert secret not in files[2].read_text(encoding="utf-8")
    compose = json.loads(files[1].read_text(encoding="utf-8"))
    assert compose["services"]["backend"]["environment"]["GAMEFORGE_AUTH_ENFORCE"] == "1"


def test_dry_run_never_creates_a_file(tmp_path: Path, monkeypatch, capsys) -> None:
    env_file = tmp_path / ".env.chat"
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert config.main([
        "--env-file", str(env_file), "--provider", "openai", "--dry-run",
    ]) == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["files_written"] is False
    assert summary["hosted_credentials_present"] is False
    assert not env_file.exists()
    assert not Path(str(env_file) + ".compose.json").exists()


def test_existing_configuration_refuses_accidental_overwrite(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    path = tmp_path / ".env.chat"
    monkeypatch.setenv("SKELETON_CHAT_TEST_KEY", "sk-not-real-for-test")
    args = ["--env-file", str(path), "--provider", "openai",
            "--openai-key-env", "SKELETON_CHAT_TEST_KEY"]
    assert config.main(args) == 0
    capsys.readouterr()
    before = path.read_bytes()
    assert config.main(args) == 2
    assert path.read_bytes() == before
    assert config.main(args + ["--force"]) == 0
    assert path.read_bytes() != before


def test_symlink_output_is_rejected_without_touching_target(
    tmp_path: Path, capsys
) -> None:
    protected = tmp_path / "protected"
    protected.write_text("do not change", encoding="utf-8")
    path = tmp_path / ".env.chat"
    path.symlink_to(protected)
    assert config.main([
        "--env-file", str(path), "--provider", "openai", "--force",
    ]) == 2
    assert protected.read_text(encoding="utf-8") == "do not change"


def test_local_artifact_is_read_only_bound_without_claiming_readiness(
    tmp_path: Path, capsys
) -> None:
    model = tmp_path / "weights.json"
    model.write_bytes(b"{\"example\":true}")
    env_file = tmp_path / ".env.chat"
    assert config.main([
        "--env-file", str(env_file), "--provider", "local",
        "--local-artifact", str(model),
    ]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["local_artifact_present"] is True
    assert output["local_artifact_format_verified"] is False
    assert output["service_readiness_verified"] is False
    compose = json.loads(Path(str(env_file) + ".compose.json").read_text(encoding="utf-8"))
    mounts = compose["services"]["skeleton"]["volumes"]
    assert mounts[0]["source"] == str(model)
    assert mounts[0]["read_only"] is True
    assert mounts[0]["bind"]["create_host_path"] is False
    assert model.read_bytes() == b"{\"example\":true}"
