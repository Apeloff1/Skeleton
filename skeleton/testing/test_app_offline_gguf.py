"""Offline GGUF desktop and CLI integration, without provider or Docker dependencies."""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
from pathlib import Path
import struct

import pytest

from skeleton.app.cli import run_app_cli
from skeleton.app.local_ai import OfflineAIError, OfflineGGUFSession


_RUNTIME = r'''#!/usr/bin/env python3
import argparse
import os
from pathlib import Path
import sys

for key in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "HTTPS_PROXY", "ALL_PROXY"):
    if os.environ.get(key):
        raise SystemExit("provider environment leaked: " + key)

parser = argparse.ArgumentParser(add_help=False)
parser.add_argument("-f")
parser.add_argument("-m")
parser.add_argument("-n")
args, _ = parser.parse_known_args()
if not args.f or not args.m:
    raise SystemExit("missing local model or prompt file")
text = Path(args.f).read_text(encoding="utf-8")
if "REJECT_REQUEST" in text:
    raise SystemExit(17)
print("offline GGUF desktop answer")
'''


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def local_deployment(tmp_path: Path) -> tuple[Path, Path, Path]:
    if os.name == "nt":
        pytest.skip("executable shebang fixture is POSIX-only")
    executable = tmp_path / "llama-cli"
    executable.write_text(_RUNTIME, encoding="utf-8")
    executable.chmod(0o755)
    weights = tmp_path / "model.gguf"
    weights.write_bytes(struct.pack("<4sIQQ", b"GGUF", 3, 1, 0) + b"fixture-weights")
    manifest = tmp_path / "deployment.json"
    manifest.write_text(json.dumps({
        "schema_version": "skeleton.local_model.deployment.v1",
        "runtime_kind": "llama.cpp-cli",
        "model_id": "offline-demo",
        "executable_path": "llama-cli",
        "executable_sha256": _sha(executable),
        "model_path": "model.gguf",
        "model_sha256": _sha(weights),
        "config": {
            "timeout_seconds": 5.0,
            "max_output_bytes": 16384,
            "max_stderr_bytes": 8192,
            "context_size": 2048,
        },
    }, sort_keys=True), encoding="utf-8")
    return manifest, executable, weights


@pytest.mark.asyncio
async def test_desktop_gguf_two_turns_are_local_and_receipted(
    local_deployment: tuple[Path, Path, Path], monkeypatch
) -> None:
    manifest, _, weights = local_deployment
    monkeypatch.setenv("OPENAI_API_KEY", "never-forward-this")
    monkeypatch.setenv("HTTPS_PROXY", "http://not-a-provider.invalid")
    session = OfflineGGUFSession(manifest)
    first = await session.ask("Hello", max_output_tokens=8)
    second = await session.ask("Follow up", max_output_tokens=8)
    assert first.text == "offline GGUF desktop answer"
    assert second.text == first.text
    assert first.model_digest == _sha(weights)
    assert len(first.execution_receipt_digest) == 64
    assert len(session.history) == 4
    session.clear()
    assert session.history == ()


@pytest.mark.asyncio
async def test_failed_inference_does_not_commit_history(
    local_deployment: tuple[Path, Path, Path]
) -> None:
    session = OfflineGGUFSession(local_deployment[0])
    await session.ask("Initial", max_output_tokens=8)
    before = session.history
    with pytest.raises(Exception):
        await session.ask("REJECT_REQUEST", max_output_tokens=8)
    assert session.history == before


def test_gguf_deployment_rejects_tampered_model(
    local_deployment: tuple[Path, Path, Path]
) -> None:
    manifest, _, weights = local_deployment
    weights.write_bytes(weights.read_bytes() + b"tampered")
    with pytest.raises(RuntimeError, match="digest mismatch"):
        OfflineGGUFSession(manifest)


@pytest.mark.asyncio
async def test_artifacts_rechecked_before_every_inference(
    local_deployment: tuple[Path, Path, Path]
) -> None:
    manifest, executable, _ = local_deployment
    session = OfflineGGUFSession(manifest)
    executable.write_text(_RUNTIME + "\n# mutation\n", encoding="utf-8")
    with pytest.raises(Exception, match="artifact"):
        await session.ask("Hello", max_output_tokens=8)
    assert session.history == ()


def test_request_is_bounded_before_dispatch(
    local_deployment: tuple[Path, Path, Path]
) -> None:
    session = OfflineGGUFSession(local_deployment[0])
    with pytest.raises(OfflineAIError, match="4096"):
        session._request("x" * 4097, 8)
    with pytest.raises(OfflineAIError, match="budget"):
        session._request("valid", 2048)
    with pytest.raises(OfflineAIError, match="budget"):
        session._request("valid", True)
    assert session.history == ()


def test_headless_cli_runs_gguf_and_reports_bound_receipt(
    local_deployment: tuple[Path, Path, Path], capsys
) -> None:
    manifest, _, _ = local_deployment
    assert run_app_cli([
        "local-ai", "--deployment", str(manifest), "--prompt", "Hello",
        "--max-output-tokens", "8", "--json",
    ]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["text"] == "offline GGUF desktop answer"
    assert len(payload["execution_receipt_digest"]) == 64


def test_cli_refuses_ambiguous_or_missing_model_selection(
    local_deployment: tuple[Path, Path, Path], capsys
) -> None:
    manifest, _, _ = local_deployment
    assert run_app_cli(["local-ai", "--model", "native.json",
                        "--deployment", str(manifest), "--prompt", "hi"]) == 2
    assert run_app_cli(["local-ai", "--deployment", str(manifest)]) == 2
    assert run_app_cli(["local-ai", "--prompt", "hi"]) == 2
    assert "exactly one" in capsys.readouterr().out


@pytest.mark.asyncio
async def test_gguf_backup_restores_history_without_reexecution(
    local_deployment: tuple[Path, Path, Path], tmp_path: Path
) -> None:
    manifest, _, _ = local_deployment
    first = OfflineGGUFSession(manifest)
    await first.ask("Turn one", max_output_tokens=8)
    backup = tmp_path / "conversation.json"
    first.save_history_backup(backup)
    recovered = OfflineGGUFSession(manifest)
    assert recovered.restore_history_backup(backup) == 1
    assert recovered.history == first.history
    await recovered.ask("Turn two", max_output_tokens=8)
    assert len(recovered.history) == 4
    assert len(first.history) == 2


def test_headless_gguf_backup_roundtrip(
    local_deployment: tuple[Path, Path, Path], tmp_path: Path, capsys
) -> None:
    manifest, _, _ = local_deployment
    backup = tmp_path / "chat.json"
    assert run_app_cli([
        "local-ai", "--deployment", str(manifest), "--prompt", "Turn one",
        "--backup-out", str(backup),
    ]) == 0
    capsys.readouterr()
    assert backup.exists()
    assert run_app_cli([
        "local-ai", "--deployment", str(manifest), "--prompt", "Turn two",
        "--backup-in", str(backup), "--backup-out", str(backup), "--json",
    ]) == 0
    response = json.loads(capsys.readouterr().out)
    assert response["text"] == "offline GGUF desktop answer"
    from skeleton.app.offline_history import restore_history
    history = restore_history(backup, hashlib.sha256(
        local_deployment[2].read_bytes()
    ).hexdigest())
    assert [role for role, _ in history] == ["user", "assistant", "user", "assistant"]


def test_corrupt_gguf_backup_is_rejected_before_inference(
    local_deployment: tuple[Path, Path, Path], tmp_path: Path, capsys
) -> None:
    backup = tmp_path / "bad.json"
    backup.write_text('{"invalid":true}', encoding="utf-8")
    assert run_app_cli([
        "local-ai", "--deployment", str(local_deployment[0]),
        "--prompt", "Do not run", "--backup-in", str(backup),
    ]) == 1
    assert "request rejected" in capsys.readouterr().out


def test_headless_gguf_uses_local_index_without_persisting_source_in_chat(
    local_deployment: tuple[Path, Path, Path], tmp_path: Path, capsys
) -> None:
    from skeleton.app.offline_library import OfflineDocumentLibrary
    from skeleton.app.offline_workspace import OfflineWorkspace

    library_path = tmp_path / "knowledge.sqlite"
    docs = tmp_path / "local-docs"
    docs.mkdir()
    (docs / "game.md").write_text(
        "Physics engine replay checksum and deterministic game simulation.",
        encoding="utf-8",
    )
    with OfflineDocumentLibrary(library_path) as library:
        library.index_directory(docs)
    history_path = tmp_path / "transcript.sqlite"
    manifest, _, model = local_deployment
    assert run_app_cli([
        "local-ai", "--deployment", str(manifest), "--prompt", "physics engine",
        "--library", str(library_path), "--use-library",
        "--workspace", str(history_path), "--max-output-tokens", "8",
        "--json",
    ]) == 0
    response = json.loads(capsys.readouterr().out)
    assert response["text"] == "offline GGUF desktop answer"
    assert response["retrieved_sources"][0]["relative_path"] == "game.md"
    with OfflineWorkspace(history_path) as workspace:
        revision, messages = workspace.open("default", _sha(model))
        assert revision == 1
        assert messages[0] == ("user", "physics engine")
        assert "Physics engine replay" not in messages[0][1]
        assert messages[1][1] == response["text"]


@pytest.mark.asyncio
async def test_gguf_transient_context_does_not_replace_user_question(
    local_deployment: tuple[Path, Path, Path],
) -> None:
    session = OfflineGGUFSession(local_deployment[0])
    result = await session.ask(
        "actual question", max_output_tokens=8,
        inference_prompt="UNTRUSTED source: facts about game physics. User question: actual question",
    )
    assert result.text == "offline GGUF desktop answer"
    assert session.history[0] == ("user", "actual question")


def test_real_two_turn_gguf_qualification_keeps_runtime_bound(
    local_deployment: tuple[Path, Path, Path], capsys,
) -> None:
    from skeleton.app.offline_cli import main as offline_console

    manifest, executable, weights = local_deployment
    assert offline_console([
        "--deployment", str(manifest),
        "--qualify-model", "--max-output-tokens", "2", "--json",
    ]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["kind"] == "gguf-llama.cpp"
    assert report["model_digest"] == _sha(weights)
    assert report["runtime_digest"] == _sha(executable)
    assert report["session_reopened_between_turns"] is True
    assert report["sqlite_context_restored_and_verified"] is True
    assert report["turns_completed"] == 2
    assert all(len(item["execution_receipt_digest"]) == 64
               for item in report["receipts"])
    assert report["network_isolation_verified"] is False
