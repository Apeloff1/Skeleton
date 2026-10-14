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


def test_two_turn_qualification_executes_local_model_and_restores_context(
    tmp_path: Path, capsys,
) -> None:
    checkpoint = _checkpoint(tmp_path / "native.json")
    assert main([
        "--model", str(checkpoint), "--qualify-model",
        "--max-output-tokens", "2", "--json",
    ]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["schema_version"] == "skeleton.app.offline_functional_qualification.v1"
    assert report["artifacts_verified_before_and_after"] is True
    assert report["two_real_generation_calls_completed"] is True
    assert report["session_reopened_between_turns"] is True
    assert report["sqlite_context_restored_and_verified"] is True
    assert report["turns_completed"] == 2
    assert len(report["receipts"]) == 2
    assert all(len(item["execution_receipt_digest"]) == 64 for item in report["receipts"])
    assert report["network_isolation_verified"] is False
    assert report["trained_model_quality_verified"] is False
    assert report["release_signed"] is False


def test_model_qualification_rejects_fake_approval_and_conflicting_modes(
    tmp_path: Path, capsys,
) -> None:
    fake = tmp_path / "missing.json"
    assert main(["--model", str(fake), "--qualify-model", "--json"]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "rejected" in captured.err
    assert main(["--qualify-model", "--json"]) == 2
    assert main([
        "--model", str(fake), "--qualify-model", "--prompt", "conflict",
    ]) == 2
    assert main([
        "--model", str(fake), "--qualify-model", "--doctor",
    ]) == 2
    assert main([
        "--model", str(fake), "--qualify-model",
        "--max-output-tokens", "999",
    ]) == 1


def test_unified_app_cli_exposes_same_real_local_model_qualification(
    tmp_path: Path, capsys,
) -> None:
    from skeleton.app.cli import run_app_cli
    checkpoint = _checkpoint(tmp_path / "weights.json")
    assert run_app_cli([
        "local-ai", "--model", str(checkpoint), "--qualify-model",
        "--max-output-tokens", "2", "--json",
    ]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["turns_completed"] == 2
    assert len(report["model_digest"]) == 64


def test_qualification_never_reports_success_if_second_inference_fails(
    tmp_path: Path, monkeypatch, capsys,
) -> None:
    from skeleton.app import offline_qualification

    model = _checkpoint(tmp_path / "checkpoint.json")
    original = offline_qualification.OfflineAISession.ask
    attempts = {"count": 0}

    async def fail_on_second(self, prompt, *, max_output_tokens=32, inference_prompt=None):
        attempts["count"] += 1
        if attempts["count"] == 2:
            raise RuntimeError("injected second-turn model crash")
        return await original(
            self, prompt,
            max_output_tokens=max_output_tokens,
            inference_prompt=inference_prompt,
        )

    monkeypatch.setattr(
        offline_qualification.OfflineAISession, "ask", fail_on_second,
    )
    assert main([
        "--model", str(model), "--qualify-model",
        "--max-output-tokens", "2", "--json",
    ]) == 1
    captured = capsys.readouterr()
    assert attempts["count"] == 2
    assert captured.out == ""
    assert "second-turn model crash" in captured.err


def test_qualification_does_not_ignore_state_management_flags(
    tmp_path: Path, capsys,
) -> None:
    checkpoint = _checkpoint(tmp_path / "checkpoint.json")
    assert main([
        "--model", str(checkpoint), "--qualify-model",
        "--audit-workspace", str(tmp_path / "missing.sqlite"),
    ]) == 2
    assert main([
        "--model", str(checkpoint), "--qualify-model",
        "--snapshot-to", str(tmp_path / "snapshot"),
    ]) == 2
    assert main([
        "--model", str(checkpoint), "--qualify-model",
        "--queue-db", str(tmp_path / "queue.sqlite"), "--run-queue",
    ]) == 2
    assert capsys.readouterr().out == ""
