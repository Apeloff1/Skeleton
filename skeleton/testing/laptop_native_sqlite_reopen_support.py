"""Real descriptor-anchored SQLite reopen fixture, with a TEST-ONLY model.

Every new worker owns a newly opened production SpineDatabase, SessionGate,
ExecutionSpine and SupervisedAI. The backend merely emits fixed deterministic
tokens; no test here can assert an installed GGUF, source rights, physical
device, Windows/WSL2 readiness, or release certification.

Only explicit unittest patches bypass the model installer in these tests.
The application production path always calls activate_checked.
"""
from __future__ import annotations

from contextlib import ExitStack, contextmanager
from pathlib import Path
import os
import tempfile
from unittest import mock

from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.contracts import (
    Identity, SpineLimits,
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
from skeleton.ai.runtime.operational_ai.laptop_runtime import (
    first_turn_acceptance, cold_reopen_acceptance,
)
from hashlib import sha256
from skeleton.ai.runtime.operational_ai.model.native import Generated

MODEL = "a" * 64
TOKENIZER = "b" * 64
ANSWER = '{"answer":"synthetic SQLite replay only","confidence":0.5,"claims":[],"unresolved":[],"memory_candidates":[]}'


class SyntheticallyGenerated:
    """TEST ONLY. No installed GGUF or native inference is executed."""

    model_digest = MODEL
    tokenizer_digest = TOKENIZER

    def __init__(self, *, post_reservation_failure=False):
        self.calls = 0
        self.fail = post_reservation_failure

    def count_tokens(self, messages):
        return 48

    def generate(self, messages, *, max_output_tokens, seed, temperature):
        self.calls += 1
        if self.fail:
            raise RuntimeError("synthetic backend aborted after durable reservation")
        return Generated(
            text=ANSWER, prompt_tokens=48, generated_tokens=16,
            output_digest=sha256(ANSWER.encode("utf-8")).hexdigest(),
            model_digest=self.model_digest,
            tokenizer_digest=self.tokenizer_digest,
            finish_reason="stop",
        )


SOURCE = {
    "model_sha256": MODEL,
    "tokenizer_sha256": TOKENIZER,
    "manifest_sha256": "c" * 64,
    "archive_sha256": "d" * 64,
    "source_sha": "e" * 40,
    "installed_model_bytes": 2048,
    "installed_shard_count": 1,
}


class RealSQLiteSyntheticGGUFRig:
    """Use actual SQLite transactions across independently closed workers."""

    def __init__(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.model_root = Path("/source-only-not-a-real-installed-gguf")
        self.events = []
        self.backends = []
        self.workers = []
        self.actual_stacks = []
        self.calls = 0
        self.second_owner = None
        self.first_backend_fails = False
        self.after_first_close = None
        self.first_source = None
        self.second_source = None

    @property
    def args(self):
        return dict(
            model_root=self.model_root, state_dir=self.root,
            tenant="local", subject="operator",
            prompt="  real SQLite, synthetic model \n",
            approved=True,
        )

    def close(self):
        # Defensive cleanup if the acceptance test aborts mid-activation.
        for stack in reversed(self.actual_stacks):
            stack.close()
        self.temp.cleanup()

    def activate(self, **options):
        assert options["state_dir"] == self.root
        assert options["model_root"] == self.model_root
        assert options["tenant"] == "local"
        assert options["subject"] == "operator"
        self.calls += 1
        number = self.calls
        if number > 2:
            raise AssertionError("third native worker is never allowed")
        if number == 2 and "closed_1" not in self.events:
            raise AssertionError("cannot reopen before fully closing first SQLite")
        self.events.append(f"activated_{number}")
        stack = ExitStack()
        # Register first so the marker is written AFTER DB + flock close.
        stack.callback(lambda n=number: self._on_close(n))
        try:
            database = stack.enter_context(SpineDatabase(self.root))
            gate = stack.enter_context(SessionGate(self.root))
            backend = SyntheticallyGenerated(
                post_reservation_failure=(
                    self.first_backend_fails and number == 1
                )
            )
            principal = (
                self.second_owner
                if number == 2 and self.second_owner is not None
                else Identity("local", "operator", MODEL, TOKENIZER)
            )
            spine = ExecutionSpine(
                db=database, session_gate=gate, backend=backend,
                identity=principal, limits=SpineLimits(
                    input_bytes=32768, response_bytes=131072,
                    max_output_tokens=128, context_tokens=4096,
                ),
            )
            worker = SupervisedAI(spine)
            self.backends.append(backend)
            self.workers.append(worker)
            self.actual_stacks.append(stack)
            return stack, worker, object()
        except BaseException:
            stack.close()
            raise

    def _on_close(self, number):
        self.events.append(f"closed_{number}")
        if number == 1 and self.after_first_close is not None:
            self.after_first_close()

    @contextmanager
    def patch(self):
        first = self.first_source if self.first_source is not None else SOURCE
        second = self.second_source if self.second_source is not None else SOURCE
        with (
            mock.patch.object(
                cold_reopen_acceptance, "activate_checked",
                side_effect=self.activate,
            ) as activation,
            mock.patch.object(
                first_turn_acceptance, "require_activated_source",
                return_value=dict(first),
            ) as first_witness,
            mock.patch.object(
                cold_reopen_acceptance, "require_activated_source",
                return_value=dict(second),
            ) as reopened_witness,
        ):
            yield activation, first_witness, reopened_witness

    def query_one(self, sql, params=()):
        with SpineDatabase(self.root, readonly=True) as db:
            with db.snapshot() as conn:
                return conn.execute(sql, params).fetchone()

    def mutate(self, sql, params=()):
        with SpineDatabase(self.root) as db:
            with db.transaction() as conn:
                conn.execute(sql, params)


__all__ = ["RealSQLiteSyntheticGGUFRig", "MODEL", "TOKENIZER", "SOURCE"]
