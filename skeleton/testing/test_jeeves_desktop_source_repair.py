"""Exact SQLite-authoritative bounded source generation and parser repair.

These are post-implementation, source-only tests. Native turn responses are
synthetic and never prove real GGUF inference or model licensing. Real
filesystem source review still uses production descriptor rules with ONLY
the test fixture's temporary-root opener replaced.
"""
from __future__ import annotations

from contextlib import contextmanager
from hashlib import sha256
import json
import os
from pathlib import Path
import tempfile
import threading
from unittest import mock
import unittest

from skeleton.ai.runtime.operational_ai.laptop_runtime import (
    desktop_source_repair as repair,
    desktop_patch_bundle as patch,
    desktop_workspace as workspace,
    desktop_existing_edits as edits,
)

MODEL = "a"*64
SESSION = "s_owner1"


def source(text, path="feature.py"):
    return json.dumps({
        "schema": workspace.SCHEMA,
        "files": [{"path": path, "content": text}],
    }, ensure_ascii=False, sort_keys=True)


class NativeAnswerWorker:
    def __init__(self, answers, *, replay=False, forged=False, on_request=None):
        self.connected = True
        self.session_id = SESSION
        self.model_sha256 = MODEL
        self.answers = list(answers)
        self.replay = replay
        self.forged = forged
        self.on_request = on_request
        self.calls = []
        self._gate = threading.RLock()
        self._owner = False

    @contextmanager
    def exclusive_batch(self, manifest_sha256):
        if (
            type(manifest_sha256) is not str
            or len(manifest_sha256) != 64
            or not self._gate.acquire(blocking=False)
        ):
            raise RuntimeError("untrusted native batch lease")
        self._owner = True
        try:
            yield
        finally:
            self._owner = False
            self._gate.release()

    def request(self, op, **fields):
        if op != "turn" or not self._owner:
            raise AssertionError("model call escaped original SQLite lease")
        if fields.get("context") is not False:
            raise AssertionError("unreviewed SQLite history became repair context")
        if fields.get("action") is not None:
            raise AssertionError("repair cannot invoke privileged durable actions")
        if not self.answers:
            raise AssertionError("unbounded new model generation")
        answer = self.answers.pop(0)
        self.calls.append((op, dict(fields)))
        if self.on_request is not None:
            self.on_request(len(self.calls), fields)
        return {
            "status": "committed-native-chat-turn",
            "request_id": fields["request_id"],
            "turn": {
                "session_id": self.session_id,
                "request_id": fields["request_id"],
                "model_sha256": self.model_sha256,
                "answer": answer,
                "output_sha256": sha256(answer.encode("utf-8")).hexdigest(),
                "authoritative_commit": True,
                "replayed": self.replay,
                "device_qualified": False,
                "release_certified": False,
            },
        }


class SourceRepairAdmissionTests(unittest.TestCase):

    def test_stdlib_toml_parser_accepts_reviewed_source_and_rejects_malformed_input(self):
        # This is a Python 3.11+ runtime contract: TOML parsing must not
        # require the unlisted, third-party tomli distribution.
        import tomllib

        from skeleton.ai.runtime.operational_ai.laptop_runtime import (
            desktop_source_qualification as qualification,
        )

        self.assertIs(qualification.tomllib, tomllib)

        def reviewed(text):
            return patch.PatchEntry(
                kind="new",
                path="config/settings.toml",
                original_text="",
                replacement_text=text,
                original_sha256=None,
                replacement_sha256=sha256(text.encode("utf-8")).hexdigest(),
            )

        valid = qualification.qualify_source_file(
            reviewed('[tool.jeeves]\\nenabled = true\\n')
        )
        self.assertEqual(valid.language, "toml")
        self.assertEqual(valid.status, "parse-clean")
        self.assertFalse(valid.issues)
        self.assertIsNotNone(valid.parser_fingerprint)
        self.assertEqual(valid.bytes_checked, len('[tool.jeeves]\\nenabled = true\\n'))

        malformed = qualification.qualify_source_file(
            reviewed('[tool.jeeves]\\nenabled = true\\nenabled = false\\n')
        )
        self.assertEqual(malformed.language, "toml")
        self.assertEqual(malformed.status, "syntax-held")
        self.assertEqual(len(malformed.issues), 1)
        self.assertEqual(malformed.issues[0].code, "toml-syntax")
        self.assertIsNone(malformed.parser_fingerprint)
        self.assertFalse(malformed.to_public()["parser_fingerprint"])

    def test_operator_selected_goal_and_finite_attempts_required(self):
        valid = repair.SourceRepairRequest(
            root="/private/project", goal="Make a useful source feature",
            format="new-files", maximum_attempts=3,
        )
        self.assertEqual(len(valid.goal_sha256), 64)
        self.assertEqual(valid.maximum_attempts, 3)
        self.assertEqual(valid.format, "new-files")
        self.assertNotIn("Make a useful", valid.goal_sha256)
        for change in (
            {"root": "relative"},
            {"root": "/private/../other"},
            {"goal": ""},
            {"goal": "x"*4097},
            {"goal": True},
            {"format": "shell"},
            {"format": "auto-Git-commit"},
            {"maximum_attempts": True},
            {"maximum_attempts": 0},
            {"maximum_attempts": 4},
        ):
            with self.subTest(change=change), self.assertRaises(
                (repair.NativeSourceRepairHold, ValueError),
            ):
                repair.SourceRepairRequest(**{
                    "root": "/private/project",
                    "goal": "Build locally",
                    "format": "new-files",
                    "maximum_attempts": 2,
                    **change,
                })

    def test_original_session_and_explicit_boolean_consent_required(self):
        selected = repair.SourceRepairRequest(
            root="/private/project", goal="Implement a new feature",
            format="new-files", maximum_attempts=2,
        )
        worker = NativeAnswerWorker([])
        for approved in (False, 1, None):
            with self.subTest(approved=approved), self.assertRaises(
                repair.NativeSourceRepairHold,
            ):
                repair.NativeSourceRepairRunner(
                    worker, selected, approved=approved,
                )
        worker.session_id = None
        with self.assertRaises(repair.NativeSourceRepairHold):
            repair.NativeSourceRepairRunner(worker, selected, approved=True)

    def test_no_second_provider_or_privileged_tool_grants(self):
        selected = repair.SourceRepairRequest(
            root="/private/project", goal="Write original Python",
            format="new-files", maximum_attempts=1,
        )
        worker = NativeAnswerWorker([])
        runner = repair.NativeSourceRepairRunner(
            worker, selected, approved=True,
        )
        # The repair engine must have only a bound preexisting native worker.
        self.assertIs(runner.worker, worker)
        self.assertFalse(hasattr(runner, "provider_registry"))
        self.assertFalse(hasattr(runner, "subprocess"))
        self.assertFalse(hasattr(runner, "source_writer"))
        self.assertEqual(runner.expected_model, MODEL)
        self.assertEqual(runner.expected_session, SESSION)


@unittest.skipUnless(
    os.name == "posix" and hasattr(os, "O_NOFOLLOW"),
    "Original source review requires POSIX/WSL2 descriptor guard",
)
class NativeSourceRepairExecutionTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="jeeves-source-repair-")
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name) / "project"
        self.root.mkdir(mode=0o700)
        (self.root/"src").mkdir(mode=0o700)

        def open_test_root(path):
            return os.open(
                path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
            )
        for module in (workspace, edits, patch):
            patched = mock.patch.object(
                module, "_open_root", side_effect=open_test_root,
            )
            patched.start()
            self.addCleanup(patched.stop)

    def _runner(self, answers, *, max_attempts=3, format="new-files",
                progress=None, **worker_options):
        request = repair.SourceRepairRequest(
            root=str(self.root), goal="Build a real offline project module",
            format=format, maximum_attempts=max_attempts,
        )
        worker = NativeAnswerWorker(answers, **worker_options)
        runner = repair.NativeSourceRepairRunner(
            worker, request, approved=True, progress=progress,
        )
        return worker, runner

    def test_invalid_python_is_repaired_with_new_unique_sqlite_request_id(self):
        bad = source("def broken(:\n    pass\n", path="src/feature.py")
        fixed = source("def build():\n    return 'original code'\n",
                       path="src/feature.py")
        progress = []
        worker, runner = self._runner(
            [bad, fixed], progress=lambda r: progress.append(r),
        )
        with (
            mock.patch("subprocess.run") as commands,
            mock.patch("subprocess.Popen") as subprocesses,
        ):
            outcome = runner.execute()
        self.assertEqual(outcome.status, "review-required")
        self.assertEqual(len(outcome.attempts), 2)
        self.assertEqual(len(progress), 2)
        self.assertEqual(
            [r.source_result for r in outcome.attempts],
            ["source-parse-held", "review-required"],
        )
        self.assertEqual(len(worker.calls), 2)
        original_ids = [c[1]["request_id"] for c in worker.calls]
        self.assertEqual(len(set(original_ids)), 2)
        self.assertTrue(all(i.startswith("r_") and len(i) == 34 for i in original_ids))
        self.assertTrue(all(c[1]["context"] is False for c in worker.calls))
        self.assertIn("python-syntax", worker.calls[1][1]["prompt"])
        self.assertIn("ORIGINAL OPERATOR GOAL", worker.calls[1][1]["prompt"])
        self.assertIn("previous", worker.calls[1][1]["prompt"].lower())
        self.assertIs(outcome.candidate.__class__, patch.PortablePatchPlan)
        self.assertTrue(outcome.qualification.permits_inert_export)
        self.assertEqual(outcome.proposal, fixed)
        self.assertFalse(outcome.public_receipt()["project_files_modified"])
        self.assertFalse(outcome.public_receipt()["git_commands_executed"])
        self.assertEqual(outcome.public_receipt()["tools_granted_to_model"], 0)
        self.assertFalse((self.root/"src/feature.py").exists())
        self.assertFalse((self.root/".git").exists())
        commands.assert_not_called()
        subprocesses.assert_not_called()

    def test_schema_error_then_valid_json_source_recovered_without_extra_model(self):
        good = source('{"mode":"local","enabled":true}', path="settings.json")
        worker, runner = self._runner(
            ['{"schema":"wrong","files":[]}', good], max_attempts=2,
        )
        result = runner.execute()
        self.assertEqual(result.status, "review-required")
        self.assertEqual(len(worker.calls), 2)
        self.assertEqual(result.attempts[0].issue_codes,
                         ("proposal-schema-or-source-custody",))
        self.assertEqual(result.attempts[1].source_result, "review-required")
        self.assertEqual(result.candidate.entries[0].path, "settings.json")
        self.assertFalse((self.root/"settings.json").exists())

    def test_all_bad_proposals_stop_at_operator_maximum_without_new_work(self):
        worker, runner = self._runner(
            ["not JSON", "not JSON", "not JSON"],
            max_attempts=3,
        )
        outcome = runner.execute()
        self.assertEqual(outcome.status, "held-exhausted")
        self.assertEqual(len(outcome.attempts), 3)
        self.assertEqual(len(worker.calls), 3)
        self.assertIsNone(outcome.candidate)
        self.assertIsNone(outcome.proposal)
        self.assertIsNone(outcome.qualification)
        self.assertIsNone(outcome.public_receipt()["source_patch_sha256"])

    def test_operator_stop_does_not_cancel_or_repeat_inflight_native_turn(self):
        pending = []
        worker, runner = self._runner(
            ["wrong", source("x=1\n")],
            progress=lambda attempt: pending.append(attempt),
        )
        runner.progress = lambda attempt: (
            pending.append(attempt), runner.stop_after_current(),
        )
        outcome = runner.execute()
        self.assertEqual(outcome.status, "operator-stopped")
        self.assertEqual(len(outcome.attempts), 1)
        self.assertEqual(len(worker.calls), 1)
        self.assertEqual(len(pending), 1)

    def test_overlarge_native_answer_is_held_without_reusing_request(self):
        worker, runner = self._runner(
            ["x"*(repair.MAX_COMMITTED_PROPOSAL_BYTES+1)],
        )
        result = runner.execute()
        self.assertEqual(result.status, "held-exhausted")
        self.assertEqual(len(worker.calls), 1)
        self.assertEqual(result.attempts[0].source_result, "oversize-held")
        self.assertIsNone(result.proposal)

    def test_same_runner_cannot_replay_its_committed_native_ids(self):
        worker, runner = self._runner([source("x=2\n")], max_attempts=1)
        self.assertEqual(runner.execute().status, "review-required")
        with self.assertRaises(repair.NativeSourceRepairHold):
            runner.execute()
        self.assertEqual(len(worker.calls), 1)

    def test_native_replayed_existing_result_never_counts_as_new_generation(self):
        worker, runner = self._runner(
            [source("x=1\n")], replay=True,
        )
        with self.assertRaises(repair.NativeSourceRepairHold):
            runner.execute()
        self.assertEqual(len(worker.calls), 1)

    def test_native_session_drift_and_foreign_model_source_are_terminal(self):
        def swap(index, fields):
            if index == 1:
                worker.model_sha256 = "f"*64
        worker, runner = self._runner(
            [source("x=1\n")], on_request=swap,
        )
        with self.assertRaises(repair.NativeSourceRepairHold):
            runner.execute()
        self.assertEqual(len(worker.calls), 1)
        self.assertFalse((self.root/"feature.py").exists())

    def test_source_format_cannot_infer_existing_file_original_hash(self):
        original = self.root/"src/feature.py"
        original.write_text("x=1\n", encoding="utf-8")
        provided = json.dumps({
            "schema": edits.SCHEMA,
            "files": [{
                "path": "src/feature.py",
                "expected_sha256": "f"*64,
                "replacement": "x=2\n",
            }],
        })
        worker, runner = self._runner(
            [provided], max_attempts=1, format="existing-edits",
        )
        result = runner.execute()
        self.assertEqual(result.status, "held-exhausted")
        self.assertEqual(result.attempts[0].source_result, "needs-repair")
        self.assertEqual(original.read_text(), "x=1\n")

    def test_committed_turn_with_tampered_sha_must_not_authorize_source(self):
        worker, runner = self._runner([source("x=1\n")])
        def forged(op, **fields):
            data = NativeAnswerWorker.request(worker, op, **fields)
            data["turn"]["output_sha256"] = "f"*64
            return data
        worker.request = forged
        with self.assertRaises(repair.NativeSourceRepairHold):
            runner.execute()
        self.assertEqual(len(worker.calls), 1)
        self.assertFalse((self.root/"feature.py").exists())

    def test_original_task_not_published_in_public_source_receipt(self):
        worker, runner = self._runner(
            [source("secret='DO_NOT_PRINT_THIS'\n")],
            max_attempts=1,
        )
        result = runner.execute()
        self.assertEqual(result.status, "review-required")
        public = result.public_receipt()
        self.assertNotIn("DO_NOT_PRINT_THIS", repr(public))
        self.assertNotIn(str(self.root), repr(public))
        self.assertFalse(public["automatic_uncertain_native_retry"])
        self.assertTrue(public["operator_patch_approval_required"])
        self.assertFalse(public["release_certified"])


if __name__ == "__main__":
    unittest.main()
