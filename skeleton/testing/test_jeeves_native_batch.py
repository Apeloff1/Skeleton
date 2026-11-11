"""Cold-idempotent native batch conveyor with actual SQLite and synthetic backend.

Every accepted/replayed request uses the existing production spine; only the
generator is synthetic. No GGUF hardware, source rights, Windows install or
native cancellation is certified by source-only CI.
"""
from __future__ import annotations

from contextlib import nullcontext
from hashlib import sha256
from io import BytesIO, TextIOWrapper
import json
import os
from pathlib import Path
from types import SimpleNamespace
import tempfile
import sys
import unittest
from unittest import mock

from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.contracts import (
    Identity, SpineLimits, Conflict, Busy, IntegrityFailure,
)
from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.database import SpineDatabase
from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.lease import SessionGate
from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.coordinator import ExecutionSpine
from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.supervisor import SupervisedAI
from skeleton.jeeves.agent.native_batch_runtime import (
    NativeBatchHold, NativeBatchTask, NativeBatchPolicy, NativeBatchConveyor,
    preflight_batch_tasks,
)
from skeleton.jeeves.agent.native_batch_cli import (
    parse_casebook, main as batch_cli,
)
from skeleton.testing.test_jeeves_native_sqlite_integration import (
    MODEL, TOKENIZER, ANSWER, SyntheticallyGenerated,
)


def tasks(n=2, *, output=None):
    return tuple(
        NativeBatchTask(f"task_{i}", f"Private work item number {i}",
                        exact_output_sha256=output)
        for i in range(n)
    )


@unittest.skipUnless(os.name == "posix" and Path("/proc/self/fd").is_dir(),
                     "real protected SQLite requires Linux /proc")
class TestNativeBatchWithRealSqlite(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.db = None
        self.gate = None
        self._open()
        self.addCleanup(self._close)

    def _close(self):
        if self.gate is not None:
            self.gate.close()
            self.gate = None
        if self.db is not None:
            self.db.close()
            self.db = None

    def _open(self, *, tenant="local", subject="operator"):
        self.db = SpineDatabase(self.root)
        self.gate = SessionGate(self.root)
        self.backend = SyntheticallyGenerated()
        self.worker = SupervisedAI(ExecutionSpine(
            db=self.db, session_gate=self.gate,
            backend=self.backend,
            identity=Identity(tenant, subject, MODEL, TOKENIZER),
            limits=SpineLimits(
                input_bytes=32768, response_bytes=131072,
                max_output_tokens=128, context_tokens=4096,
            ),
        ))

    def _cold(self, *, tenant="local", subject="operator"):
        self._close()
        self._open(tenant=tenant, subject=subject)

    def _conveyor(self, **kwargs):
        return NativeBatchConveyor(self.worker, approved=True, **kwargs)

    def test_first_batch_commits_all_jobs_under_single_native_authority(self):
        result = self._conveyor().run("batch_001", tasks(3))
        self.assertEqual(result.committed, 3)
        self.assertEqual(result.replayed, 0)
        self.assertEqual(self.backend.calls, 3)
        self.assertEqual(len(result.receipts), 3)
        self.assertEqual(len({x.session_id for x in result.receipts}), 3)
        with self.db.snapshot() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM turns").fetchone(), (3,))
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM outbox").fetchone(), (3,))

    def test_second_identical_batch_replays_without_any_generation(self):
        first = self._conveyor().run("batch_001", tasks(3))
        result = self._conveyor().run("batch_001", tasks(3))
        self.assertEqual(result.committed, 0)
        self.assertEqual(result.replayed, 3)
        self.assertEqual(self.backend.calls, 3)
        self.assertEqual(result.batch_sha256, first.batch_sha256)
        self.assertEqual(
            [x.output_sha256 for x in first.receipts],
            [x.output_sha256 for x in result.receipts],
        )

    def test_cold_reopen_proves_same_committed_requests_without_generation(self):
        first = self._conveyor().run("batch_001", tasks(4))
        self._cold()
        result = self._conveyor().run("batch_001", tasks(4))
        self.assertEqual(result.replayed, 4)
        self.assertEqual(result.committed, 0)
        self.assertEqual(self.backend.calls, 0)
        self.assertEqual(result.batch_sha256, first.batch_sha256)

    def test_subset_replay_cannot_reuse_changed_task_under_same_identifier(self):
        first = self._conveyor().run("batch_001", tasks(2))
        self._cold()
        changed = (
            NativeBatchTask("task_0", "Changed private task"),
            tasks(2)[1],
        )
        with self.assertRaises(Conflict):
            self._conveyor().run("batch_001", changed)
        self.assertEqual(self.backend.calls, 0)

    def test_changed_batch_id_allocates_distinct_native_sessions(self):
        first = self._conveyor().run("batch_001", tasks(1))
        second = self._conveyor().run("batch_002", tasks(1))
        self.assertNotEqual(first.receipts[0].session_id,
                            second.receipts[0].session_id)
        self.assertEqual(self.backend.calls, 2)

    def test_same_task_ids_different_principal_never_replay_old_receipts(self):
        first = self._conveyor().run("batch_001", tasks(1))
        self._cold(subject="different")
        second = self._conveyor().run("batch_001", tasks(1))
        self.assertNotEqual(first.receipts[0].session_id,
                            second.receipts[0].session_id)
        self.assertEqual(self.backend.calls, 1)

    def test_native_failure_is_pending_and_never_retried_on_cold_rerun(self):
        self.backend.fail = True
        with self.assertRaises(RuntimeError):
            self._conveyor().run("batch_001", tasks(1))
        with self.db.snapshot() as conn:
            self.assertEqual(conn.execute("SELECT state FROM requests").fetchone(), ("pending",))
        self.assertEqual(self.backend.calls, 1)
        self._cold()
        with self.assertRaises(Busy):
            self._conveyor().run("batch_001", tasks(1))
        self.assertEqual(self.backend.calls, 0)

    def test_tampered_committed_response_is_not_replayed(self):
        self._conveyor().run("batch_001", tasks(1))
        with self.db.transaction() as conn:
            conn.execute("UPDATE turns SET response=?", (b"forged",))
        self._cold()
        with self.assertRaises(IntegrityFailure):
            self._conveyor().run("batch_001", tasks(1))
        self.assertEqual(self.backend.calls, 0)

    def test_wrong_exact_output_criterion_holds_without_undoing_native_commit(self):
        with self.assertRaises(NativeBatchHold):
            self._conveyor().run("batch_001", tasks(1, output="f" * 64))
        self.assertEqual(self.backend.calls, 1)
        with self.db.snapshot() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM turns").fetchone(), (1,))

    def test_correct_exact_output_criterion_passes(self):
        dig = sha256(ANSWER.encode()).hexdigest()
        result = self._conveyor().run("batch_001", tasks(2, output=dig))
        self.assertTrue(all(x.exact_objective_passed for x in result.receipts))

    def test_batch_preview_requires_no_model_generation(self):
        preview = self._conveyor().preflight("batch_001", tasks(5))
        self.assertEqual(preview["jobs"], 5)
        self.assertEqual(preview["reserved_output_tokens"], 5 * 128)
        self.assertFalse(preview["real_native_calls_started"])
        self.assertEqual(self.backend.calls, 0)

    def test_operator_policy_denies_oversized_model_reservation(self):
        policy = NativeBatchPolicy(maximum_reserved_output_tokens=100)
        with self.assertRaises(NativeBatchHold):
            self._conveyor(policy=policy).run("batch_001", tasks(1))
        self.assertEqual(self.backend.calls, 0)

    def test_duplicate_task_ids_cannot_be_submitted_to_native(self):
        duplicated = (NativeBatchTask("x", "one"), NativeBatchTask("x", "two"))
        with self.assertRaises(NativeBatchHold):
            self._conveyor().run("batch_001", duplicated)
        self.assertEqual(self.backend.calls, 0)

    def test_invalid_task_name_rejected_before_model(self):
        with self.assertRaises(Exception):
            NativeBatchTask("../../test", "Unapproved")
        self.assertEqual(self.backend.calls, 0)

    def test_unbounded_batch_policy_is_rejected(self):
        for amount in (0, -1, 1001, True, 1.2):
            with self.subTest(amount=amount), self.assertRaises(NativeBatchHold):
                NativeBatchPolicy(maximum_jobs=amount)

    def test_cli_preflight_rejects_batch_size_before_model_activation(self):
        with self.assertRaises(NativeBatchHold):
            preflight_batch_tasks(
                "batch_001", tasks(3),
                NativeBatchPolicy(maximum_jobs=2),
                configured_output_tokens=128,
            )

    def test_cli_preflight_rejects_invalid_native_output_ceiling(self):
        for size in (0, 8193, True, -1):
            with self.subTest(size=size), self.assertRaises(NativeBatchHold):
                preflight_batch_tasks(
                    "batch_001", tasks(1),
                    NativeBatchPolicy(), configured_output_tokens=size,
                )

    def test_cli_preflight_rejects_unknown_batch_id(self):
        with self.assertRaises(Exception):
            preflight_batch_tasks(
                "../../bad", tasks(1),
                NativeBatchPolicy(), configured_output_tokens=128,
            )

    def test_all_public_receipts_hide_private_prompts_and_response_text(self):
        result = self._conveyor().run("batch_001", tasks(1))
        raw = json.dumps(result.to_public_record())
        self.assertNotIn("Private work item", raw)
        self.assertNotIn(ANSWER, raw)
        self.assertFalse(result.to_public_record()["release_certified"])

    def test_casebook_parser_rejects_duplicate_json_keys(self):
        raw = b'{"schema":"jeeves.native_batch_casebook.v1","batch_id":"x","batch_id":"y","tasks":[]}'
        with self.assertRaises(Exception):
            parse_casebook(raw)

    def test_casebook_parser_rejects_unrecognized_operator_tool_grants(self):
        record = {
            "schema": "jeeves.native_batch_casebook.v1",
            "batch_id": "batch_001",
            "tasks": [{"task_id": "x", "prompt": "Private",
                       "tools": ["shell"]}],
        }
        with self.assertRaises(NativeBatchHold):
            parse_casebook(json.dumps(record).encode())

    def test_casebook_accepts_bounded_valid_typed_tasks(self):
        expected = tasks(3)
        raw = json.dumps({
            "schema": "jeeves.native_batch_casebook.v1",
            "batch_id": "batch_001",
            "tasks": [
                {"task_id": x.task_id, "prompt": x.prompt}
                for x in expected
            ],
        }).encode()
        batch, actual = parse_casebook(raw)
        self.assertEqual(batch, "batch_001")
        self.assertEqual(expected, actual)

    def _cli(self, *, approve=True, batch_json=None):
        raw = (batch_json if batch_json is not None else json.dumps({
            "schema": "jeeves.native_batch_casebook.v1",
            "batch_id": "batch_001",
            "tasks": [{"task_id": t.task_id, "prompt": t.prompt}
                      for t in tasks(2)],
        }).encode())
        stdin = TextIOWrapper(BytesIO(raw), encoding="utf-8")
        # Use actual buffered text streams: production emits to an owned
        # binary buffer, which a StringIO-only fixture does not provide.
        stdout = TextIOWrapper(BytesIO(), encoding="utf-8", write_through=True)
        stderr = TextIOWrapper(BytesIO(), encoding="utf-8", write_through=True)
        with (
            mock.patch("sys.stdin", stdin),
            mock.patch("sys.stdout", stdout),
            mock.patch("sys.stderr", stderr),
            mock.patch("skeleton.jeeves.agent.native_batch_cli.activate_checked",
                       return_value=(nullcontext(), self.worker, object())) as active,
            mock.patch("skeleton.jeeves.agent.native_batch_cli.inspect_native_jeeves",
                       return_value=SimpleNamespace(source_bridge_ready=True)),
            # Only the test fixture replaces the installed-source fence;
            # the production fence is separately tested to reject synthetic workers.
            mock.patch(
                "skeleton.jeeves.agent.native_batch_cli.NativeSourceFence",
                return_value=SimpleNamespace(assert_live=lambda _worker: None),
            ),
        ):
            arguments = [
                "--model-root", "/approved/private/model",
                "--state-dir", str(self.root),
                "--tenant", "local", "--subject", "operator",
                "--batch-stdin",
            ]
            if approve:
                arguments.append("--approve-native")
            status = batch_cli(arguments)
        stdout.flush()
        stderr.flush()
        return (
            status,
            stdout.buffer.getvalue().decode("utf-8", "strict"),
            stderr.buffer.getvalue().decode("utf-8", "strict"),
            active.call_count,
        )

    def test_cli_real_path_commits_synthetic_source_only_batch(self):
        # CI diagnosis reports only source function/line, never private data.
        # The operator CLI intentionally redacts exception text.
        attribute_sites = []
        def trace(frame, event, arg):
            if (event == "exception" and isinstance(arg[1], AttributeError)
                    and "/skeleton/" in frame.f_code.co_filename):
                attribute_sites.append((frame.f_code.co_name, frame.f_lineno))
            return trace
        prior_trace = sys.gettrace()
        try:
            sys.settrace(trace)
            status, stdout, stderr, calls = self._cli()
        finally:
            sys.settrace(prior_trace)
        self.assertEqual(status, 0, stderr + " attribute_sites=" + repr(attribute_sites[-20:]))
        self.assertEqual(calls, 1)
        public = json.loads(stdout)
        self.assertEqual(public["committed_jobs"], 2)
        self.assertEqual(self.backend.calls, 2)
        self.assertNotIn(ANSWER, stdout)

    def test_cli_repeat_uses_only_committed_sqlite_replay(self):
        first = self._cli()
        second = self._cli()
        self.assertEqual(first[0], 0, first[2])
        self.assertEqual(second[0], 0, second[2])
        self.assertEqual(json.loads(second[1])["replayed_jobs"], 2)
        self.assertEqual(self.backend.calls, 2)

    def test_cli_missing_operator_approval_blocks_activation(self):
        status, stdout, stderr, calls = self._cli(approve=False)
        self.assertEqual(status, 2)
        self.assertEqual(calls, 0)
        self.assertEqual(self.backend.calls, 0)
        self.assertEqual(stdout, "")

    def test_cli_invalid_batch_id_blocks_activation_before_model(self):
        bad = json.dumps({
            "schema": "jeeves.native_batch_casebook.v1",
            "batch_id": "../../unsafe",
            "tasks": [{"task_id": "x", "prompt": "Keep private"}],
        }).encode()
        status, stdout, stderr, calls = self._cli(batch_json=bad)
        self.assertEqual(status, 2)
        self.assertEqual(calls, 0)
        self.assertEqual(self.backend.calls, 0)
        self.assertNotIn("Keep private", stderr)


if __name__ == "__main__":
    unittest.main()
