"""Guard every private CLI response against installed-source drift.

The native worker and installed source are synthetic test doubles. Passing
these tests proves neither GGUF quality nor rights/hardware/release readiness.
"""
from __future__ import annotations

from io import StringIO
from unittest import mock
import json
import unittest

from skeleton.ai.runtime.operational_ai.laptop_runtime.publication import (
    NativePublicationHold, emit_native_jsonl,
)
from skeleton.ai.runtime.operational_ai.laptop_runtime.contracts import ContractViolation
from skeleton.jeeves.agent.native_source_fence import NativeSourceFence
from skeleton.testing.laptop_runtime_test_support import FakeWorker, MODEL, TOKENIZER
from skeleton.testing.test_jeeves_native_cli_timeout_and_redaction import (
    call_cli, cli_args,
)


SOURCE = {
    "model_sha256": MODEL, "tokenizer_sha256": TOKENIZER,
    "manifest_sha256": "c" * 64, "archive_sha256": "d" * 64,
    "source_sha": "e" * 40, "installed_model_bytes": 2048,
    "installed_shard_count": 1,
}


def prepared():
    worker = FakeWorker()
    with mock.patch(
        "skeleton.jeeves.agent.native_source_fence.require_activated_source",
        return_value=dict(SOURCE),
    ):
        fence = NativeSourceFence(
            worker, object(), expected_tenant="local",
            expected_subject="owner",
        )
    return worker, fence


class ShortWriter(StringIO):
    def write(self, text):
        super().write(text[:4])
        return 4


class ReportedWriter(StringIO):
    def __init__(self, value):
        super().__init__()
        self.value = value
    def write(self, text):
        return self.value


class NativePublicationCustodyTests(unittest.TestCase):
    def test_native_chat_cli_uses_one_bounded_json_record(self):
        code, out, err, *_ = call_cli(cli_args(), prompt=b"private request")
        self.assertEqual(code, 0, err)
        row = json.loads(out)
        self.assertEqual(row["status"], "native-chat-committed")
        self.assertEqual(row["text"], "synthetic answer")
        self.assertNotIn("private request", out)
        self.assertNotIn("private request", err)

    def test_complete_source_bound_frame_reports_actual_utf8_bytes(self):
        worker, fence = prepared()
        out = StringIO()
        data = {"schema":"native.test.v1", "answer":"🦊ê"}
        with mock.patch(
            "skeleton.jeeves.agent.native_source_fence.require_activated_source",
            return_value=dict(SOURCE),
        ) as source:
            amount = emit_native_jsonl(worker, fence, data, out)
        self.assertEqual(amount, len(out.getvalue().encode("utf8")))
        self.assertEqual(json.loads(out.getvalue()), data)
        self.assertEqual(source.call_count, 3)
        self.assertEqual(worker.generation_calls, 0)

    def test_oversized_private_data_never_reaches_text_writer(self):
        worker, fence = prepared()
        out = StringIO()
        with mock.patch(
            "skeleton.jeeves.agent.native_source_fence.require_activated_source",
            return_value=dict(SOURCE),
        ):
            with self.assertRaises(NativePublicationHold):
                emit_native_jsonl(
                    worker, fence, {"answer":"PRIVATE"*128}, out,
                    maximum_result_bytes=32,
                )
        self.assertEqual(out.getvalue(), "")
        self.assertEqual(worker.generation_calls, 0)

    def test_bad_ceiling_values_refused_without_inspecting_source(self):
        worker, fence = prepared()
        for value in (None, True, False, 0, -1, "1024", 1.0, 16777217):
            with self.subTest(value=value):
                with mock.patch(
                    "skeleton.jeeves.agent.native_source_fence.require_activated_source",
                ) as source:
                    with self.assertRaises(NativePublicationHold):
                        emit_native_jsonl(
                            worker, fence, {"answer":"private"}, StringIO(),
                            maximum_result_bytes=value,
                        )
                    source.assert_not_called()

    def test_nonfinite_number_is_not_a_fabricated_native_record(self):
        worker, fence = prepared()
        for value in (float("inf"), float("-inf"), float("nan")):
            out = StringIO()
            with mock.patch(
                "skeleton.jeeves.agent.native_source_fence.require_activated_source",
                return_value=dict(SOURCE),
            ):
                with self.assertRaises(NativePublicationHold):
                    emit_native_jsonl(worker, fence, {"answer":value}, out)
            self.assertFalse(out.getvalue())

    def test_lone_surrogate_never_escapes_jsonl(self):
        worker, fence = prepared()
        out = StringIO()
        with mock.patch(
            "skeleton.jeeves.agent.native_source_fence.require_activated_source",
            return_value=dict(SOURCE),
        ):
            with self.assertRaises(NativePublicationHold):
                emit_native_jsonl(worker, fence, {"answer":"\ud800"}, out)
        self.assertEqual(out.getvalue(), "")

    def test_drift_during_serialization_blocks_before_disclosure(self):
        worker, fence = prepared()
        out = StringIO()
        real = json.dumps
        def drift(*args, **kwargs):
            worker.spine.backend.model_digest = "f"*64
            return real(*args, **kwargs)
        with (
            mock.patch(
                "skeleton.jeeves.agent.native_source_fence.require_activated_source",
                return_value=dict(SOURCE),
            ),
            mock.patch(
                "skeleton.ai.runtime.operational_ai.laptop_runtime.publication.json.dumps",
                side_effect=drift,
            ),
        ):
            with self.assertRaises(ContractViolation):
                emit_native_jsonl(worker, fence, {"answer":"private"}, out)
        self.assertEqual(out.getvalue(), "")

    def test_revoked_source_at_second_check_never_writes(self):
        worker, fence = prepared()
        out = StringIO()
        with mock.patch(
            "skeleton.jeeves.agent.native_source_fence.require_activated_source",
            side_effect=[
                dict(SOURCE), {**SOURCE, "installed_shard_count": 2},
            ],
        ) as source:
            with self.assertRaises(ContractViolation):
                emit_native_jsonl(worker, fence, {"answer":"private"}, out)
        self.assertEqual(source.call_count, 2)
        self.assertFalse(out.getvalue())

    def test_expired_source_at_first_check_never_serializes(self):
        worker, fence = prepared()
        out = StringIO()
        with mock.patch(
            "skeleton.jeeves.agent.native_source_fence.require_activated_source",
            side_effect=ContractViolation("synthetic expired lease"),
        ):
            with self.assertRaises(ContractViolation):
                emit_native_jsonl(worker, fence, {"answer":"private"}, out)
        self.assertFalse(out.getvalue())

    def test_short_write_is_terminal_with_no_new_native_call(self):
        worker, fence = prepared()
        out = ShortWriter()
        with mock.patch(
            "skeleton.jeeves.agent.native_source_fence.require_activated_source",
            return_value=dict(SOURCE),
        ):
            with self.assertRaises(NativePublicationHold):
                emit_native_jsonl(worker, fence, {"answer":"private"}, out)
        self.assertEqual(len(out.getvalue()), 4)
        self.assertEqual(worker.generation_calls, 0)

    def test_invalid_character_write_counts_are_refused(self):
        for count in (None, True, False, 0, -1, "complete"):
            worker, fence = prepared()
            with self.subTest(count=count), mock.patch(
                "skeleton.jeeves.agent.native_source_fence.require_activated_source",
                return_value=dict(SOURCE),
            ):
                with self.assertRaises(NativePublicationHold):
                    emit_native_jsonl(
                        worker, fence, {"answer":"secret"},
                        ReportedWriter(count),
                    )
            self.assertEqual(worker.generation_calls, 0)

    def test_nonmapping_and_untrusted_streams_refused_before_io(self):
        worker, fence = prepared()
        for record in (None, [], "private", True):
            with self.subTest(record=repr(record)), self.assertRaises(NativePublicationHold):
                emit_native_jsonl(worker, fence, record, StringIO())
        with self.assertRaises(NativePublicationHold):
            emit_native_jsonl(worker, fence, {"answer":"secret"}, object())

    def test_postwrite_source_revocation_cannot_report_success(self):
        worker, fence = prepared()
        class MutatingWriter(StringIO):
            def write(self, text):
                worker.spine.backend.model_digest = "f"*64
                return super().write(text)
        out = MutatingWriter()
        with mock.patch(
            "skeleton.jeeves.agent.native_source_fence.require_activated_source",
            return_value=dict(SOURCE),
        ):
            with self.assertRaises(ContractViolation):
                emit_native_jsonl(worker, fence, {"answer":"private"}, out)
        self.assertGreater(len(out.getvalue()), 0)
        self.assertEqual(worker.generation_calls, 0)
        # An already-written result cannot be retracted. CLI must hold and
        # must not claim success or retry any native model effect.

    def test_unsupported_guard_and_unserializable_record_fail_closed(self):
        worker, fence = prepared()
        with self.assertRaises(NativePublicationHold):
            emit_native_jsonl(worker, object(), {"answer":"private"}, StringIO())
        with mock.patch(
            "skeleton.jeeves.agent.native_source_fence.require_activated_source",
            return_value=dict(SOURCE),
        ):
            with self.assertRaises(NativePublicationHold):
                emit_native_jsonl(worker, fence, {"answer": object()}, StringIO())


if __name__ == "__main__":
    unittest.main()
