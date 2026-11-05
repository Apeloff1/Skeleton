"""Bounded serial native work-batch tests after the actual UI implementation.

All simulated workers are test-only. They verify **no** parallel inference,
no automatic retries, exact SHA/operator approval and unique canonical SQLite
run identities; they cannot certify physical GGUF or release readiness.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import FrozenInstanceError
from hashlib import sha256
import json
import threading
from unittest import mock
import unittest

from skeleton.ai.runtime.operational_ai.laptop_runtime.desktop_client import (
    DesktopConfig, DesktopBridge, DesktopBridgeHold,
)
from skeleton.ai.runtime.operational_ai.laptop_runtime.desktop_batch_work import (
    BatchHold, DurableBatchPlan, BatchRunReceipt, BatchItemReceipt,
    parse_durable_batch, SerialDurableBatchRunner,
)

MODEL = "a" * 64


def raw(*tasks, maximum_model_calls=8):
    items = [{
        "title": title,
        "task": task,
        "maximum_steps": 8,
        "maximum_model_calls": maximum_model_calls,
        "maximum_wall_seconds": 180,
    } for title, task in tasks]
    return json.dumps({
        "schema": "jeeves.desktop.durable-work-batch.v1",
        "items": items,
    }, sort_keys=True, ensure_ascii=False)


def plan(n=3):
    return parse_durable_batch(raw(*[
        ("Original task " + str(i), "Build private local feature " + str(i))
        for i in range(n)
    ]))


class FakeCommittedNative:
    def __init__(self, *, hold_at=None, disconnect_at=None, forged=False):
        self.hold_at = hold_at
        self.disconnect_at = disconnect_at
        self.forged = forged
        self.calls = []
        self.connected = True
        self._lock = threading.Lock()
        self._lease = threading.RLock()
        self._leased = False
        self._in_flight = False

    @contextmanager
    def exclusive_batch(self, manifest_sha256):
        if (
            type(manifest_sha256) is not str
            or len(manifest_sha256) != 64
            or not self._lease.acquire(blocking=False)
        ):
            raise BatchHold("original reviewed work lease unavailable")
        try:
            self._leased = True
            yield
        finally:
            self._leased = False
            self._lease.release()

    def request(self, op, **fields):
        self._lock.acquire()
        try:
            if not self._leased:
                raise RuntimeError("native work does not hold an exclusive lease")
            if self._in_flight:
                raise RuntimeError("parallel native inference unsafe")
            self._in_flight = True
            self.calls.append((op, dict(fields)))
            seq = len(self.calls)
            if self.hold_at == seq:
                raise RuntimeError("native SQLite effect uncertain")
            if self.disconnect_at == seq:
                self.connected = False
            result = {
                "status": "durable-work-committed",
                "run_id": fields["run_id"],
                "durable": {
                    "schema": "jeeves.desktop.durable-work.v1",
                    "status": "terminal-committed",
                    "run_id": fields["run_id"],
                    "model_sha256": MODEL,
                    "output_sha256": "b" * 64,
                    "success": True,
                    "automatic_resume": False,
                    "native_generation_executed": True,
                    "release_certified": False,
                    "usage": {"tool_calls": 0},
                },
            }
            if self.forged:
                result["durable"]["run_id"] = "wrun_foreign"
            return result
        finally:
            self._in_flight = False
            self._lock.release()



def _can_lease(bridge: DesktopBridge) -> bool:
    try:
        with bridge.exclusive_batch("b" * 64):
            return True
    except DesktopBridgeHold:
        return False


class DurableBatchAdmissionTests(unittest.TestCase):
    def test_typed_source_plan_allocates_distinct_visible_durable_run_ids(self):
        selected = plan(20)
        self.assertEqual(len(selected.items), 20)
        self.assertEqual(len({item.run_id for item in selected.items}), 20)
        self.assertEqual(selected.aggregate_model_calls, 160)
        self.assertEqual(selected.aggregate_wall_seconds, 3600)
        for item in selected.items:
            self.assertTrue(item.run_id.startswith("wrun_"))
            self.assertEqual(len(item.run_id), 37)
        receipt = selected.to_public()
        self.assertTrue(receipt["uses_canonical_durable_sqlite"])
        self.assertEqual(receipt["worker_count"], 1)
        self.assertEqual(receipt["provider_count"], 1)
        self.assertFalse(receipt["automatic_resume"])
        self.assertFalse(receipt["automatic_retries"])
        # Metadata legitimately includes a task *count*, not private text.
        self.assertNotIn("Build private local feature", repr(receipt))

    def test_reject_invalid_schema_duplicate_key_and_model_authority(self):
        bads = (
            "{}",
            '{"schema":"jeeves.desktop.durable-work-batch.v1","items":[]}',
            '{"schema":"jeeves.desktop.durable-work-batch.v1","items":[],"items":[]}',
            '{"schema":"jeeves.desktop.durable-work-batch.v1","items":[{"title":"x","task":"x","maximum_steps":NaN,"maximum_model_calls":8,"maximum_wall_seconds":180}]}',
            raw(("Only", "Task")).replace(
                '"title": "Only"', '"title": "Only", "grant_shell": true',
            ),
            raw(("Bad", "\x00secret")),
            raw(("One", "x" * 32769)),
        )
        for source in bads:
            with self.subTest(source=source[:100]), self.assertRaises(BatchHold):
                parse_durable_batch(source)

    def test_oversized_batch_aggregate_and_wall_limits_fail_closed(self):
        with self.assertRaises(BatchHold):
            plan(33)
        with self.assertRaises(BatchHold):
            parse_durable_batch(raw(*[
                ("Task " + str(i), "private " + "x" * 32000)
                for i in range(6)
            ]))
        too_long = json.loads(raw(*[
            ("Task " + str(i), "bounded native")
            for i in range(32)
        ]))
        for item in too_long["items"]:
            item["maximum_wall_seconds"] = 600
        with self.assertRaises(BatchHold):
            parse_durable_batch(json.dumps(too_long))

    def test_wrong_manifest_or_untyped_approval_cannot_invoke_worker(self):
        selected = plan()
        worker = FakeCommittedNative()
        for manifest, approved in (
            (selected.manifest_sha256, False),
            (selected.manifest_sha256, 1),
            ("f" * 64, True),
        ):
            with self.subTest(manifest=manifest,approved=approved), self.assertRaises(
                BatchHold,
            ):
                SerialDurableBatchRunner(
                    worker, selected, approved=approved,
                    expected_manifest_sha256=manifest,
                )
        self.assertEqual(worker.calls, [])


class SerialNativeWorkTests(unittest.TestCase):
    def _runner(self, worker, *, n=3, progress=None):
        chosen = plan(n)
        return SerialDurableBatchRunner(
            worker, chosen,
            expected_manifest_sha256=chosen.manifest_sha256,
            approved=True, progress=progress,
        ), chosen

    def test_three_committed_tasks_are_serial_and_preserve_exact_native_ids(self):
        worker = FakeCommittedNative()
        observed = []
        runner, selected = self._runner(
            worker, n=3, progress=lambda receipt: observed.append(receipt),
        )
        receipt = runner.execute()
        self.assertEqual(receipt.status, "completed")
        self.assertEqual(receipt.items_started, 3)
        self.assertEqual(receipt.items_committed, 3)
        self.assertIsNone(receipt.stopped_at_sequence)
        self.assertEqual(
            [item.run_id for item in observed],
            [item.run_id for item in selected.items],
        )
        self.assertEqual([call[0] for call in worker.calls], ["durable"] * 3)
        for n, (_, args) in enumerate(worker.calls):
            self.assertEqual(args["action"], "start")
            self.assertEqual(args["run_id"], selected.items[n].run_id)
            self.assertEqual(args["prompt"], selected.items[n].task)
            self.assertEqual(args["maximum_steps"], selected.items[n].maximum_steps)
            self.assertEqual(args["maximum_model_calls"], selected.items[n].maximum_model_calls)
            self.assertEqual(args["maximum_wall_seconds"], selected.items[n].maximum_wall_seconds)
        public = receipt.public_receipt()
        self.assertEqual(public["items_committed"], 3)
        self.assertFalse(public["automatic_retry"])
        self.assertEqual(public["source_of_truth"],
                         "canonical-principal-bound-SQLite-work-orders")
        self.assertNotIn("Build private", repr(public))

    def test_native_failure_at_second_stops_without_retrying_id(self):
        worker = FakeCommittedNative(hold_at=2)
        runner, selected = self._runner(worker, n=4)
        receipt = runner.execute()
        self.assertEqual(receipt.status, "held")
        self.assertEqual(receipt.items_started, 2)
        self.assertEqual(receipt.items_committed, 1)
        self.assertEqual(receipt.stopped_at_sequence, 2)
        self.assertEqual(len(worker.calls), 2)
        self.assertEqual(receipt.completed[1].status, "held")
        self.assertEqual(receipt.completed[1].run_id, selected.items[1].run_id)
        self.assertEqual(receipt.completed[1].output_sha256, None)

    def test_forged_durable_result_refused_as_uncertain_native_effect(self):
        worker = FakeCommittedNative(forged=True)
        runner, selected = self._runner(worker, n=3)
        receipt = runner.execute()
        self.assertEqual(receipt.status, "held")
        self.assertEqual(receipt.items_started, 1)
        self.assertEqual(receipt.items_committed, 0)
        self.assertEqual(len(worker.calls), 1)

    def test_explicit_stop_after_current_does_not_issue_subsequent_work(self):
        worker = FakeCommittedNative()
        active = []
        runner, selected = self._runner(worker, n=4)
        runner.progress = lambda item: (active.append(item), runner.stop_after_current())
        receipt = runner.execute()
        self.assertEqual(receipt.status, "operator-stopped")
        self.assertEqual(receipt.items_started, 1)
        self.assertEqual(receipt.items_committed, 1)
        self.assertEqual(len(worker.calls), 1)
        self.assertEqual(receipt.stopped_at_sequence, 2)

    def test_disconnected_worker_cannot_start_or_resurrect_native(self):
        worker = FakeCommittedNative()
        worker.connected = False
        runner, selected = self._runner(worker, n=3)
        receipt = runner.execute()
        self.assertEqual(receipt.status, "held")
        self.assertEqual(receipt.items_started, 0)
        self.assertEqual(receipt.stopped_at_sequence, 1)
        self.assertEqual(worker.calls, [])


    def test_unleased_native_worker_cannot_enter_admitted_queue(self):
        class NoLease:
            connected = True
            def request(self, op, **fields):
                raise AssertionError("never call unleased native inference")
        selected = plan(2)
        with self.assertRaises(BatchHold):
            SerialDurableBatchRunner(
                NoLease(), selected, approved=True,
                expected_manifest_sha256=selected.manifest_sha256,
            )

    def test_another_thread_cannot_interleave_when_native_bridge_is_leased(self):
        bridge = DesktopBridge(DesktopConfig(
            model_root="/trusted/model", state_dir="/private/state",
            tenant="local", subject="owner",
        ))
        bridge._started = True
        class Child:
            def poll(self):
                return None
        bridge._process = Child()
        outcome = []
        with bridge.exclusive_batch("a" * 64):
            def interloper():
                try:
                    bridge.request("status")
                    outcome.append("unsafe")
                except DesktopBridgeHold:
                    outcome.append("held")
            thread = threading.Thread(target=interloper)
            thread.start()
            thread.join(timeout=3)
            self.assertFalse(thread.is_alive())
        self.assertEqual(outcome, ["held"])
        self.assertTrue(bridge.connected)
        # A failed competing request is refused BEFORE writing any IPC data.
        self.assertIsNone(bridge._pressure_reason)

    def test_two_overlapping_serial_batches_on_one_bridge_cannot_both_start(self):
        bridge = DesktopBridge(DesktopConfig(
            model_root="/trusted/model", state_dir="/private/state",
            tenant="local", subject="owner",
        ))
        bridge._started = True
        bridge._process = type("Child", (), {"poll": lambda self: None})()
        outcome = []
        with bridge.exclusive_batch("a" * 64):
            t = threading.Thread(target=lambda: (
                outcome.append("unsafe") if _can_lease(bridge)
                else outcome.append("held")
            ))
            t.start()
            t.join(timeout=3)
            self.assertFalse(t.is_alive())
        self.assertEqual(outcome, ["held"])

    def test_second_execution_cannot_replay_same_ids(self):
        worker = FakeCommittedNative()
        runner, selected = self._runner(worker, n=1)
        self.assertEqual(runner.execute().status, "completed")
        with self.assertRaises(BatchHold):
            runner.execute()
        self.assertEqual(len(worker.calls), 1)

    def test_no_network_shell_or_subprocess_model_side_effect(self):
        worker = FakeCommittedNative()
        runner, selected = self._runner(worker, n=2)
        with (
            mock.patch("subprocess.Popen") as model,
            mock.patch("subprocess.run") as command,
        ):
            result = runner.execute()
            self.assertEqual(result.status, "completed")
            model.assert_not_called()
            command.assert_not_called()

    def test_all_tasks_are_immutable_only_after_manifest_approval(self):
        worker = FakeCommittedNative()
        runner, selected = self._runner(worker, n=2)
        with self.assertRaises(FrozenInstanceError):
            selected.items[0].task = "replaced by model"
        self.assertEqual(runner.execute().items_committed, 2)
        self.assertEqual(worker.calls[0][1]["prompt"], selected.items[0].task)


if __name__ == "__main__":
    unittest.main()
