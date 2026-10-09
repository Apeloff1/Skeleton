"""Real sandboxed-process contract for the public offline GGUF CLI path.

The tiny GGUF header and fake CLI verify wiring/containment only. They are NOT
trained weights and cannot qualify the output quality of a real llama model.
"""
from __future__ import annotations

import asyncio
from contextlib import redirect_stdout
from io import StringIO
import hashlib
import json
import os
from pathlib import Path
from queue import Queue
from types import SimpleNamespace
import struct
import tempfile
import unittest
from unittest.mock import patch

from skeleton.app.cli import run_app_cli
from skeleton.app.local_ai_gguf import (
    OfflineGGUFError, OfflineGGUFSession, generate_local_gguf_sync,
)
from skeleton.app.windows_launcher import main as exe_main


FAKE_CLI = """#!/usr/bin/env python3
import argparse
import os
from pathlib import Path
import sys

for key in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "XAI_API_KEY", "HTTP_PROXY", "HTTPS_PROXY"):
    if os.environ.get(key):
        raise SystemExit("credential or proxy leaked to local model process")
args = argparse.ArgumentParser(add_help=False)
args.add_argument("-m")
args.add_argument("-f")
args.add_argument("-n")
options, unknown = args.parse_known_args()
prompt = Path(options.f).read_text(encoding="utf-8")
if "SECRET_PROMPT_MARKER" not in prompt:
    raise SystemExit("missing secret input")
if any("SECRET_PROMPT_MARKER" in part for part in sys.argv):
    raise SystemExit("secret input leaked to process arguments")
if any("https://" in part for part in sys.argv):
    raise SystemExit("unexpected remote URL argument")
print("offline subprocess answer from selected GGUF")
"""


class TestPublicGGUFCLI(unittest.TestCase):
    def _fixtures(self, root: Path) -> tuple[Path, Path]:
        llama = root / "llama-cli"
        llama.write_text(FAKE_CLI, encoding="utf-8")
        llama.chmod(0o755)
        gguf = root / "operator.gguf"
        gguf.write_bytes(
            struct.pack("<4sIQQ", b"GGUF", 3, 1, 0)
            + b"operator-owned-local-open-weight-fixture"
        )
        return llama, gguf

    @unittest.skipIf(os.name == "nt", "POSIX shebang subprocess fixture")
    def test_canonical_gguf_process_wiring_without_network_or_secrets(self):
        with tempfile.TemporaryDirectory() as directory:
            llama, model = self._fixtures(Path(directory))
            output = StringIO()
            with patch.dict(
                os.environ, {
                    "OPENAI_API_KEY": "must-not-leak",
                    "ANTHROPIC_API_KEY": "must-not-leak",
                    "HTTPS_PROXY": "https://forbidden.invalid",
                },
            ), redirect_stdout(output):
                code = run_app_cli([
                    "local-ai", "--llama-executable", str(llama),
                    "--gguf-model", str(model),
                    "--prompt", "SECRET_PROMPT_MARKER please answer",
                    "--max-output-tokens", "8", "--json",
                ])
            self.assertEqual(code, 0, output.getvalue())
            report = json.loads(output.getvalue())
            self.assertEqual(
                report["text"], "offline subprocess answer from selected GGUF",
            )
            self.assertEqual(
                report["model_digest"], hashlib.sha256(model.read_bytes()).hexdigest(),
            )
            self.assertEqual(
                report["runtime_digest"], hashlib.sha256(llama.read_bytes()).hexdigest(),
            )
            self.assertEqual(report["backend"], "llama.cpp")
            self.assertTrue(report["token_counts_are_estimates"])
            self.assertFalse(report["hosted_provider_used"])
            self.assertFalse(report["model_downloaded"])
            self.assertFalse(report["model_quality_certified"])
            self.assertIsNone(report["execution_receipt_digest"])
            self.assertEqual(len(report["request_sha256"]), 64)

    @unittest.skipIf(os.name == "nt", "POSIX shebang subprocess fixture")
    def test_frozen_executable_exposes_same_gguf_command_boundary(self):
        with tempfile.TemporaryDirectory() as directory:
            llama, model = self._fixtures(Path(directory))
            out = StringIO()
            with redirect_stdout(out):
                code = exe_main([
                    "--offline-command", "local-ai",
                    "--gguf-model", str(model),
                    "--llama-executable", str(llama),
                    "--prompt", "SECRET_PROMPT_MARKER", "--json",
                ])
            self.assertEqual(code, 0, out.getvalue())
            self.assertEqual(json.loads(out.getvalue())["backend"], "llama.cpp")

    @unittest.skipIf(os.name == "nt", "POSIX shebang subprocess fixture")
    def test_operator_gguf_desktop_multiturn_session_is_ephemeral(self):
        with tempfile.TemporaryDirectory() as directory:
            llama, weights = self._fixtures(Path(directory))
            session = OfflineGGUFSession(llama, weights)
            first = asyncio.run(session.ask("SECRET_PROMPT_MARKER first", max_output_tokens=5))
            second = asyncio.run(session.ask("SECRET_PROMPT_MARKER second", max_output_tokens=5))
            self.assertEqual(len(session.history), 4)
            self.assertEqual(session.model_digest, hashlib.sha256(weights.read_bytes()).hexdigest())
            self.assertEqual(first.model_digest, second.model_digest)
            self.assertIsNone(first.execution_receipt_digest)
            self.assertEqual(session.ui_output_budget, 32)
            self.assertFalse(hasattr(session, "export_transcript"))
            self.assertFalse(hasattr(session, "import_transcript"))
            session.clear()
            self.assertEqual(session.history, ())

    def test_gguf_desktop_requires_existing_local_artifacts(self):
        with tempfile.TemporaryDirectory() as directory:
            _, weights = self._fixtures(Path(directory))
            with self.assertRaises((OSError, ValueError, RuntimeError)):
                OfflineGGUFSession(Path(directory) / "missing", weights)

    def test_gguf_desktop_disables_native_only_actions(self):
        from skeleton.app.local_ai import OfflineAIWindow

        class Button:
            def __init__(self):
                self.state = ""

            def configure(self, **options):
                self.state = options["state"]

        with tempfile.TemporaryDirectory() as directory:
            llama, model = self._fixtures(Path(directory))
            window = OfflineAIWindow.__new__(OfflineAIWindow)
            window.session = OfflineGGUFSession(llama, model)
            window.active = False
            for name in (
                "load_button", "gguf_button", "train_button",
                "improve_button", "benchmark_button", "send_button",
                "clear_button", "cancel_button", "open_history_button",
                "save_history_button",
            ):
                setattr(window, name, Button())
            window._refresh()
            for name in (
                "improve_button", "benchmark_button",
                "open_history_button", "save_history_button",
            ):
                with self.subTest(button=name):
                    self.assertEqual(getattr(window, name).state, "disabled")
            self.assertEqual(window.send_button.state, "normal")
            self.assertEqual(window.clear_button.state, "normal")
            self.assertEqual(window.gguf_button.state, "normal")

    def test_desktop_never_displays_or_persists_rejected_generation(self):
        from skeleton.app.local_ai import OfflineAIWindow

        class Composer:
            text = ""

            def get(self, *_):
                return self.text

            def insert(self, _at, text):
                self.text = text

        class Status:
            text = ""

            def set(self, value):
                self.text = value

        window = OfflineAIWindow.__new__(OfflineAIWindow)
        window.closed = False
        window.active = True
        window.events = Queue()
        window.composer = Composer()
        window.status = Status()
        window.window = SimpleNamespace(after=lambda *_: None)
        rendered = []
        window._append = lambda role, text: rendered.append((role, text))
        window._refresh = lambda: None

        window.events.put(("generation_error", ("private user prompt", "cancelled")))
        window._drain()
        self.assertEqual(rendered, [])
        self.assertEqual(window.composer.text, "private user prompt")
        self.assertIn("cancelled", window.status.text)

        window.composer.text = ""
        answer = SimpleNamespace(
            text="accepted local answer", input_tokens=3, output_tokens=4,
            execution_receipt_digest=None,
        )
        window.events.put(("answer", ("verified user prompt", answer)))
        window._drain()
        self.assertEqual(rendered, [
            ("You", "verified user prompt"),
            ("Skeleton · Local", "accepted local answer"),
        ])
        self.assertIn("no execution receipt", window.status.text)

    def test_explicit_model_runtime_and_prompt_are_all_required(self):
        missing = (
            ["--gguf-model", "x.gguf", "--prompt", "hello"],
            ["--llama-executable", "llama-cli", "--prompt", "hello"],
            ["--llama-executable", "llama-cli", "--gguf-model", "x.gguf"],
            ["--llama-executable", "llama-cli", "--gguf-model", "x.gguf",
             "--prompt", "hello", "--model", "native.json"],
            ["--llama-executable", "llama-cli", "--gguf-model", "x.gguf",
             "--prompt", "hello", "--load-chat", "transcript.json"],
            ["--llama-executable", "llama-cli", "--gguf-model", "x.gguf",
             "--prompt", "hello", "--train-corpus", "data.txt"],
        )
        for arguments in missing:
            with self.subTest(args=arguments), redirect_stdout(StringIO()):
                self.assertEqual(run_app_cli(["local-ai", *arguments]), 2)

    def test_installed_command_missing_gguf_artifacts_refuses_without_launch(self):
        """Missing artifacts are a runtime admission failure (1), not a CLI parse failure (2)."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            missing_model = root / "missing.gguf"
            missing_runtime = root / "missing-llama-cli.exe"
            args = [
                "local-ai", "--gguf-model", str(missing_model),
                "--llama-executable", str(missing_runtime),
                "--prompt", "offline", "--json",
            ]
            for runner in (
                lambda: run_app_cli(args),
                lambda: exe_main(["--offline-command", *args]),
            ):
                with self.subTest(runner=runner):
                    result = StringIO()
                    with patch("subprocess.Popen", side_effect=AssertionError(
                        "missing artifacts must never reach process launch"
                    )), redirect_stdout(result):
                        code = runner()
                    self.assertEqual(code, 1, result.getvalue())
                    self.assertIn("local GGUF request rejected:", result.getvalue())
                    self.assertNotIn("hosted", result.getvalue().lower())
            self.assertFalse(missing_model.exists())
            self.assertFalse(missing_runtime.exists())

    def test_invalid_gguf_token_budgets_fail_before_launch(self):
        for budget in (True, 0, -1, 2049):
            with self.subTest(budget=budget), self.assertRaises(OfflineGGUFError):
                generate_local_gguf_sync(
                    "/not/executed", "/not/read.gguf", "hello",
                    max_output_tokens=budget,
                )

    def test_symlink_model_rejected_and_output_budgets_enforced(self):
        with tempfile.TemporaryDirectory() as directory:
            llama, model = self._fixtures(Path(directory))
            alias = Path(directory) / "alias.gguf"
            try:
                alias.symlink_to(model)
            except OSError:
                self.skipTest("symlink unsupported")
            output = StringIO()
            with redirect_stdout(output):
                code = run_app_cli([
                    "local-ai", "--gguf-model", str(alias),
                    "--llama-executable", str(llama),
                    "--prompt", "SECRET_PROMPT_MARKER",
                ])
            self.assertEqual(code, 1)
            self.assertIn("rejected", output.getvalue())


if __name__ == "__main__":
    unittest.main()
