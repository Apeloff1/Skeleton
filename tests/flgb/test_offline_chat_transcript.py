"""Regression tests for user-explicit, Docker-free local transcript continuity."""
from __future__ import annotations

import asyncio
from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
import os
import tempfile
import unittest
from unittest.mock import patch

from skeleton.app.local_ai import OfflineAISession
from skeleton.app.local_ai_transcript import (
    LocalTranscriptError,
    MAX_TRANSCRIPT_BYTES,
    decode_transcript,
    encode_transcript,
    load_transcript,
    save_transcript,
)
from skeleton.ai.runtime.inference.artifact import write_local_model_artifact
from tests.flgb.test_desktop_offline_ai import backend

MODEL = "a" * 64
TOKENIZER = "b" * 64
HISTORY = (("user", "hello"), ("assistant", "world"))


class TestLocalTranscript(unittest.TestCase):
    def test_export_import_round_trip_and_terminal_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            a = OfflineAISession(backend())
            answer = asyncio.run(a.ask("hello", max_output_tokens=2))
            path = Path(d) / "conversation.json"
            digest = a.export_transcript(path)
            self.assertEqual(len(digest), 64)
            self.assertEqual(path.stat().st_size < MAX_TRANSCRIPT_BYTES, True)
            b = OfflineAISession(backend())
            self.assertEqual(b.import_transcript(path), 1)
            self.assertEqual(a.history, b.history)
            self.assertEqual(b.history[1][1], answer.text)
            self.assertTrue(asyncio.run(b.ask("world", max_output_tokens=2)).text)
            self.assertEqual(len(b.history), 4)

    def test_model_identity_mismatch_rejected_without_state_changes(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "chat.json"
            save_transcript(path, model_digest=MODEL, tokenizer_digest=TOKENIZER, history=HISTORY)
            s = OfflineAISession(backend())
            s.history = (("user", "before"), ("assistant", "still here"))
            with self.assertRaisesRegex(LocalTranscriptError, "different model"):
                s.import_transcript(path)
            self.assertEqual(s.history[0], ("user", "before"))

    def test_digest_mutation_fails_closed(self) -> None:
        raw = encode_transcript(model_digest=MODEL, tokenizer_digest=TOKENIZER, history=HISTORY)
        tampered = raw.replace(b"world", b"other")
        with self.assertRaisesRegex(LocalTranscriptError, "digest mismatch"):
            decode_transcript(tampered, model_digest=MODEL, tokenizer_digest=TOKENIZER)

    def test_json_duplicate_nonfinite_and_unknown_fields_refused(self) -> None:
        raw = encode_transcript(model_digest=MODEL, tokenizer_digest=TOKENIZER, history=HISTORY)
        for corrupted in (
            raw.replace(b'"schema":', b'"schema":"wrong","schema":'),
            raw.replace(b'"digest":', b'"new":NaN,"digest":'),
            raw.replace(b'"digest":', b'"unexpected":123,"digest":'),
        ):
            with self.subTest(corrupted=corrupted[:64]):
                with self.assertRaises(LocalTranscriptError):
                    decode_transcript(corrupted, model_digest=MODEL, tokenizer_digest=TOKENIZER)

    def test_incomplete_oversized_or_wrong_role_history_refused(self) -> None:
        for history in (
            (("user", "orphan"),),
            (("assistant", "out of order"), ("user", "wrong")),
            (("user", "a" * 4097), ("assistant", "answer")),
            (("user", "hello"), ("assistant", "")),
            (("user", "hello"), ("assistant", "world")) * 9,
        ):
            with self.subTest(size=len(history)):
                with self.assertRaises(LocalTranscriptError):
                    encode_transcript(model_digest=MODEL, tokenizer_digest=TOKENIZER, history=history)

    def test_full_file_rejected_before_open_and_symlink_refused(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "huge.json"
            with path.open("wb") as stream:
                stream.seek(MAX_TRANSCRIPT_BYTES)
                stream.write(b"!")
            with patch("os.open", side_effect=AssertionError("must not open oversize")):
                with self.assertRaises(LocalTranscriptError):
                    load_transcript(path, model_digest=MODEL, tokenizer_digest=TOKENIZER)
            good = Path(d) / "good.json"
            save_transcript(good, model_digest=MODEL, tokenizer_digest=TOKENIZER, history=HISTORY)
            link = Path(d) / "linked.json"
            try:
                link.symlink_to(good)
            except OSError:
                self.skipTest("symlinks unavailable")
            with self.assertRaises(LocalTranscriptError):
                load_transcript(link, model_digest=MODEL, tokenizer_digest=TOKENIZER)

    def test_failed_atomic_replace_preserves_existing_transcript(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "chat.json"
            save_transcript(path, model_digest=MODEL, tokenizer_digest=TOKENIZER, history=HISTORY)
            before = path.read_bytes()
            with patch("os.replace", side_effect=OSError("disk failed")):
                with self.assertRaisesRegex(LocalTranscriptError, "cannot save"):
                    save_transcript(path, model_digest=MODEL, tokenizer_digest=TOKENIZER, history=())
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual(sorted(p.name for p in Path(d).iterdir()), ["chat.json"])

    def test_cli_restores_history_and_saves_checkpoint_bound_conversation(self) -> None:
        from skeleton.app.cli import run_app_cli

        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "model.json"
            transcript = Path(d) / "conversation.json"
            write_local_model_artifact(backend(), path)
            output = StringIO()
            with redirect_stdout(output):
                code = run_app_cli([
                    "local-ai", "--model", str(path),
                    "--prompt", "hello", "--max-output-tokens", "2",
                    "--save-chat", str(transcript), "--json",
                ])
            self.assertEqual(code, 0, output.getvalue())
            result = json.loads(output.getvalue())
            self.assertEqual(result["conversation_turns"], 1)
            self.assertEqual(len(result["chat_sha256"]), 64)
            output = StringIO()
            with redirect_stdout(output):
                code = run_app_cli([
                    "local-ai", "--model", str(path),
                    "--prompt", "world", "--max-output-tokens", "2",
                    "--load-chat", str(transcript),
                    "--save-chat", str(transcript), "--json",
                ])
            self.assertEqual(code, 0, output.getvalue())
            result = json.loads(output.getvalue())
            self.assertEqual(result["conversation_turns"], 2)
            self.assertEqual(
                len(load_transcript(
                    transcript, model_digest=result["model_digest"],
                    tokenizer_digest=backend().tokenizer_digest,
                )), 4,
            )

    def test_cannot_replace_checkpoint_or_other_model_chat(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "checkpoint.json"
            path.write_text('{"schema":"native-checkpoint","weights":[]}', encoding="utf-8")
            before = path.read_bytes()
            with self.assertRaises(LocalTranscriptError):
                save_transcript(path, model_digest=MODEL, tokenizer_digest=TOKENIZER, history=HISTORY)
            self.assertEqual(path.read_bytes(), before)
            other_path = Path(d) / "other.json"
            save_transcript(other_path, model_digest="c"*64, tokenizer_digest=TOKENIZER, history=HISTORY)
            before = other_path.read_bytes()
            with self.assertRaisesRegex(LocalTranscriptError, "different model"):
                save_transcript(other_path, model_digest=MODEL, tokenizer_digest=TOKENIZER, history=HISTORY)
            self.assertEqual(other_path.read_bytes(), before)

    def test_malformed_deep_json_is_rejected_without_recursion_escape(self) -> None:
        invalid = (b"[" * 1500) + b"0" + (b"]" * 1500)
        with self.assertRaises(LocalTranscriptError):
            decode_transcript(invalid, model_digest=MODEL, tokenizer_digest=TOKENIZER)

    def test_cli_refuses_unbound_chat_options(self) -> None:
        from skeleton.app.cli import run_app_cli
        for option in ("--load-chat", "--save-chat"):
            output = StringIO()
            with redirect_stdout(output):
                code = run_app_cli(["local-ai", option, "/tmp/no-chat.json"])
            self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
