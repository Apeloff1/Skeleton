"""Cold restart custody, operator approval and read-only SQLite batch recovery.

These source-only tests intentionally contain no GGUF, GPU, source rights
grant, outside process, or release certification. Actual original run IDs
must survive exact save/reopen without an unapproved native retry.
"""
from __future__ import annotations

from contextlib import contextmanager
from hashlib import sha256
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest import mock

from skeleton.ai.runtime.operational_ai.laptop_runtime.desktop_batch_work import (
    parse_durable_batch,
)
from skeleton.ai.runtime.operational_ai.laptop_runtime.desktop_batch_recovery import (
    BatchRecoveryHold, serialize_recovery, parse_recovery,
    save_reviewed_recovery, load_private_recovery, inspect_original_work,
)

MODEL = "a" * 64
ANSWER = "b" * 64


def batch(n=4):
    return parse_durable_batch(json.dumps({
        "schema": "jeeves.desktop.durable-work-batch.v1",
        "items": [{
            "title": "Original private work " + str(i),
            "task": "Implement local-only feature: original bytes " + str(i),
            "maximum_steps": 8,
            "maximum_model_calls": 8,
            "maximum_wall_seconds": 180,
        } for i in range(n)],
    }, ensure_ascii=False))


class RecoveryEncodingTests(unittest.TestCase):
    def test_exact_ids_original_tasks_and_budgets_survive_cold_reopen(self):
        planned = batch(18)
        raw = serialize_recovery(planned)
        restored = parse_recovery(
            raw, expected_manifest_sha256=planned.manifest_sha256,
        )
        self.assertEqual(restored, planned)
        self.assertEqual(serialize_recovery(restored), raw)
        self.assertEqual([i.run_id for i in restored.items],
                         [i.run_id for i in planned.items])
        self.assertEqual([i.task for i in restored.items],
                         [i.task for i in planned.items])
        self.assertEqual(restored.aggregate_model_calls, 18 * 8)

    def test_private_prompt_not_leaked_through_a_public_receipt(self):
        planned = batch()
        public = planned.to_public()
        self.assertEqual(public["manifest_sha256"], planned.manifest_sha256)
        for private in ("Implement local-only feature", "original bytes"):
            self.assertNotIn(private, repr(public))
        encoded = serialize_recovery(planned)
        self.assertIn(b"Implement local-only feature", encoded)
        self.assertLess(len(encoded), 262144)

    def test_changed_original_task_is_not_approved_by_old_digest(self):
        chosen = batch()
        before = serialize_recovery(chosen)
        doc = json.loads(before)
        doc["items"][0]["task"] = "Changed task: steal SQLite key"
        altered = json.dumps(
            doc, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        ).encode("utf-8")
        with self.assertRaises((BatchRecoveryHold, ValueError)):
            parse_recovery(
                altered,
                expected_manifest_sha256=chosen.manifest_sha256,
            )
        self.assertEqual(parse_recovery(
            before, expected_manifest_sha256=chosen.manifest_sha256,
        ), chosen)

    def test_replaced_original_run_id_cannot_borrow_prior_sqlite_history(self):
        chosen = batch()
        doc = json.loads(serialize_recovery(chosen))
        doc["items"][0]["run_id"] = "wrun_" + "0" * 32
        changed = json.dumps(doc, ensure_ascii=False, sort_keys=True,
                             separators=(",", ":")).encode("utf-8")
        with self.assertRaises((BatchRecoveryHold, ValueError)):
            parse_recovery(
                changed, expected_manifest_sha256=chosen.manifest_sha256,
            )

    def test_ambiguous_duplicate_unknown_and_noncannonical_records_hold(self):
        chosen = batch()
        raw = serialize_recovery(chosen)
        bads = (
            b"{}",
            raw + b" ",
            raw.replace(b'"schema":', b'"unexpected":123,"schema":', 1),
            raw.replace(b'"items":', b'"items":[],"items":', 1),
            raw.replace(b'"run_id":"wrun_', b'"run_id":"foreign_', 1),
            raw.replace(b'"maximum_model_calls":8', b'"maximum_model_calls":NaN', 1),
            b"\xff",
            b"x" * 262145,
        )
        for b in bads:
            with self.subTest(size=len(b)), self.assertRaises(
                (ValueError, BatchRecoveryHold),
            ):
                parse_recovery(
                    b, expected_manifest_sha256=chosen.manifest_sha256,
                )

    def test_cannot_accept_partial_or_untyped_operator_digest(self):
        chosen = batch()
        raw = serialize_recovery(chosen)
        for forged in (
            "", None, True, chosen.manifest_sha256[:20],
            "f" * 64, chosen.manifest_sha256.upper(),
        ):
            with self.subTest(forged=forged), self.assertRaises(
                BatchRecoveryHold,
            ):
                parse_recovery(raw, expected_manifest_sha256=forged)


@unittest.skipUnless(os.name == "posix", "Descriptor-anchored private recovery needs POSIX")
class PrivateFilesystemRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory(prefix="jeeves-recovery-")
        self.path = Path(self.folder.name)
        os.chmod(self.path, 0o700)
        self.plan = batch(3)
        self.saved = self.path / "approved.jeevesbatch"

    def tearDown(self):
        self.folder.cleanup()

    def _save(self):
        return save_reviewed_recovery(
            self.plan, self.saved,
            expected_manifest_sha256=self.plan.manifest_sha256,
            approve_private_export=True,
        )

    def test_private_exact_saved_file_is_mode_0600_and_cold_reopen_readonly(self):
        with (
            mock.patch("subprocess.Popen") as process,
            mock.patch("subprocess.run") as run,
        ):
            receipt = self._save()
            reopened = load_private_recovery(
                self.saved,
                expected_manifest_sha256=self.plan.manifest_sha256,
            )
            process.assert_not_called()
            run.assert_not_called()
        self.assertEqual(reopened, self.plan)
        self.assertEqual(receipt["file_sha256"], sha256(self.saved.read_bytes()).hexdigest())
        self.assertEqual(receipt["task_count"], 3)
        self.assertFalse(receipt["native_inference_started"])
        self.assertFalse(receipt["automatic_resume"])
        self.assertFalse(receipt["release_certified"])
        st = os.stat(self.saved, follow_symlinks=False)
        self.assertTrue(stat.S_ISREG(st.st_mode))
        self.assertEqual(st.st_mode & 0o777, 0o600)
        self.assertEqual(st.st_nlink, 1)
        self.assertEqual(st.st_uid, os.getuid())

    def test_existing_file_never_overwritten_even_when_original_is_approved(self):
        self._save()
        original = self.saved.read_bytes()
        with self.assertRaises(FileExistsError):
            self._save()
        self.assertEqual(self.saved.read_bytes(), original)

    def test_symlink_leaf_is_not_read_or_overwritten(self):
        foreign = self.path / "foreign.txt"
        foreign.write_bytes(b"private external source, not a saved work order")
        self.saved.symlink_to(foreign)
        with self.assertRaises((OSError, BatchRecoveryHold)):
            self._save()
        with self.assertRaises((OSError, BatchRecoveryHold)):
            load_private_recovery(
                self.saved, expected_manifest_sha256=self.plan.manifest_sha256,
            )
        self.assertEqual(foreign.read_bytes(),
                         b"private external source, not a saved work order")

    def test_foreign_hardlink_is_rejected_before_recovery(self):
        self._save()
        alias = self.path / "hardlink.jeevesbatch"
        os.link(self.saved, alias)
        with self.assertRaises(BatchRecoveryHold):
            load_private_recovery(
                alias, expected_manifest_sha256=self.plan.manifest_sha256,
            )

    def test_group_writable_parent_is_not_accepted(self):
        os.chmod(self.path, 0o770)
        with self.assertRaises((BatchRecoveryHold, ValueError)):
            self._save()
        self.assertFalse(self.saved.exists())

    def test_world_readable_saved_file_not_trusted(self):
        self._save()
        os.chmod(self.saved, 0o644)
        with self.assertRaises(BatchRecoveryHold):
            load_private_recovery(
                self.saved, expected_manifest_sha256=self.plan.manifest_sha256,
            )

    def test_file_tampering_and_wrong_operator_sha_are_fenced(self):
        self._save()
        with self.assertRaises(BatchRecoveryHold):
            load_private_recovery(
                self.saved, expected_manifest_sha256="a" * 64,
            )
        with self.saved.open("wb") as output:
            output.write(b'{"schema":"jeeves.desktop.private-batch-recovery.v1"}')
        with self.assertRaises(BatchRecoveryHold):
            load_private_recovery(
                self.saved,
                expected_manifest_sha256=self.plan.manifest_sha256,
            )

    def test_no_unapproved_or_untyped_export(self):
        for approved, expected in (
            (False, self.plan.manifest_sha256),
            (1, self.plan.manifest_sha256),
            (True, "b" * 64),
            (True, ""),
        ):
            with self.subTest(approved=approved), self.assertRaises(BatchRecoveryHold):
                save_reviewed_recovery(
                    self.plan, self.saved,
                    expected_manifest_sha256=expected,
                    approve_private_export=approved,
                )
        self.assertFalse(self.saved.exists())


class ReadOnlyRecoveredSQLiteTests(unittest.TestCase):
    def setUp(self):
        self.plan = batch(3)

    class ReadOnlyWorker:
        def __init__(self, *, action="inspect", tamper=None, disconnect=False):
            self.connected = not disconnect
            self.calls = []
            self.lease_count = 0
            self.expected_action = action
            self.tamper = tamper or {}
        @contextmanager
        def exclusive_batch(self, manifest_sha256):
            self.lease_count += 1
            try:
                yield
            finally:
                self.lease_count -= 1
        def request(self, op, **fields):
            if self.lease_count != 1 or op != "durable":
                raise AssertionError("recovery escaped original native lease")
            if fields.get("action") in ("start", "resume"):
                raise AssertionError("cold recovery must NEVER invoke native work")
            self.calls.append((op, fields.copy()))
            status = (
                "durable-work-inspected" if fields["action"] == "inspect"
                else "durable-work-replayed"
            )
            nested = (
                "inspected" if fields["action"] == "inspect"
                else "terminal-replayed"
            )
            result = {
                "status": status,
                "run_id": fields["run_id"],
                "durable": {
                    "schema": "jeeves.desktop.durable-work.v1",
                    "action": fields["action"], "status": nested,
                    "run_id": fields["run_id"],
                    "model_sha256": MODEL,
                    "native_generation_executed": False,
                    "automatic_resume": False,
                    "release_certified": False,
                    "device_qualified": False,
                    "success": True,
                    "replayed_without_native_generation": True,
                    "output_sha256": ANSWER,
                },
            }
            result["durable"].update(self.tamper)
            return result

    def _reconcile(self, worker, *, sequence=2, action="inspect",
                   digest=None, run_id=None):
        item = self.plan.items[sequence - 1]
        return inspect_original_work(
            worker, self.plan,
            sequence=sequence, action=action,
            expected_manifest_sha256=digest if digest is not None
            else self.plan.manifest_sha256,
            approved_run_id=run_id if run_id is not None else item.run_id,
        )

    def test_only_one_existing_work_inspection_with_original_exact_prompt(self):
        worker = self.ReadOnlyWorker()
        receipt = self._reconcile(worker)
        self.assertEqual(receipt.run_id, self.plan.items[1].run_id)
        self.assertEqual(receipt.action, "inspect")
        self.assertFalse(receipt.native_generation_executed)
        self.assertFalse(receipt.automatic_retry)
        self.assertEqual(worker.lease_count, 0)
        self.assertEqual(len(worker.calls), 1)
        op, fields = worker.calls[0]
        self.assertEqual(fields["run_id"], self.plan.items[1].run_id)
        self.assertEqual(fields["prompt"], self.plan.items[1].task)
        self.assertEqual(fields["maximum_steps"], self.plan.items[1].maximum_steps)
        self.assertEqual(fields["maximum_model_calls"], self.plan.items[1].maximum_model_calls)
        self.assertEqual(fields["maximum_wall_seconds"], self.plan.items[1].maximum_wall_seconds)
        self.assertNotIn(self.plan.items[1].task, repr(receipt.to_public()))

    def test_explicit_sealed_replay_is_read_only_without_native_generation(self):
        worker = self.ReadOnlyWorker(action="replay")
        receipt = self._reconcile(worker, action="replay")
        self.assertEqual(receipt.output_sha256, ANSWER)
        self.assertFalse(receipt.to_public()["native_generation_executed"])
        self.assertEqual(worker.calls[0][1]["action"], "replay")
        self.assertEqual(len(worker.calls), 1)

    def test_unapproved_resume_or_start_cannot_touch_native_worker(self):
        worker = self.ReadOnlyWorker()
        for action in ("start", "resume", "retry", "", None, True):
            with self.subTest(action=action), self.assertRaises(BatchRecoveryHold):
                self._reconcile(worker, action=action)
        self.assertEqual(worker.calls, [])
        self.assertEqual(worker.lease_count, 0)

    def test_wrong_plan_or_selected_run_id_fails_before_native_request(self):
        worker = self.ReadOnlyWorker()
        with self.assertRaises(BatchRecoveryHold):
            self._reconcile(worker, digest="f" * 64)
        with self.assertRaises(BatchRecoveryHold):
            self._reconcile(worker, run_id="wrun_" + "0" * 32)
        with self.assertRaises(BatchRecoveryHold):
            self._reconcile(worker, sequence=0)
        self.assertEqual(worker.calls, [])

    def test_native_source_or_restart_receipt_tamper_holds(self):
        for tamper in (
            {"run_id": "wrun_" + "f" * 32},
            {"native_generation_executed": True},
            {"automatic_resume": True},
            {"release_certified": True},
            {"device_qualified": True},
            {"status": "terminal-committed"},
            {"model_sha256": "not a digest"},
        ):
            with self.subTest(tamper=tamper):
                worker = self.ReadOnlyWorker(tamper=tamper)
                with self.assertRaises(BatchRecoveryHold):
                    self._reconcile(worker)
                self.assertEqual(len(worker.calls), 1)

    def test_worker_disconnected_is_a_hold_not_implicit_reactivation(self):
        worker = self.ReadOnlyWorker(disconnect=True)
        with self.assertRaises(BatchRecoveryHold):
            self._reconcile(worker)
        self.assertEqual(worker.calls, [])


if __name__ == "__main__":
    unittest.main()
