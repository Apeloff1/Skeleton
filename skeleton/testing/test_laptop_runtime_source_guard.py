"""Fail-closed installed GGUF custody on the consumer laptop entry point.

Every worker/installer/source witness here is a synthetic test double. These
tests do not qualify real inference, installed rights, hardware, Windows 11,
WSL2, model performance or release. They test the production guard contract.
"""
from __future__ import annotations

from contextlib import ExitStack
from io import BytesIO, StringIO
from types import SimpleNamespace
from unittest import mock
import json
import threading
import unittest

from skeleton.ai.runtime.operational_ai.laptop_runtime.contracts import ContractViolation
from skeleton.ai.runtime.operational_ai.laptop_runtime.cli import main
from skeleton.ai.runtime.operational_ai.laptop_runtime.dispatcher import LaptopDispatcher
from skeleton.ai.runtime.operational_ai.laptop_runtime.run_once import generate_once
from skeleton.ai.runtime.operational_ai.laptop_runtime.source_guard import (
    LocalSourceFence, SourceFencedLaptopDispatcher,
)
from skeleton.testing.laptop_runtime_test_support import (
    FakeWorker, MODEL, TOKENIZER,
)


SOURCE = {
    "model_sha256": MODEL, "tokenizer_sha256": TOKENIZER,
    "manifest_sha256": "c" * 64, "archive_sha256": "d" * 64,
    "source_sha": "e" * 40, "installed_model_bytes": 2048,
    "installed_shard_count": 1,
}


def local_guard(worker=None, witness=None):
    worker = worker or FakeWorker()
    report = dict(SOURCE) if witness is None else witness
    with mock.patch(
        "skeleton.ai.runtime.operational_ai.laptop_runtime.source_guard.require_activated_source",
        return_value=report,
    ):
        guard = LocalSourceFence(
            worker, object(), tenant="local", subject="owner",
        )
    return worker, guard


class InstalledGGUFSourceGuardTests(unittest.TestCase):
    def test_expected_principal_source_snapshot_and_release_hold(self):
        worker, guard = local_guard()
        self.assertIs(guard.worker, worker)
        self.assertEqual(guard.identity.model_sha256, MODEL)
        self.assertEqual(guard.source, SOURCE)
        self.assertFalse(guard.release_certified)
        self.assertEqual(worker.generation_calls, 0)

    def test_inspector_source_must_match_model_and_be_typed(self):
        invalids = (
            {"model_sha256": "f" * 64},
            {"tokenizer_sha256": "f" * 64},
            {"manifest_sha256": "A" * 64},
            {"archive_sha256": "G" * 64},
            {"source_sha": "a" * 39},
            {"installed_model_bytes": True},
            {"installed_model_bytes": 0},
            {"installed_shard_count": False},
            {"installed_shard_count": 65537},
            {"unverified_rights": True},
        )
        for changed in invalids:
            with self.subTest(changed=changed):
                worker = FakeWorker()
                with mock.patch(
                    "skeleton.ai.runtime.operational_ai.laptop_runtime.source_guard.require_activated_source",
                    return_value={**SOURCE, **changed},
                ):
                    with self.assertRaises(ContractViolation):
                        LocalSourceFence(
                            worker, object(), tenant="local",
                            subject="owner",
                        )
                self.assertEqual(worker.generation_calls, 0)

    def test_wrong_owner_rejected_before_source_lookup(self):
        worker = FakeWorker()
        with mock.patch(
            "skeleton.ai.runtime.operational_ai.laptop_runtime.source_guard.require_activated_source",
        ) as source:
            with self.assertRaises(ContractViolation):
                LocalSourceFence(
                    worker, object(), tenant="another", subject="owner",
                )
            source.assert_not_called()

    def test_other_worker_cannot_use_existing_source_fence(self):
        worker, guard = local_guard()
        with self.assertRaises(ContractViolation):
            guard.assert_live(FakeWorker())
        self.assertEqual(worker.generation_calls, 0)

    def test_source_lease_loss_permanently_revokes_even_after_repair(self):
        worker, guard = local_guard()
        with mock.patch(
            "skeleton.ai.runtime.operational_ai.laptop_runtime.source_guard.require_activated_source",
            side_effect=[
                {**SOURCE, "installed_shard_count": 3},
                dict(SOURCE),
            ],
        ) as witness:
            with self.assertRaises(ContractViolation):
                guard.assert_live(worker)
            with self.assertRaisesRegex(ContractViolation, "permanently revoked"):
                guard.assert_live(worker)
            self.assertEqual(witness.call_count, 1)
        self.assertEqual(worker.generation_calls, 0)

    def test_nonfinite_and_fabricated_source_inspections_are_terminal(self):
        worker, guard = local_guard()
        for bad in (None, {}, "healthy", True):
            other, fence = local_guard()
            with self.subTest(bad=repr(bad)), mock.patch(
                "skeleton.ai.runtime.operational_ai.laptop_runtime.source_guard.require_activated_source",
                return_value=bad,
            ):
                with self.assertRaises(ContractViolation):
                    fence.assert_live(other)
                self.assertTrue(fence._revoked)
        self.assertFalse(guard._revoked)

    def test_identity_change_before_sqlite_read_permanently_revokes(self):
        worker, guard = local_guard()
        worker.spine.backend.model_digest = "f" * 64
        with self.assertRaises(ContractViolation):
            guard.assert_live(worker)
        worker.spine.backend.model_digest = MODEL
        with self.assertRaises(ContractViolation):
            guard.assert_live(worker)
        self.assertEqual(worker.generation_calls, 0)

    def test_inspector_exception_does_not_reveal_private_failure(self):
        worker, guard = local_guard()
        with mock.patch(
            "skeleton.ai.runtime.operational_ai.laptop_runtime.source_guard.require_activated_source",
            side_effect=ContractViolation("private source path"),
        ):
            with self.assertRaises(ContractViolation):
                guard.assert_live(worker)
        self.assertTrue(guard._revoked)

    def test_dispatcher_blocks_reads_and_model_effects_after_revocation(self):
        worker, guard = local_guard()
        with mock.patch(
            "skeleton.ai.runtime.operational_ai.laptop_runtime.source_guard.require_activated_source",
            return_value=dict(SOURCE),
        ) as witness:
            dispatcher = SourceFencedLaptopDispatcher(worker, guard)
            identity = dispatcher.dispatch("identity", {})
            self.assertEqual(identity["identity"]["model_sha256"], MODEL)
            worker.spine.backend.model_digest = "f" * 64
            with self.assertRaises(ContractViolation):
                dispatcher.dispatch("identity", {})
            self.assertTrue(guard._revoked)
        self.assertEqual(worker.generation_calls, 0)
        self.assertGreaterEqual(witness.call_count, 3)

    def test_dispatcher_checks_source_after_worker_status_read(self):
        worker, guard = local_guard()
        real_status = worker.status
        def drift():
            response = real_status()
            worker.spine.backend.model_digest = "f" * 64
            return response
        worker.status = drift
        with mock.patch(
            "skeleton.ai.runtime.operational_ai.laptop_runtime.source_guard.require_activated_source",
            return_value=dict(SOURCE),
        ):
            dispatcher = SourceFencedLaptopDispatcher(worker, guard)
            with self.assertRaises(ContractViolation):
                dispatcher.dispatch("status", {})
        self.assertTrue(guard._revoked)
        self.assertEqual(worker.generation_calls, 0)

    def test_protocol_is_denied_after_source_rejected(self):
        worker, guard = local_guard()
        with mock.patch(
            "skeleton.ai.runtime.operational_ai.laptop_runtime.source_guard.require_activated_source",
            return_value=dict(SOURCE),
        ):
            dispatcher = SourceFencedLaptopDispatcher(worker, guard)
            self.assertIsNotNone(dispatcher.protocol())
        worker.spine.backend.model_digest = "f" * 64
        with self.assertRaises(ContractViolation):
            dispatcher.protocol()
        self.assertTrue(guard._revoked)

    def test_untrusted_dispatcher_guard_does_not_gain_worker_access(self):
        with self.assertRaises(ContractViolation):
            SourceFencedLaptopDispatcher(FakeWorker(), object())

    def test_healthy_source_can_back_multiple_sequential_read_only_calls(self):
        worker, guard = local_guard()
        with mock.patch(
            "skeleton.ai.runtime.operational_ai.laptop_runtime.source_guard.require_activated_source",
            return_value=dict(SOURCE),
        ):
            dispatcher = SourceFencedLaptopDispatcher(worker, guard)
            for _ in range(9):
                result = dispatcher.dispatch("identity", {})
                self.assertEqual(result["identity"]["model_sha256"], MODEL)
        self.assertFalse(guard._revoked)
        self.assertEqual(worker.generation_calls, 0)

    def test_competing_request_is_denied_before_an_extra_source_probe(self):
        """Nonblocking admission must reject a second source inspection."""
        worker = FakeWorker()
        started, release = threading.Event(), threading.Event()
        actual_turn = worker.turn

        def blocked_turn(*args, **kwargs):
            started.set()
            if not release.wait(5):
                raise TimeoutError("synthetic blocked generation")
            return actual_turn(*args, **kwargs)

        worker.turn = blocked_turn
        responses = []
        with mock.patch(
            "skeleton.ai.runtime.operational_ai.laptop_runtime.source_guard.require_activated_source",
            return_value=dict(SOURCE),
        ) as inspection:
            guard = LocalSourceFence(worker, object(), tenant="local", subject="owner")
            dispatcher = SourceFencedLaptopDispatcher(worker, guard)
            session = dispatcher.dispatch("create", {})["session_id"]

            def issue_turn():
                try:
                    responses.append(dispatcher.dispatch("turn", {
                        "session_id": session, "request_id": "r_test",
                        "prompt": "private task",
                    }))
                except BaseException as exc:
                    responses.append(exc)

            running = threading.Thread(target=issue_turn, daemon=True)
            running.start()
            try:
                self.assertTrue(started.wait(5))
                prior_probes = inspection.call_count
                with self.assertRaises(ContractViolation):
                    dispatcher.dispatch("identity", {})
                with self.assertRaises(ContractViolation):
                    dispatcher.protocol()
                self.assertEqual(inspection.call_count, prior_probes)
            finally:
                release.set()
                running.join(5)
            self.assertFalse(running.is_alive())
            self.assertEqual(len(responses), 1)
            self.assertIsInstance(responses[0], dict)
            self.assertEqual(worker.generation_calls, 1)

    def test_source_revoked_during_sqlite_create_prevents_native_generation(self):
        worker = FakeWorker()
        original_create = worker.spine.create

        def change_model_after_create(session):
            created = original_create(session)
            worker.spine.backend.model_digest = "f" * 64
            return created

        worker.spine.create = change_model_after_create
        with mock.patch(
            "skeleton.ai.runtime.operational_ai.laptop_runtime.source_guard.require_activated_source",
            return_value=dict(SOURCE),
        ):
            guard = LocalSourceFence(worker, object(), tenant="local", subject="owner")
            dispatcher = SourceFencedLaptopDispatcher(worker, guard)
            with self.assertRaises(ContractViolation):
                generate_once(worker, "private task", dispatcher=dispatcher)
        self.assertTrue(guard._revoked)
        self.assertEqual(worker.generation_calls, 0)
        self.assertEqual(len(worker.spine.created), 1)

    def test_unfenced_or_foreign_dispatcher_refused_before_sqlite_creation(self):
        worker = FakeWorker()
        with self.assertRaises(ContractViolation):
            generate_once(worker, "private task", dispatcher=LaptopDispatcher(worker))
        self.assertFalse(worker.spine.created)
        with mock.patch(
            "skeleton.ai.runtime.operational_ai.laptop_runtime.source_guard.require_activated_source",
            return_value=dict(SOURCE),
        ):
            other = FakeWorker()
            guard = LocalSourceFence(other, object(), tenant="local", subject="owner")
            foreign = SourceFencedLaptopDispatcher(other, guard)
            with self.assertRaises(ContractViolation):
                generate_once(worker, "private task", dispatcher=foreign)
        self.assertFalse(worker.spine.created)


def flags(mode):
    return [
        "--model-root","/private/installed",
        "--state-dir","/private/sqlite",
        "--tenant","local","--subject","owner",
        "--mode",mode,
        *([] if mode == "serve" else ["--prompt-stdin"]),
        *(["--approve-real-acceptance"] if mode == "acceptance" else []),
    ]


class ShortWriter(StringIO):
    def write(self, data):
        super().write(data[:4])
        return 4


class FakeHTTPServer:
    def __init__(self, address, dispatcher, bearer):
        self.address = address
        self.dispatcher = dispatcher
        self.bearer = bearer
        self.server_port = address[1]
        self.calls = 0
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False
    def serve_forever(self, **options):
        self.calls += 1


class SourceBoundLaptopCLIOutputTests(unittest.TestCase):
    def execute(
        self, mode, *, task=b"private task", output=None,
        effect=None, worker=None,
    ):
        worker=worker or FakeWorker()
        stack=ExitStack()
        received=SimpleNamespace(buffer=BytesIO(task))
        out=output if output is not None else StringIO()
        err=StringIO()
        kwargs={"schema":"test-native-source","text":"example"}
        with (
            mock.patch(
                "skeleton.ai.runtime.operational_ai.laptop_runtime.cli.sys.stdin",received,
            ),
            mock.patch(
                "skeleton.ai.runtime.operational_ai.laptop_runtime.cli.sys.stdout",out,
            ),
            mock.patch(
                "skeleton.ai.runtime.operational_ai.laptop_runtime.cli.sys.stderr",err,
            ),
            mock.patch(
                "skeleton.ai.runtime.operational_ai.laptop_runtime.cli.activate_checked",
                return_value=(stack,worker,object()),
            ) as activated,
            mock.patch(
                "skeleton.ai.runtime.operational_ai.laptop_runtime.source_guard.require_activated_source",
                return_value=dict(SOURCE),
            ),
            mock.patch(
                "skeleton.ai.runtime.operational_ai.laptop_runtime.cli.generate_once",
                side_effect=effect if effect is not None else None,
                return_value=kwargs if effect is None else None,
            ) as native,
            mock.patch(
                "skeleton.ai.runtime.operational_ai.laptop_runtime.cli.run_first_turn_acceptance",
                return_value={
                    "model_sha256":MODEL,"tokenizer_sha256":TOKENIZER,
                    "output_sha256":"e"*64,"native_model_observed":True,
                    "release_certified":False,
                },
            ) as first,
            mock.patch(
                "skeleton.ai.runtime.operational_ai.laptop_runtime.cli.LaptopHTTPServer",
                FakeHTTPServer,
            ),
            mock.patch.dict(
                "skeleton.ai.runtime.operational_ai.laptop_runtime.cli.os.environ",
                {"SKELETON_LOCAL_AI_BEARER":"A"*64},
            ),
        ):
            code=main(flags(mode))
        return code,out.getvalue(),err.getvalue(),received,worker,activated,native,first

    def test_one_shot_publication_is_single_finite_source_checked_jsonl(self):
        code,out,err,reader,worker,activate,native,first=self.execute("once")
        self.assertEqual(code,0,err)
        self.assertEqual(json.loads(out)["status"],"real-offline-turn-committed")
        self.assertFalse(json.loads(out)["release_certified"])
        self.assertEqual(reader.buffer.read(),b"")
        self.assertEqual(worker.generation_calls,0)
        activate.assert_called_once()
        native.assert_called_once()
        first.assert_not_called()

    def test_approved_acceptance_publication_is_finite_source_bound(self):
        code,out,err,reader,worker,activate,native,first=self.execute("acceptance")
        self.assertEqual(code,0,err)
        data=json.loads(out)
        self.assertEqual(data["status"],"real-first-turn-native-replay-checked")
        self.assertFalse(data["release_certified"])
        native.assert_not_called()
        first.assert_called_once()
        self.assertIs(first.call_args.kwargs["require_real"],True)

    def test_loopback_server_dispatcher_has_live_guard(self):
        code,out,err,reader,worker,activate,native,first=self.execute("serve")
        self.assertEqual(code,0,err)
        self.assertEqual(json.loads(out)["status"],"native-loopback-listening")
        native.assert_not_called()
        first.assert_not_called()
        self.assertEqual(worker.generation_calls,0)

    def test_source_change_after_generating_refuses_output(self):
        worker=FakeWorker()
        def alter(*args, **kwargs):
            worker.spine.backend.model_digest = "f" * 64
            return {"answer":"sensitive result"}
        # A changed source after the one-shot model effect cannot publish
        # its output or return success, even if SQLite already committed.
        code,out,err,reader,_,_,_,_ = self.execute(
            "once",effect=alter,worker=worker,
        )
        self.assertEqual(code,2)
        self.assertFalse(out)
        self.assertNotIn("sensitive",err)

    def test_short_stdout_write_is_a_terminal_hold(self):
        code,out,err,reader,worker,activate,native,first=self.execute(
            "once",output=ShortWriter(),
        )
        self.assertEqual(code,2)
        self.assertEqual(len(out),4)
        native.assert_called_once()
        self.assertEqual(worker.generation_calls,0)


if __name__ == "__main__":
    unittest.main()
