"""Operator chat bootstrap stays private, explicit and side-effect bounded."""
from __future__ import annotations

import json
import hashlib
import os
import stat
from pathlib import Path

import pytest
from dotenv import dotenv_values

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
    # An intentional model reconfiguration preserves durable authentication
    # and database identities. Repeating the same request is byte-stable.
    before_values = dotenv_values(path)
    assert config.main(args + ["--force"]) == 0
    assert path.read_bytes() == before
    assert config.main(args + ["--force", "--model", "operator-model-v2"]) == 0
    after_values = dotenv_values(path)
    assert after_values["AI_MODEL"] == "operator-model-v2"
    persistent_keys = (
        "MONGO_INITDB_ROOT_PASSWORD", "MONGO_URL", "SKL_MONGO_URI",
        "JWT_SECRET", "GAMEFORGE_JWT_SECRET", "SKL_ENGINE_SERVICE_TOKEN",
        "SKELETON_MASTER_SECRET", "GF_SEAL_SECRET", "GF_KEYHOLDER_SEED",
    )
    assert all(after_values[key] == before_values[key] for key in persistent_keys)


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


def _pinned_runtime_deployment(root: Path) -> tuple[Path, Path, Path, Path]:
    runtime = root / "runtime"
    runtime.mkdir()
    executable = runtime / "llama-completion"
    header = bytearray(32)
    header[:7] = b"\x7fELF\x02\x01\x01"
    header[18:20] = (62).to_bytes(2, "little")
    executable.write_bytes(header)
    executable.chmod(0o755)
    library = runtime / "libllama.so.0"
    library.write_bytes(b"test-library")
    model = root / "model.gguf"
    model.write_bytes(b"test-model")
    digest = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    manifest = root / "deployment.json"
    manifest.write_text(json.dumps({
        "schema_version": "skeleton.local_model.deployment.v1", "runtime_kind": "llama.cpp-cli",
        "model_id": "test-model", "executable_path": str(executable),
        "executable_sha256": digest(executable), "model_path": str(model), "model_sha256": digest(model),
        "runtime_libraries": {library.name: digest(library)},
    }), encoding="utf-8")
    return manifest, executable, model, library


@pytest.mark.skipif(not hasattr(os, "O_NOFOLLOW"), reason="Pinned runtime requires no-follow file opens")
def test_portable_deployment_preserves_and_validates_pinned_libraries(tmp_path: Path) -> None:
    manifest, _, _, library = _pinned_runtime_deployment(tmp_path)
    options = {"deployment": manifest, "catalog": None, "env_file": tmp_path / ".env.local"}
    config._prepared_local_sources(options, force=False, dry_run=True)
    prepared = json.loads(options["local_manifests"][0][1])
    assert prepared["runtime_libraries"] == {library.name: hashlib.sha256(library.read_bytes()).hexdigest()}
    assert any(binding["source"] == str(library) and binding["read_only"]
               for binding in options["local_bindings"])
    library.write_bytes(b"tampered-library")
    with pytest.raises(config.ConfigurationError, match="differs from its declared digest"):
        config._prepared_local_sources(options, force=False, dry_run=True)


@pytest.mark.skipif(not hasattr(os, "O_NOFOLLOW"), reason="Pinned runtime requires no-follow file opens")
@pytest.mark.parametrize("change", ["missing", "extra", "symlink"])
def test_portable_deployment_rejects_unpinned_or_unsafe_runtime_entries(tmp_path: Path, change: str) -> None:
    manifest, executable, _, library = _pinned_runtime_deployment(tmp_path)
    if change == "missing":
        library.unlink()
    elif change == "extra":
        (executable.parent / "libunlisted.so").write_bytes(b"unlisted")
    else:
        target = tmp_path / "target.so"
        target.write_bytes(library.read_bytes())
        library.unlink()
        library.symlink_to(target)
    options = {"deployment": manifest, "catalog": None, "env_file": tmp_path / ".env.local"}
    with pytest.raises(config.ConfigurationError, match="pinned runtime"):
        config._prepared_local_sources(options, force=False, dry_run=True)


@pytest.mark.parametrize("inventory", [None, {}])
def test_portable_deployment_rejects_declared_empty_library_inventory(tmp_path: Path, inventory) -> None:
    manifest, _, _, _ = _pinned_runtime_deployment(tmp_path)
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["runtime_libraries"] = inventory
    manifest.write_text(json.dumps(payload), encoding="utf-8")
    options = {"deployment": manifest, "catalog": None, "env_file": tmp_path / ".env.local"}
    with pytest.raises(config.ConfigurationError, match="library inventory"):
        config._prepared_local_sources(options, force=False, dry_run=True)


@pytest.mark.skipif(not hasattr(os, "O_NOFOLLOW"), reason="Pinned runtime requires no-follow file opens")
def test_portable_catalog_counts_shared_host_files_at_each_distinct_target(tmp_path: Path) -> None:
    manifest, executable, model, library = _pinned_runtime_deployment(tmp_path)
    second = tmp_path / "deployment-two.json"
    second.write_bytes(manifest.read_bytes())
    digest = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    catalog = tmp_path / "catalog.json"
    payload = {
        "schema_version": "skeleton.local_model.catalog.v1", "primary_model_id": "one",
        "max_total_artifact_bytes": 1000000,
        "models": [{"model_id": name, "kind": "deployment", "path": str(path), "sha256": digest(path)}
                   for name, path in (("one", manifest), ("two", second))],
    }
    catalog.write_text(json.dumps(payload), encoding="utf-8")
    options = {"deployment": None, "catalog": catalog, "env_file": tmp_path / ".env.local"}
    config._prepared_local_sources(options, force=False, dry_run=True)
    expected = 2 * (executable.stat().st_size + model.stat().st_size + library.stat().st_size)
    expected += sum(len(raw) for _, raw in options["local_manifests"] if b'"runtime_kind"' in raw)
    payload["max_total_artifact_bytes"] = expected - 1
    catalog.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(config.ConfigurationError, match="artifact byte budget"):
        config._prepared_local_sources(options, force=False, dry_run=True)
