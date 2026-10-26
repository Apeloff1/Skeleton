"""Regression for real offline shell arguments, bounded grounding and backups."""
from __future__ import annotations

import asyncio
import contextlib
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from skeleton.ai.model_runtime.native_llm_runtime import NativeLLMRuntime
from skeleton.ai.runtime.inference.native_runtime import NativeRuntimeLocalModel
from skeleton.app.local_ai import OfflineAIError, OfflineAISession
from skeleton.app.offline_workspace import DurableOfflineSession
from skeleton.cortex.transformer import TinyTransformer


def _model(seed: int = 13) -> NativeRuntimeLocalModel:
    return NativeRuntimeLocalModel(NativeLLMRuntime(TinyTransformer(
        vocab=("system:", "user:", "assistant:", "hello", "answer"),
        dim=8, ctx=96, seed=seed, n_heads=2, n_layers=2, d_ff=16,
    )))


def test_manual_history_backup_restores_only_matching_model_to_fresh_session():
    with TemporaryDirectory() as folder:
        path = Path(folder) / "context-backup.json"
        session = OfflineAISession(_model())
        session.history = (("user", "hello"), ("assistant", "answer"))
        digest = session.save_history_backup(path)
        assert len(digest) == 64 and path.is_file()
        restored = OfflineAISession(_model())
        assert restored.restore_history_backup(path) == 1
        assert restored.history == session.history
        try:
            restored.restore_history_backup(path)
        except OfflineAIError as exc:
            assert "new conversation" in str(exc)
        else:
            raise AssertionError("existing context must never be overwritten")


def test_manual_backup_does_not_restore_into_different_model():
    from skeleton.app.offline_history import OfflineHistoryError

    with TemporaryDirectory() as folder:
        path = Path(folder) / "history.json"
        original = OfflineAISession(_model(13))
        original.history = (("user", "hello"), ("assistant", "answer"))
        original.save_history_backup(path)
        different = OfflineAISession(_model(17))
        try:
            different.restore_history_backup(path)
        except (OfflineHistoryError, OfflineAIError):
            assert different.history == ()
        else:
            raise AssertionError("foreign model history should be rejected")


def test_workspace_forwards_only_user_prompt_plus_grounding_context():
    class FakeSession:
        model_digest = "a" * 64
        history = ()
        preferred_output_tokens = 18
        received = None

        async def ask(self, prompt, *, max_output_tokens=32, grounding_context=None):
            self.received = (prompt, max_output_tokens, grounding_context)
            self.history = (("user", prompt), ("assistant", "answer"))
            return SimpleNamespace(text="answer")

    with TemporaryDirectory() as folder:
        model = FakeSession()
        wrapper = DurableOfflineSession(model, Path(folder) / "workspace.sqlite3")
        try:
            assert wrapper.max_interactive_tokens == 18
            asyncio.run(wrapper.ask("original question", max_output_tokens=8,
                                    grounding_context="read-only local reference"))
            assert model.received == ("original question", 8, "read-only local reference")
            assert wrapper.history[0] == ("user", "original question")
        finally:
            wrapper.close()


def test_library_cli_never_calls_removed_inference_prompt_parameter():
    from skeleton.app import offline_cli

    class FakeSession:
        def __init__(self):
            self.grounding = []
        async def ask(self, prompt, *, max_output_tokens=32, grounding_context=None):
            self.grounding.append(grounding_context)
            return SimpleNamespace(text="answer", model_digest="a" * 64,
                                   execution_receipt_digest="b" * 64, input_tokens=1,
                                   output_tokens=1)

    with TemporaryDirectory() as folder:
        session = FakeSession()
        output = StringIO()
        with (
            patch.object(offline_cli, "load_native_checkpoint", return_value=object()),
            patch.object(offline_cli, "OfflineAISession", return_value=session),
            patch.object(offline_cli, "OfflineDocumentLibrary") as library,
            patch.object(offline_cli, "render_local_context", return_value="read-only cited content"),
            contextlib.redirect_stdout(output),
        ):
            library.return_value.__enter__.return_value.search.return_value = [
                SimpleNamespace(relative_path="notes.txt", document_sha256="1" * 64)
            ]
            rc = offline_cli.main(["--model", "checkpoint.json", "--prompt", "hello",
                                   "--library", str(Path(folder) / "notes.sqlite3"),
                                   "--use-library", "--json"])
        assert rc == 0
        assert session.grounding == ["read-only cited content"]
        assert '"retrieved_sources"' in output.getvalue()


def test_empty_library_results_keep_grounding_absent():
    from skeleton.app import offline_cli

    class FakeSession:
        value = "unset"
        async def ask(self, prompt, *, max_output_tokens=32, grounding_context=None):
            self.value = grounding_context
            return SimpleNamespace(text="answer", model_digest="a" * 64,
                                   execution_receipt_digest="b" * 64, input_tokens=1,
                                   output_tokens=1)

    session = FakeSession()
    with (
        patch.object(offline_cli, "load_native_checkpoint", return_value=object()),
        patch.object(offline_cli, "OfflineAISession", return_value=session),
        patch.object(offline_cli, "OfflineDocumentLibrary") as library,
        contextlib.redirect_stdout(StringIO()),
    ):
        library.return_value.__enter__.return_value.search.return_value = []
        assert offline_cli.main(["--model", "checkpoint.json", "--prompt", "hello",
                                 "--library", "notes.sqlite3", "--use-library", "--json"]) == 0
    assert session.value is None


def test_app_cli_routes_offline_library_workspace_and_backup_to_original_owner():
    from skeleton.app.cli import run_app_cli
    from skeleton.app import offline_cli

    flags = ("--library", "--use-library", "--workspace", "--backup-in", "--backup-out")
    for flag in flags:
        with patch.object(offline_cli, "main", return_value=0) as delegated:
            rc = run_app_cli(["local-ai", "--model", "local.json", "--prompt", "hello", flag, "path"])
            assert rc == 0
            delegated.assert_called_once()
            assert delegated.call_args.args[0][0:2] == ["--model", "local.json"]
