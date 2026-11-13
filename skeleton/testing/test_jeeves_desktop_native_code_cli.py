"""Real-bridge-contract tests for the headless offline Jeeves code CLI.

All fake native receipts are SOURCE-ONLY witnesses, not model, installed
license, physical device or release proof. The production command actually
uses DesktopBridge + DesktopHost + the installed local GGUF/SQLite; these
tests replace only that final native-child factory with deterministic
responses, and use temporary descriptor-rooted original files.
"""
from __future__ import annotations

from contextlib import contextmanager
from hashlib import sha256
from io import BytesIO, StringIO
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest import mock

from skeleton.ai.runtime.operational_ai.laptop_runtime import (
    desktop_native_code_cli as native_cli,
    desktop_project_context as context,
    desktop_workspace as workspace,
    desktop_existing_edits as edits,
    desktop_patch_bundle as bundle,
    desktop_project_work as mixed,
)

MODEL = "a" * 64
SESSION = "s_headless_native_01"


def request(
    *, project_root="/private/project", action="inspect",
    goal="Generate useful local Python source",
    format="mixed-work", attempts=2, source_paths=None,
    source_sha=None, job_sha=None, model_root="/private/model",
    state_dir="/private/native_state", threads=4, gpu_layers=0,
):
    return {
        "schema": native_cli.SCHEMA,
        "action": action,
        "project_root": str(project_root),
        "model_root": model_root,
        "state_dir": state_dir,
        "tenant": "local",
        "subject": "operator",
        "goal": goal,
        "format": format,
        "maximum_attempts": attempts,
        "source_paths": list(source_paths or []),
        "source_context_sha256": source_sha,
        "job_sha256": job_sha,
        "context_tokens": 4096,
        "max_output_tokens": 1024,
        "threads": threads,
        "gpu_layers": gpu_layers,
        "inference_ms": 90000,
        "capacity_budget_bytes": 8000000000,
    }


def package(old_digest: str) -> str:
    return json.dumps({
        "schema": mixed.SCHEMA,
        "new_files": [
            {"path": "src/new.py", "content": "def helper():\n    return 42\n"},
        ],
        "existing_edits": [
            {
                "path": "src/core.py",
                "expected_sha256": old_digest,
                "replacement": "def core():\n    return 42\n",
            },
        ],
    }, ensure_ascii=False, sort_keys=True)


class FakeNativeBridge:
    """Contract-matching source-only fake for one exact model/SQLite child."""

    def __init__(self, cfg, answers, *, mutate=None, fail_new=False):
        self.config = cfg
        self.answers = list(answers)
        self.mutate = mutate
        self.fail_new = fail_new
        self.model_sha256 = None
        self.session_id = None
        self.connected = False
        self.closed = False
        self.events = []
        self.lock = threading.RLock()
        self.owned = False

    def open(self):
        if self.connected:
            raise AssertionError("native worker started twice")
        self.connected = True
        self.model_sha256 = MODEL
        self.events.append("open")
        return {
            "status": "native-gguf-ready",
            "source_bound": True,
            "physical_device_qualified": False,
            "release_certified": False,
        }

    def request(self, op, **fields):
        self.events.append(op)
        if op == "new":
            if self.fail_new:
                raise RuntimeError("synthetic SQLite setup refused")
            self.session_id = SESSION
            return {"status": "new-durable-session", "session_id": SESSION}
        if op != "turn" or not self.owned or not self.answers:
            raise AssertionError("unreviewed native op or unbounded model turn")
        if fields.get("context") is not False:
            raise AssertionError("native request reused unapproved chat history")
        answer = self.answers.pop(0)
        if self.mutate is not None:
            self.mutate(len(self.events), fields)
        return {
            "status": "committed-native-chat-turn",
            "request_id": fields["request_id"],
            "turn": {
                "request_id": fields["request_id"],
                "session_id": SESSION,
                "model_sha256": MODEL,
                "answer": answer,
                "output_sha256": sha256(answer.encode()).hexdigest(),
                "authoritative_commit": True,
                "replayed": False,
                "device_qualified": False,
                "release_certified": False,
            },
        }

    @contextmanager
    def exclusive_batch(self, _digest):
        self.lock.acquire()
        if not self.connected or self.owned:
            self.lock.release()
            raise AssertionError("source-work exclusive lease missing")
        self.owned = True
        try:
            yield
        finally:
            self.owned = False
            self.lock.release()

    def close(self):
        self.closed = True
        self.connected = False
        self.events.append("close")


class NativeHeadlessRequestParserTests(unittest.TestCase):
    def test_strict_native_request_schema_and_no_approval_from_json(self):
        selected = request()
        parsed = native_cli.parse_native_request(json.dumps(selected).encode())
        self.assertEqual(parsed["maximum_attempts"], 2)
        self.assertEqual(parsed["gpu_layers"], 0)
        bad = (
            {},
            dict(selected, shell=True),
            dict(selected, action="merge-to-main"),
            dict(selected, action="execute-python"),
            dict(selected, action=[]),
            dict(selected, format=[]),
            dict(selected, format="arbitrary-work"),
            dict(selected, model_root="../bad"),
            dict(selected, project_root="/private/../traversal"),
            dict(selected, state_dir="/private/../escape"),
            dict(selected, maximum_attempts=0),
            dict(selected, maximum_attempts=True),
            dict(selected, maximum_attempts=4),
            dict(selected, source_paths=["../bad.py"]),
            dict(selected, source_paths=[".git/config"]),
            dict(selected, source_paths=["src/core.py", "src/CORE.py"]),
            dict(selected, source_context_sha256="f"*64),
            dict(selected, goal=""),
            dict(selected, goal="x" * 4097),
            dict(selected, context_tokens=100),
            dict(selected, max_output_tokens=8192),
            dict(selected, gpu_layers=2),
            dict(selected, threads=0),
            dict(selected, threads=True),
            dict(selected, capacity_budget_bytes=-1),
            dict(selected, inference_ms=0),
            dict(selected, job_sha256="a"*64),
        )
        for obj in bad:
            with self.subTest(value=repr(obj)[:100]), self.assertRaises(
                (native_cli.HeadlessNativeSourceHold, ValueError),
            ):
                native_cli.parse_native_request(json.dumps(obj).encode())

    def test_generated_request_requires_exact_inspected_job(self):
        req = request(action="generate")
        with self.assertRaises(native_cli.HeadlessNativeSourceHold):
            native_cli.parse_native_request(json.dumps(req).encode())
        selected = dict(req, job_sha256="a" * 64)
        self.assertEqual(
            native_cli.parse_native_request(json.dumps(selected).encode())["action"],
            "generate",
        )

    def test_duplicate_nonfinite_untyped_and_excessive_native_json_rejected(self):
        for raw in (
            b"{}", b"[]", b"",
            b'{"schema":"x","schema":"x"}',
            b'{"cpu":NaN}',
            b'{"source_paths":Infinity}',
            b"x"*(native_cli.MAX_REQUEST_BYTES + 1),
            b"\xff",
        ):
            with self.subTest(raw=raw[:32]), self.assertRaises(
                native_cli.HeadlessNativeSourceHold,
            ):
                native_cli.parse_native_request(raw)

    def test_headless_review_requires_no_native_approval_flags(self):
        req = request()
        with self.assertRaises(native_cli.HeadlessNativeSourceHold):
            native_cli.execute_native_request(
                req, approve_native=True,
                bridge_factory=lambda cfg: None,
            )
        with self.assertRaises(native_cli.HeadlessNativeSourceHold):
            native_cli.execute_native_request(
                req, emit_private_proposal=True,
                bridge_factory=lambda cfg: None,
            )


@unittest.skipUnless(
    os.name == "posix" and hasattr(os, "O_NOFOLLOW"),
    "Native source+model custody is POSIX/WSL2-first",
)
class HeadlessNativeSessionTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="jeeves-native-cli-fixture-")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name) / "project"
        self.root.mkdir(mode=0o700)
        (self.root / "src").mkdir(mode=0o700)
        self.original = "def core():\n    return 1\n"
        self.file = self.root / "src/core.py"
        self.file.write_text(self.original, encoding="utf-8")
        self.old_sha = sha256(self.original.encode()).hexdigest()

        def temp_root(value):
            return os.open(
                value, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
            )
        for module in (workspace, edits, bundle, context):
            patcher = mock.patch.object(
                module, "_open_root", side_effect=temp_root,
            )
            patcher.start()
            self.addCleanup(patcher.stop)

    def inspect(self, *, with_context=True, **kwargs):
        req = request(
            project_root=self.root,
            source_paths=["src/core.py"] if with_context else [],
            **kwargs,
        )
        result = native_cli.execute_native_request(
            req, bridge_factory=lambda _cfg: self.fail(
                "inspection must not touch installed model",
            ),
        )
        self.assertEqual(result["status"],
                         "operator-review-required-before-native-model")
        self.assertFalse(result["native_gguf_started"])
        self.assertFalse(result["source_files_modified"])
        self.assertFalse(result["git_commands_executed"])
        self.assertFalse(result["release_certified"])
        self.assertNotIn(self.original, repr(result))
        self.assertNotIn(str(self.root), repr(result))
        return req, result

    def gen_request(self, **opts):
        base, inspected = self.inspect(**opts)
        return dict(
            base, action="generate", job_sha256=inspected["job_sha256"],
            source_context_sha256=inspected["source_context_sha256"],
        )

    def test_verified_original_source_and_real_bridge_contract_one_committed_turn(self):
        req = self.gen_request()
        observed = []
        worker = FakeNativeBridge(None, [package(self.old_sha)])
        def factory(cfg):
            observed.append(cfg)
            worker.config = cfg
            return worker
        with (
            mock.patch("subprocess.run") as shell,
            mock.patch("os.system") as system,
        ):
            report = native_cli.execute_native_request(
                req, approve_native=True, bridge_factory=factory,
            )
        self.assertEqual(report["status"], "review-required")
        self.assertTrue(report["source_receipt_verified"])
        self.assertEqual(report["native_model_sha256"], MODEL)
        self.assertEqual(report["durable_session_id"], SESSION)
        self.assertEqual(report["native_source"]["attempt_count"], 1)
        self.assertEqual(report["native_source"]["source_context_sha256"]
                         if "source_context_sha256" in report["native_source"] else
                         report["native_source"]["operator_source_context_sha256"],
                         req["source_context_sha256"])
        self.assertEqual(report["native_source"]["source_manifest_sha256"],
                         report["native_source"]["source_manifest_sha256"])
        self.assertFalse(report["source_files_modified"])
        self.assertFalse(report["git_commands_executed"])
        self.assertFalse(report["private_proposal_emitted"])
        self.assertNotIn("private_proposal", report)
        self.assertNotIn("def core", repr(report))
        self.assertEqual(worker.events, ["open", "new", "turn", "close"])
        self.assertTrue(worker.closed)
        self.assertEqual(self.file.read_text(), self.original)
        self.assertFalse((self.root / "src/new.py").exists())
        self.assertEqual(len(observed), 1)
        cfg = observed[0]
        self.assertTrue(cfg.enable_pressure_guard)
        self.assertFalse(cfg.enable_signed_source_tool)
        self.assertEqual(cfg.gpu_layers, 0)
        self.assertEqual(cfg.context, 4096)
        self.assertEqual(cfg.tenant, "local")
        shell.assert_not_called()
        system.assert_not_called()

    def test_explicit_print_private_source_requires_extra_cli_flag(self):
        req = self.gen_request()
        worker = FakeNativeBridge(None, [package(self.old_sha)])
        result = native_cli.execute_native_request(
            req, approve_native=True, emit_private_proposal=True,
            bridge_factory=lambda cfg: worker,
        )
        self.assertTrue(result["private_proposal_emitted"])
        self.assertEqual(result["private_proposal"], package(self.old_sha))
        self.assertEqual(self.file.read_text(), self.original)

    def test_task_hash_changes_with_goal_or_resource_budget(self):
        req, inspected = self.inspect()
        for change in (
            {"goal": "Do a materially different project change"},
            {"threads": 2},
            {"maximum_attempts": 1},
            {"format": "new-files"},
        ):
            altered = dict(req, **change)
            altered_inspect = native_cli.execute_native_request(
                altered,
                bridge_factory=lambda cfg: self.fail("no model in inspect"),
            )
            self.assertNotEqual(
                inspected["job_sha256"], altered_inspect["job_sha256"],
            )

    def test_missing_native_approval_never_constructs_installed_model(self):
        req = self.gen_request()
        created = []
        with self.assertRaises(native_cli.HeadlessNativeSourceHold):
            native_cli.execute_native_request(
                req, approve_native=False,
                bridge_factory=lambda cfg: created.append(cfg),
            )
        self.assertEqual(created, [])
        self.assertEqual(self.file.read_text(), self.original)

    def test_generation_refuses_forged_or_stale_job_before_launch(self):
        req = self.gen_request()
        started = []
        for change in (
            {"job_sha256": "f"*64},
            {"goal": "Retarget project without owner inspection"},
            {"threads": 2},
        ):
            with self.subTest(change=change), self.assertRaises(
                native_cli.HeadlessNativeSourceHold,
            ):
                native_cli.execute_native_request(
                    dict(req, **change), approve_native=True,
                    bridge_factory=lambda cfg: started.append(cfg),
                )
        self.assertEqual(started, [])

    def test_source_changed_after_task_inspection_blocks_real_native_start(self):
        req = self.gen_request()
        self.file.write_text("def core():\n    return 17\n", encoding="utf-8")
        created = []
        with self.assertRaises(native_cli.HeadlessNativeSourceHold):
            native_cli.execute_native_request(
                req, approve_native=True,
                bridge_factory=lambda cfg: created.append(cfg),
            )
        self.assertEqual(created, [])
        self.assertEqual(self.file.read_text(), "def core():\n    return 17\n")

    def test_native_new_session_failure_does_not_infer_or_retry(self):
        req = self.gen_request()
        worker = FakeNativeBridge(None, [], fail_new=True)
        with self.assertRaises(RuntimeError):
            native_cli.execute_native_request(
                req, approve_native=True,
                bridge_factory=lambda cfg: worker,
            )
        self.assertEqual(worker.events, ["open", "new", "close"])
        self.assertTrue(worker.closed)

    def test_file_drift_during_committed_turn_is_terminal_no_second_inference(self):
        req = self.gen_request()
        def change(_n, _fields):
            self.file.write_text("def core():\n    return 99\n", encoding="utf-8")
        worker = FakeNativeBridge(
            None, [package(self.old_sha), package(self.old_sha)],
            mutate=change,
        )
        with self.assertRaises(context.SourceContextHold):
            native_cli.execute_native_request(
                req, approve_native=True,
                bridge_factory=lambda cfg: worker,
            )
        self.assertEqual(worker.events, ["open", "new", "turn", "close"])
        self.assertTrue(worker.closed)
        self.assertEqual(self.file.read_text(), "def core():\n    return 99\n")

    def test_failed_generated_json_stops_at_exact_operator_turn_budget(self):
        req = self.gen_request(attempts=1)
        worker = FakeNativeBridge(None, ["not JSON"])
        result = native_cli.execute_native_request(
            req, approve_native=True,
            bridge_factory=lambda cfg: worker,
        )
        self.assertEqual(result["status"], "held-exhausted")
        self.assertEqual(result["native_source"]["attempt_count"], 1)
        self.assertFalse(result["private_proposal_emitted"])
        self.assertFalse(result["release_certified"])
        self.assertEqual(worker.events, ["open", "new", "turn", "close"])

    def test_no_context_new_file_mode_is_supported(self):
        req = self.gen_request(with_context=False, format="new-files")
        reply = json.dumps({
            "schema": workspace.SCHEMA,
            "files": [{"path": "src/generated.py", "content": "x=1\n"}],
        })
        worker = FakeNativeBridge(None, [reply])
        result = native_cli.execute_native_request(
            req, approve_native=True,
            bridge_factory=lambda cfg: worker,
        )
        self.assertEqual(result["status"], "review-required")
        self.assertIsNone(result["source_context_sha256"])
        self.assertFalse((self.root / "src/generated.py").exists())

    def test_actual_main_stdin_stdout_and_safe_generic_error_contract(self):
        req, inspected = self.inspect()
        public = StringIO()
        private_errors = StringIO()
        ok = native_cli.main(
            [], source=BytesIO(json.dumps(req).encode()),
            output=public, errors=private_errors,
            bridge_factory=lambda cfg: self.fail("inspection launched a GGUF"),
        )
        self.assertEqual(ok, 0)
        self.assertEqual(private_errors.getvalue(), "")
        payload = json.loads(public.getvalue())
        self.assertEqual(payload["job_sha256"], inspected["job_sha256"])
        self.assertNotIn(str(self.root), public.getvalue())
        self.assertNotIn(self.original, public.getvalue())
        bad = dict(req, action="generate")
        public = StringIO()
        private_errors = StringIO()
        code = native_cli.main(
            ["--approve-native-generation"],
            source=BytesIO(json.dumps(bad).encode()),
            output=public, errors=private_errors,
            bridge_factory=lambda cfg: self.fail("bad input started model"),
        )
        self.assertEqual(code, 2)
        self.assertEqual(public.getvalue(), "")
        self.assertIn("held", private_errors.getvalue())
        self.assertNotIn(str(self.root), private_errors.getvalue())


if __name__ == "__main__":
    unittest.main()
