"""Standalone console contract: real native inference, backup and fail-closed CLI."""
from __future__ import annotations

import json
from pathlib import Path

from skeleton.app.offline_cli import main
from skeleton.ai.model_runtime.native_llm_runtime import NativeLLMRuntime
from skeleton.ai.runtime.inference.artifact import write_local_model_artifact
from skeleton.ai.runtime.inference.native_runtime import NativeRuntimeLocalModel
from skeleton.cortex.transformer import TinyTransformer


def _checkpoint(path: Path) -> Path:
    model = TinyTransformer(
        vocab=("system:", "user:", "assistant:", "hello", "world", "answer"),
        dim=8, ctx=64, seed=41, n_heads=2, n_layers=2, d_ff=16,
    )
    write_local_model_artifact(
        NativeRuntimeLocalModel(NativeLLMRuntime(model)), path,
    )
    return path


def test_console_smoke_does_not_require_model_file_or_provider(capsys) -> None:
    assert main(["--native-smoke"]) == 0
    assert "PASS" in capsys.readouterr().out


def test_console_rejects_ambiguous_or_incomplete_inputs(capsys) -> None:
    assert main([]) == 2
    assert main(["--prompt", "hello"]) == 2
    assert main(["--model", "missing.json"]) == 2
    assert main(["--native-smoke", "--prompt", "hello"]) == 2
    assert "requires" in capsys.readouterr().err


def test_console_native_generation_and_backup_across_processes(
    tmp_path: Path, capsys,
) -> None:
    checkpoint = _checkpoint(tmp_path / "weights.json")
    transcript = tmp_path / "backup.json"
    assert main([
        "--model", str(checkpoint), "--prompt", "hello",
        "--max-output-tokens", "2", "--backup-out", str(transcript), "--json",
    ]) == 0
    first = json.loads(capsys.readouterr().out)
    assert first["text"]
    assert len(first["model_digest"]) == 64
    assert len(first["execution_receipt_digest"]) == 64
    assert transcript.is_file()

    assert main([
        "--model", str(checkpoint), "--prompt", "world",
        "--max-output-tokens", "2",
        "--backup-in", str(transcript), "--backup-out", str(transcript), "--json",
    ]) == 0
    second = json.loads(capsys.readouterr().out)
    assert len(second["execution_receipt_digest"]) == 64
    from skeleton.app.offline_history import restore_history
    history = restore_history(transcript, first["model_digest"])
    assert len(history) == 4
    assert history[0] == ("user", "hello")
    assert history[2] == ("user", "world")


def test_invalid_model_and_corrupt_backup_never_produce_success(
    tmp_path: Path, capsys,
) -> None:
    checkpoint = _checkpoint(tmp_path / "weights.json")
    backup = tmp_path / "backup.json"
    backup.write_text('{"payload":null}', encoding="utf-8")
    assert main([
        "--model", str(checkpoint), "--prompt", "hello",
        "--backup-in", str(backup), "--json",
    ]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "rejected" in captured.err


def test_console_rejects_missing_gguf_artifact(tmp_path: Path, capsys) -> None:
    assert main([
        "--deployment", str(tmp_path / "absent.json"),
        "--prompt", "hello", "--json",
    ]) == 1
    assert capsys.readouterr().out == ""


def test_console_workspace_automatically_recovers_between_runs(
    tmp_path: Path, capsys,
) -> None:
    weights = _checkpoint(tmp_path / "weights.json")
    store = tmp_path / "local-state.db"
    for prompt in ("hello", "world"):
        assert main([
            "--model", str(weights), "--prompt", prompt,
            "--max-output-tokens", "2", "--workspace", str(store),
            "--session-id", "offline-user", "--json",
        ]) == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["text"]
    from skeleton.app.offline_workspace import OfflineWorkspace
    with OfflineWorkspace(store) as journal:
        revision, history = journal.open("offline-user", payload["model_digest"])
        assert revision == 2
        assert len(history) == 4


def test_console_rejects_workspace_and_backup_import_conflict(
    tmp_path: Path, capsys,
) -> None:
    weights = _checkpoint(tmp_path / "weights.json")
    assert main([
        "--model", str(weights), "--prompt", "hello",
        "--workspace", str(tmp_path / "db.sqlite"),
        "--backup-in", str(tmp_path / "chat.json"),
    ]) == 2
    assert "cannot be combined" in capsys.readouterr().err
