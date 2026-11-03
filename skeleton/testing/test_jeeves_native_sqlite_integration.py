"""Real SQLite execution-spine integration, with a SYNTHETIC tokenizer/backend.

These tests use the actual protected SQLite storage, session flock fence,
quota supervisor, transaction receipt, outbox, replay and Jeeves adapter.
The only simulated component is generation: tests do not claim physical GGUF
model, native device, model rights or release qualification.
"""
from __future__ import annotations

from hashlib import sha256
import os
import tempfile
from pathlib import Path
import sys
import unittest

from skeleton.ai.runtime.operational_ai.model.native import Generated
from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.contracts import (
    Busy, Conflict, Identity, IntegrityFailure, SpineLimits,
)
from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.database import (
    SpineDatabase,
)
from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.lease import (
    SessionGate,
)
from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.coordinator import (
    ExecutionSpine,
)
from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.supervisor import (
    SupervisedAI,
)
from skeleton.jeeves.agent.native_chat import NativeJeevesChat, NativeChatHold
from skeleton.jeeves.agent.native_provider import NativeJeevesProvider
from skeleton.jeeves.agent.types import ModelMessage, ModelRequest


MODEL = "a" * 64
TOKENIZER = "b" * 64
ANSWER = '{"answer":"synthetic fixed evidence","confidence":0.5,"claims":[],"unresolved":[],"memory_candidates":[]}'


class SyntheticallyGenerated:
    """SYNTHETIC test-only backend; never permitted as deployment evidence."""

    model_digest = MODEL
    tokenizer_digest = TOKENIZER

    def __init__(self, *, answer=ANSWER, post_reservation_failure=False):
        self.answer = answer
        self.calls = 0
        self.token_counts = 0
        self.fail = post_reservation_failure

    def count_tokens(self, messages):
        self.token_counts += 1
        return 48

    def generate(self, messages, *, max_output_tokens, seed, temperature):
        self.calls += 1
        if self.fail:
            raise RuntimeError("synthetic backend aborted after durable reservation")
        return Generated(
            text=self.answer,
            prompt_tokens=48,
            generated_tokens=16,
            output_digest=sha256(self.answer.encode("utf-8")).hexdigest(),
            model_digest=self.model_digest,
            tokenizer_digest=self.tokenizer_digest,
            finish_reason="stop",
        )


@unittest.skipUnless(os.name == "posix" and Path("/proc/self/fd").is_dir(),
                     "descriptor-anchored SQLite requires Linux")
class TestNativeJeevesRealSqliteBoundary(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = self.tmp.name
        self.identity = Identity("local", "operator", MODEL, TOKENIZER)
        self.limits = SpineLimits(
            input_bytes=32768,
            response_bytes=131072,
            max_output_tokens=128,
            context_tokens=4096,
        )
        self.backend = SyntheticallyGenerated()
        self._open(self.backend)
        self.addCleanup(self._cleanup_spine)

    def _cleanup_spine(self):
        if getattr(self, "gate", None) is not None:
            self.gate.close()
            self.gate = None
        if getattr(self, "db", None) is not None:
            self.db.close()
            self.db = None

    def _open(self, backend=None, *, principal=None):
        self.db = SpineDatabase(self.root)
        self.gate = SessionGate(self.root)
        self.backend = backend or SyntheticallyGenerated()
        self.spine = ExecutionSpine(
            db=self.db,
            session_gate=self.gate,
            backend=self.backend,
            identity=principal or self.identity,
            limits=self.limits,
        )
        self.worker = SupervisedAI(self.spine)

    def _cold_open(self, backend=None, *, principal=None):
        self._cleanup_spine()
        self._open(backend, principal=principal)

    def _request(self, *, request_id="r1", text="Question"):
        return ModelRequest(
            request_id=request_id,
            messages=(ModelMessage("system", "Be concise."),
                      ModelMessage("user", text)),
            max_tokens=128,
        )

    def test_one_native_chat_commits_real_sqlite_and_outbox(self):
        chat = NativeJeevesChat(self.worker)
        receipt = chat.turn("hello", request_id="request_A")
        self.assertEqual(receipt.text, ANSWER)
        self.assertEqual(self.backend.calls, 1)
        self.assertEqual(receipt.prompt_tokens, 48)
        self.assertEqual(receipt.generated_tokens, 16)
        with self.db.snapshot() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM turns").fetchone()[0], 1)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM outbox").fetchone()[0], 1)
            self.assertEqual(conn.execute("SELECT state FROM requests").fetchone()[0], "committed")
        self.assertEqual(len(chat.history()), 2)

    def test_no_second_generation_for_committed_request(self):
        chat = NativeJeevesChat(self.worker)
        first = chat.turn("hello", request_id="request_B")
        second = chat.turn("hello", request_id="request_B")
        self.assertEqual(first.output_sha256, second.output_sha256)
        self.assertTrue(second.replayed)
        self.assertEqual(self.backend.calls, 1)
        self.assertEqual(len(chat.history()), 2)

    def test_cold_reopen_requires_no_synthetic_generation(self):
        first_chat = NativeJeevesChat(self.worker)
        first = first_chat.turn("hello", request_id="request_C")
        old_session = first_chat.session_id
        self._cold_open(SyntheticallyGenerated())
        reopened = NativeJeevesChat(self.worker, session_id=old_session)
        replay = reopened.turn("hello", request_id="request_C")
        self.assertTrue(replay.replayed)
        self.assertEqual(replay.output_sha256, first.output_sha256)
        self.assertEqual(self.backend.calls, 0)
        self.assertEqual(len(reopened.history()), 2)

    def test_cold_reopen_can_continue_same_session(self):
        chat = NativeJeevesChat(self.worker)
        chat.turn("first", request_id="request_D1")
        session = chat.session_id
        self._cold_open(SyntheticallyGenerated())
        chat = NativeJeevesChat(self.worker, session_id=session)
        result = chat.turn("second", request_id="request_D2")
        self.assertEqual(result.session_id, session)
        self.assertEqual(self.backend.calls, 1)
        self.assertEqual(len(chat.history()), 4)
        with self.db.snapshot() as conn:
            self.assertEqual(conn.execute(
                "SELECT revision FROM sessions WHERE session=?",
                (session,),
            ).fetchone()[0], 2)

    def test_foreign_subject_cannot_resume_original_transcript(self):
        chat = NativeJeevesChat(self.worker)
        chat.turn("first", request_id="request_E")
        session = chat.session_id
        foreign = Identity("local", "other_operator", MODEL, TOKENIZER)
        self._cold_open(SyntheticallyGenerated(), principal=foreign)
        with self.assertRaises(Conflict):
            NativeJeevesChat(self.worker, session_id=session)
        self.assertEqual(self.backend.calls, 0)

    def test_changed_prompt_under_same_request_cannot_regenerate(self):
        chat = NativeJeevesChat(self.worker)
        chat.turn("original", request_id="request_F")
        with self.assertRaises(Conflict):
            chat.turn("malicious changed input", request_id="request_F")
        self.assertEqual(self.backend.calls, 1)

    def test_pending_unknown_backend_failure_persists_across_cold_restart(self):
        self.backend.fail = True
        chat = NativeJeevesChat(self.worker)
        session = chat.session_id
        with self.assertRaises(RuntimeError):
            chat.turn("ambiguous native execution", request_id="request_G")
        self.assertEqual(self.backend.calls, 1)
        with self.db.snapshot() as conn:
            self.assertEqual(conn.execute("SELECT state FROM requests").fetchone()[0], "pending")
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM turns").fetchone()[0], 0)
        self._cold_open(SyntheticallyGenerated())
        restored = NativeJeevesChat(self.worker, session_id=session)
        with self.assertRaises(Busy):
            restored.turn("ambiguous native execution", request_id="request_G")
        self.assertEqual(self.backend.calls, 0)

    def test_durable_response_tamper_is_refused(self):
        chat = NativeJeevesChat(self.worker)
        chat.turn("hello", request_id="request_H")
        with self.db.transaction() as conn:
            conn.execute("UPDATE turns SET response=?", (b"tampered!",))
        with self.assertRaises(IntegrityFailure):
            chat.turn("hello", request_id="request_H")
        self.assertEqual(self.backend.calls, 1)

    def test_durable_receipt_tamper_is_refused(self):
        chat = NativeJeevesChat(self.worker)
        chat.turn("hello", request_id="request_I")
        with self.db.transaction() as conn:
            conn.execute("UPDATE turns SET receipt_sha256=?", ("f" * 64,))
        with self.assertRaises(IntegrityFailure):
            chat.turn("hello", request_id="request_I")
        self.assertEqual(self.backend.calls, 1)

    def test_model_provider_uses_same_transactional_spine(self):
        provider = NativeJeevesProvider(self.worker)
        req = self._request(request_id="model_A")
        response = provider.complete(req)
        self.assertEqual(response.provider, "jeeves_native")
        self.assertEqual(response.content, ANSWER)
        self.assertTrue(response.metadata["authoritative_commit"])
        self.assertEqual(self.backend.calls, 1)
        self.assertFalse(response.cached)
        self.assertEqual(
            NativeJeevesProvider(self.worker).complete(req).content, ANSWER,
        )
        self.assertEqual(self.backend.calls, 1)

    def test_model_response_no_fallback_after_uncertainty(self):
        self.backend.fail = True
        provider = NativeJeevesProvider(self.worker)
        with self.assertRaises(RuntimeError):
            provider.complete(self._request(request_id="model_B"))
        self.assertEqual(self.backend.calls, 1)
        with self.assertRaises(Busy):
            provider.complete(self._request(request_id="model_B"))
        self.assertEqual(self.backend.calls, 1)

    def test_bad_model_digest_fails_identity_gate(self):
        bad = SyntheticallyGenerated()
        bad.model_digest = "f" * 64
        with self.assertRaises(Exception):
            ExecutionSpine(
                db=self.db, session_gate=self.gate, backend=bad,
                identity=self.identity, limits=self.limits,
            )

    def test_closed_sqlite_session_denies_new_native_turn(self):
        chat = NativeJeevesChat(self.worker)
        result = chat.turn("first", request_id="request_J")
        self.assertTrue(chat.close())
        self._cold_open(SyntheticallyGenerated())
        other = NativeJeevesChat(self.worker, session_id=result.session_id)
        with self.assertRaises(Conflict):
            other.turn("second", request_id="request_K")
        self.assertEqual(self.backend.calls, 0)


if __name__ == "__main__":
    unittest.main()
