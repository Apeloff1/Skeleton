"""Test source-bound REPL publication without a real GGUF model.

The mock source inspector and deterministic native worker are not physical
device or rights evidence. No real llama.cpp process is created here.
"""
from __future__ import annotations

from io import BytesIO, StringIO
from unittest import mock
import json
import unittest

from skeleton.ai.runtime.operational_ai.laptop_runtime.contracts import (
    ContractViolation,
)
from skeleton.jeeves.agent.native_chat import NativeJeevesChat
from skeleton.jeeves.agent.native_repl import NativeJeevesRepl, NativeReplHold
from skeleton.jeeves.agent.native_source_fence import NativeSourceFence
from skeleton.testing.test_jeeves_native_provider_bridge import (
    SimulatedWorker, MODEL, TOKENIZER,
)

SOURCE = {
    "model_sha256": MODEL, "tokenizer_sha256": TOKENIZER,
    "manifest_sha256": "c" * 64,
    "archive_sha256": "d" * 64, "source_sha": "e" * 40,
    "installed_model_bytes": 1024, "installed_shard_count": 1,
}


def built():
    worker = SimulatedWorker()
    chat = NativeJeevesChat(worker)
    with mock.patch(
        "skeleton.jeeves.agent.native_source_fence.require_activated_source",
        return_value=dict(SOURCE),
    ):
        fence = NativeSourceFence(
            worker, object(), expected_tenant="local",
            expected_subject="operator",
        )
        repl = NativeJeevesRepl(chat, source_fence=fence)
    return worker, chat, repl


class LiveGGUFReplPublicationTests(unittest.TestCase):
    def test_live_source_rechecked_before_status_and_turn_disclosure(self):
        worker, chat, repl = built()
        out = StringIO()
        with mock.patch(
            "skeleton.jeeves.agent.native_source_fence.require_activated_source",
            return_value=dict(SOURCE),
        ) as witness:
            code = repl.serve(BytesIO(b":status\nhello\n:quit\n"), out)
        self.assertEqual(code, 0)
        self.assertGreater(witness.call_count, 4)
        records = [json.loads(x) for x in out.getvalue().splitlines()]
        self.assertEqual(records[0]["status"], "jeeves-native-chat-ready")
        self.assertEqual(records[1]["status"], "ready")
        self.assertEqual(records[2]["status"], "committed-native-chat-turn")
        self.assertEqual(records[-1]["status"], "session-preserved-for-resume")
        self.assertEqual(worker.spine.generations, 1)
        self.assertFalse(records[2]["release_certified"])

    def test_model_swapped_after_native_call_never_publishes_text(self):
        worker, chat, repl = built()
        original = chat.turn
        def change_after_turn(*args, **kwargs):
            result = original(*args, **kwargs)
            worker.spine.backend.model_digest = "f" * 64
            return result
        out = StringIO()
        with (
            mock.patch.object(chat, "turn", side_effect=change_after_turn),
            mock.patch(
                "skeleton.jeeves.agent.native_source_fence.require_activated_source",
                return_value=dict(SOURCE),
            ),
        ):
            code = repl.serve(BytesIO(b"private model prompt\nsecond\n"), out)
        self.assertEqual(code, 2)
        lines = [json.loads(x) for x in out.getvalue().splitlines()]
        self.assertEqual(lines[0]["status"], "jeeves-native-chat-ready")
        self.assertEqual(lines[-1]["status"], "held")
        self.assertNotIn("committed-native-chat-turn", out.getvalue())
        self.assertNotIn(worker.spine.generated_text, out.getvalue())
        self.assertNotIn("private model prompt", out.getvalue())
        self.assertEqual(worker.spine.generations, 1)
        self.assertTrue(repl._terminated)

    def test_history_source_swap_never_exports_private_messages(self):
        worker, chat, repl = built()
        original = chat.history
        def change_after_history(*args, **kwargs):
            result = original(*args, **kwargs)
            worker.spine.backend.tokenizer_digest = "f" * 64
            return result
        out = StringIO()
        with (
            mock.patch.object(chat, "history", side_effect=change_after_history),
            mock.patch(
                "skeleton.jeeves.agent.native_source_fence.require_activated_source",
                return_value=dict(SOURCE),
            ),
        ):
            code = repl.serve(BytesIO(b":history\n"), out)
        self.assertEqual(code, 2)
        self.assertEqual(worker.spine.generations, 0)
        self.assertNotIn("explicit-history-export", out.getvalue())
        self.assertIn('"status":"held"', out.getvalue())
        self.assertTrue(repl._terminated)

    def test_repl_refuses_other_worker_fence_before_reading_prompts(self):
        worker, chat, repl = built()
        different_worker, _, _ = built()
        with mock.patch(
            "skeleton.jeeves.agent.native_source_fence.require_activated_source",
            return_value=dict(SOURCE),
        ):
            foreign = NativeSourceFence(
                different_worker, object(), expected_tenant="local",
                expected_subject="operator",
            )
            with self.assertRaisesRegex(ContractViolation, "different native worker"):
                NativeJeevesRepl(chat, source_fence=foreign)
        self.assertEqual(worker.spine.generations, 0)

    def test_repl_rejects_forged_source_guard_type(self):
        worker = SimulatedWorker()
        chat = NativeJeevesChat(worker)
        with self.assertRaises(NativeReplHold):
            NativeJeevesRepl(chat, source_fence=mock.Mock())
        self.assertEqual(worker.spine.generations, 0)

    def test_native_lease_revoked_before_first_status_never_claims_ready(self):
        worker, chat, repl = built()
        out = StringIO()
        reader = BytesIO(b"private prompt\n")
        with mock.patch(
            "skeleton.jeeves.agent.native_source_fence.require_activated_source",
            side_effect=ContractViolation("native capacity lease revoked"),
        ):
            with self.assertRaisesRegex(ContractViolation, "lease revoked"):
                repl.serve(reader, out)
        self.assertFalse(out.getvalue())
        self.assertEqual(reader.tell(), 0)
        self.assertEqual(worker.spine.generations, 0)

    def test_unchanged_model_but_source_archive_swapped_blocks_history(self):
        worker, chat, repl = built()
        out = StringIO()
        with mock.patch(
            "skeleton.jeeves.agent.native_source_fence.require_activated_source",
            return_value={**SOURCE, "archive_sha256": "f" * 64},
        ):
            with self.assertRaises(ContractViolation):
                repl.serve(BytesIO(b":history\n"), out)
        self.assertFalse(out.getvalue())
        self.assertEqual(worker.spine.generations, 0)


if __name__ == "__main__":
    unittest.main()
