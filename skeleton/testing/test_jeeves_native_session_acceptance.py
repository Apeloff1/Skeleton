"""True SQLite multi-turn native session acceptance, SYNTHETIC generator only.

All source-only cases exercise the real supervisor and durable replay. No
case loads physical GGUF bytes, observes real device pressure or qualifies
model licenses; runtime and GUI readiness retain independent holds.
"""
from __future__ import annotations

from contextlib import nullcontext
from hashlib import sha256
from io import BytesIO, StringIO, TextIOWrapper
import json
import os
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest import mock

from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.contracts import (
    Identity, SpineLimits,
)
from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.database import SpineDatabase
from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.lease import SessionGate
from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.coordinator import ExecutionSpine
from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.supervisor import SupervisedAI
from skeleton.jeeves.agent.native_session_acceptance import (
    NativeSessionHold, SessionCase, SessionBudget, run_native_session,
    verify_cold_session_replay,
)
from skeleton.jeeves.agent.native_session_cli import (
    _casebook, main as session_cli,
)
from skeleton.testing.test_jeeves_native_sqlite_integration import (
    MODEL, TOKENIZER, ANSWER, SyntheticallyGenerated,
)


def _cases(n=2, *, expected=None):
    return tuple(
        SessionCase(
            f"case_{i+1}", f"Private operator turn {i+1}",
            expected_output_sha256=expected,
        ) for i in range(n)
    )


@unittest.skipUnless(os.name == "posix" and Path("/proc/self/fd").is_dir(),
                     "real protected SQLite requires Linux /proc")
class TestRealSqliteNativeSessionAcceptance(unittest.TestCase):
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

    def _open(self, *, subject="operator"):
        self.db = SpineDatabase(self.root)
        self.gate = SessionGate(self.root)
        self.backend = SyntheticallyGenerated()
        self.worker = SupervisedAI(ExecutionSpine(
            db=self.db, session_gate=self.gate,
            backend=self.backend,
            identity=Identity("local", subject, MODEL, TOKENIZER),
            limits=SpineLimits(
                input_bytes=32768, response_bytes=131072,
                max_output_tokens=128, context_tokens=4096,
            ),
        ))

    def _cold(self, *, subject="operator"):
        self._close()
        self._open(subject=subject)

    def test_two_real_sqlite_turns_preserve_order_and_receipts(self):
        report = run_native_session(
            self.worker, _cases(2), approved=True,
        )
        self.assertTrue(report.complete)
        self.assertFalse(report.cold_replay_verified)
        self.assertEqual(self.backend.calls, 2)
        self.assertEqual(len(report.turns), 2)
        self.assertEqual(
            [x.case_id for x in report.turns], ["case_1", "case_2"],
        )
        self.assertTrue(all(not x.replayed for x in report.turns))
        with self.db.snapshot() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM turns").fetchone(), (2,))
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM outbox").fetchone(), (2,))
        self.assertFalse(report.to_record()["release_certified"])

    def test_four_turns_commit_four_distinct_request_ids(self):
        report = run_native_session(
            self.worker, _cases(4), approved=True,
        )
        self.assertEqual(len({x.request_id for x in report.turns}), 4)
        self.assertEqual(self.backend.calls, 4)

    def test_cold_reopen_recovers_all_turns_with_zero_new_generation(self):
        cases = _cases(3)
        first = run_native_session(self.worker, cases, approved=True)
        self._cold()
        second = verify_cold_session_replay(
            self.worker, cases, first, approved=True,
        )
        self.assertTrue(second.cold_replay_verified)
        self.assertEqual(
            [x.output_sha256 for x in first.turns],
            [x.output_sha256 for x in second.turns],
        )
        self.assertEqual(self.backend.calls, 0)

    def test_no_approval_never_starts_a_model(self):
        with self.assertRaises(NativeSessionHold):
            run_native_session(self.worker, _cases(), approved=False)
        self.assertEqual(self.backend.calls, 0)

    def test_exact_expected_output_digest_passes(self):
        digest = sha256(ANSWER.encode("utf-8")).hexdigest()
        report = run_native_session(
            self.worker, _cases(2, expected=digest),
            approved=True,
        )
        self.assertTrue(all(x.exact_predicate_passed is True for x in report.turns))

    def test_incorrect_exact_output_digest_fails_closed(self):
        with self.assertRaises(NativeSessionHold):
            run_native_session(
                self.worker, _cases(1, expected="f" * 64),
                approved=True,
            )
        # A failed objective predicate does NOT undo the native SQLite
        # commit or authorize retry.
        self.assertEqual(self.backend.calls, 1)
        with self.db.snapshot() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM turns").fetchone(), (1,))

    def test_identical_prompts_still_obtain_distinct_committed_request_ids(self):
        cases = (
            SessionCase("a", "Same input"),
            SessionCase("b", "Same input"),
        )
        result = run_native_session(self.worker, cases, approved=True)
        self.assertNotEqual(result.turns[0].request_id, result.turns[1].request_id)
        self.assertEqual(self.backend.calls, 2)

    def test_same_model_source_required_across_cold_replay(self):
        cases = _cases()
        first = run_native_session(self.worker, cases, approved=True)
        self._cold(subject="other")
        with self.assertRaises(Exception):
            verify_cold_session_replay(self.worker, cases, first, approved=True)
        self.assertEqual(self.backend.calls, 0)

    def test_changed_casebook_prompt_is_rejected_without_generation(self):
        cases = _cases()
        first = run_native_session(self.worker, cases, approved=True)
        self._cold()
        wrong = (SessionCase("case_1", "Different secret task"), cases[1])
        with self.assertRaises(NativeSessionHold):
            verify_cold_session_replay(self.worker, wrong, first, approved=True)
        self.assertEqual(self.backend.calls, 0)

    def test_cold_replay_requires_independent_operator_approval(self):
        cases = _cases()
        first = run_native_session(self.worker, cases, approved=True)
        self._cold()
        with self.assertRaises(NativeSessionHold):
            verify_cold_session_replay(
                self.worker, cases, first, approved=False,
            )
        self.assertEqual(self.backend.calls, 0)

    def test_tampered_sqlite_response_is_not_replayed_as_native_output(self):
        cases = _cases()
        first = run_native_session(self.worker, cases, approved=True)
        with self.db.transaction() as conn:
            conn.execute(
                "UPDATE turns SET response=? WHERE request_id=?",
                (b"tampered", first.turns[0].request_id),
            )
        self._cold()
        with self.assertRaises(Exception):
            verify_cold_session_replay(
                self.worker, cases, first, approved=True,
            )
        self.assertEqual(self.backend.calls, 0)

    def test_cold_replay_does_not_allow_new_case_count(self):
        cases = _cases()
        first = run_native_session(self.worker, cases, approved=True)
        self._cold()
        with self.assertRaises(NativeSessionHold):
            verify_cold_session_replay(
                self.worker, _cases(3), first, approved=True,
            )
        self.assertEqual(self.backend.calls, 0)

    def test_over_budget_turn_count_denied_before_model(self):
        with self.assertRaises(NativeSessionHold):
            run_native_session(
                self.worker, _cases(3), approved=True,
                budget=SessionBudget(maximum_turns=2),
            )
        self.assertEqual(self.backend.calls, 0)

    def test_reserved_output_ceiling_denies_even_small_expected_answers(self):
        with self.assertRaises(NativeSessionHold):
            run_native_session(
                self.worker, _cases(2), approved=True,
                budget=SessionBudget(maximum_reserved_output_tokens=255),
            )
        self.assertEqual(self.backend.calls, 0)

    def test_duplicate_operator_case_ids_are_denied_pre_inference(self):
        cases = (SessionCase("same", "one"), SessionCase("same", "two"))
        with self.assertRaises(NativeSessionHold):
            run_native_session(self.worker, cases, approved=True)
        self.assertEqual(self.backend.calls, 0)

    def test_source_only_backend_error_does_not_attempt_automatic_retry(self):
        self.backend.fail = True
        with self.assertRaises(RuntimeError):
            run_native_session(self.worker, _cases(1), approved=True)
        self.assertEqual(self.backend.calls, 1)
        with self.db.snapshot() as conn:
            self.assertEqual(conn.execute("SELECT state FROM requests").fetchone(), ("pending",))

    def test_model_text_is_not_in_public_receipt(self):
        report = run_native_session(self.worker, _cases(1), approved=True)
        record = report.to_record()
        self.assertNotIn(ANSWER, json.dumps(record))
        self.assertNotIn("Private operator turn", json.dumps(record))
        self.assertEqual(record["turns"][0]["output_sha256"], sha256(ANSWER.encode()).hexdigest())

    def test_casebook_rejects_unknown_fields(self):
        raw = json.dumps({"schema": "jeeves.native_session_casebook.v1",
                          "cases": [{"case_id": "a", "prompt": "task", "tool": "shell"}]}).encode()
        with self.assertRaises(NativeSessionHold):
            _casebook(raw)

    def test_casebook_rejects_duplicate_json_keys(self):
        raw = b'{"schema":"jeeves.native_session_casebook.v1","cases":[],"cases":[]}'
        with self.assertRaises(Exception):
            _casebook(raw)

    def test_casebook_rejects_nonfinite_json(self):
        raw = b'{"schema":"jeeves.native_session_casebook.v1","cases":NaN}'
        with self.assertRaises(Exception):
            _casebook(raw)

    def test_casebook_accepts_finite_typed_cases(self):
        cases = _cases()
        raw = json.dumps({
            "schema": "jeeves.native_session_casebook.v1",
            "cases": [
                {"case_id": c.case_id, "prompt": c.prompt} for c in cases
            ],
        }).encode()
        self.assertEqual(_casebook(raw), cases)

    def test_casebook_rejects_unpaired_approval(self):
        stdin = TextIOWrapper(
            BytesIO(b'{"schema":"jeeves.native_session_casebook.v1","cases":[]}'),
            encoding="utf-8",
        )
        stdout, stderr = StringIO(), StringIO()
        with (
            mock.patch("sys.stdin", stdin),
            mock.patch("sys.stdout", stdout),
            mock.patch("sys.stderr", stderr),
            mock.patch("skeleton.jeeves.agent.native_session_cli.activate_checked",
                       side_effect=AssertionError("MUST NOT LOAD")) as loader,
        ):
            status = session_cli([
                "--model-root", "/untrusted", "--state-dir", str(self.root),
                "--tenant", "local", "--subject", "operator",
                "--casebook-stdin",
            ])
        self.assertEqual(status, 2)
        loader.assert_not_called()
        self.assertNotIn("untrusted", stderr.getvalue())

    def _cli(self, *, cold_replay=False, casebook=None):
        cases = _cases(2)
        raw = casebook if casebook is not None else json.dumps({
            "schema": "jeeves.native_session_casebook.v1",
            "cases": [{"case_id": c.case_id, "prompt": c.prompt} for c in cases],
        }).encode()
        stdin = TextIOWrapper(BytesIO(raw), encoding="utf-8")
        stdout, stderr = StringIO(), StringIO()
        called = [0]
        def activate(**kwargs):
            called[0] += 1
            if called[0] == 2:
                self._cold()
            return nullcontext(), self.worker, object()
        with (
            mock.patch("sys.stdin", stdin),
            mock.patch("sys.stdout", stdout),
            mock.patch("sys.stderr", stderr),
            mock.patch("skeleton.jeeves.agent.native_session_cli.activate_checked",
                       side_effect=activate),
            mock.patch("skeleton.jeeves.agent.native_session_cli.inspect_native_jeeves",
                       return_value=SimpleNamespace(source_bridge_ready=True)),
        ):
            args = [
                "--model-root", "/approved/private/model",
                "--state-dir", str(self.root),
                "--tenant", "local", "--subject", "operator",
                "--approve-native", "--casebook-stdin",
            ]
            if cold_replay:
                args.append("--cold-replay")
            status = session_cli(args)
        return status, stdout.getvalue(), stderr.getvalue(), called[0]

    def test_operator_cli_two_turns_source_only_and_no_answer_disclosure(self):
        status, stdout, stderr, count = self._cli()
        self.assertEqual(status, 0, stderr)
        self.assertEqual(count, 1)
        record = json.loads(stdout)
        self.assertEqual(record["committed_turns"], 2)
        self.assertNotIn(ANSWER, stdout)
        self.assertNotIn("Private operator turn", stdout)

    def test_operator_cli_cold_replays_on_second_native_epoch(self):
        status, stdout, stderr, count = self._cli(cold_replay=True)
        self.assertEqual(status, 0, stderr)
        self.assertEqual(count, 2)
        record = json.loads(stdout)
        self.assertTrue(record["cold_replay_verified"])
        self.assertEqual(self.backend.calls, 0)

    def test_operator_cli_missing_case_prevents_model_activation(self):
        raw = json.dumps({"schema": "jeeves.native_session_casebook.v1",
                          "cases": []}).encode()
        status, stdout, stderr, count = self._cli(casebook=raw)
        self.assertEqual(status, 2)
        self.assertEqual(stdout, "")
        self.assertEqual(count, 0)
        self.assertNotIn("Private operator turn", stderr)


if __name__ == "__main__":
    unittest.main()
