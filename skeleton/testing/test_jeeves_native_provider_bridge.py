"""SIMULATED source qualification only; not real GGUF/device/release evidence."""
from __future__ import annotations

from hashlib import sha256
from types import SimpleNamespace
import unittest

from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.contracts import (
    Conflict, Identity, SpineLimits,
)
from skeleton.jeeves.agent.native_provider import NativeJeevesProvider, native_provider_router
from skeleton.jeeves.agent.native_receipt_boundary import NativeReceiptError
from skeleton.jeeves.agent.native_runtime import NativeJeevesRuntime, NativeRuntimeHold
from skeleton.jeeves.agent.native_readiness import inspect_native_jeeves
from skeleton.jeeves.agent.native_schema_boundary import NativeSchemaError
from skeleton.jeeves.agent.provider import ProviderExhausted, ProviderError
from skeleton.jeeves.agent.runtime import AgentConfig, RunInputs
from skeleton.jeeves.agent.types import Budget, Goal, ModelMessage, ModelRequest

MODEL = "a" * 64
TOKENIZER = "b" * 64


class SimulatedSpine:
    """A deliberately narrow in-memory test fake, not SQLite or llama.cpp."""

    def __init__(self):
        self.identity = Identity("local", "operator", MODEL, TOKENIZER)
        self.backend = SimpleNamespace(model_digest=MODEL, tokenizer_digest=TOKENIZER)
        self.limits = SpineLimits(
            input_bytes=32768, response_bytes=131072,
            max_output_tokens=128, context_tokens=1024,
        )
        self.sessions = set()
        self.closed_sessions = set()
        self.turns = {}
        self.pending = set()
        self.generations = 0
        self.generated_text = '{"answer":"ok","confidence":1,"refs":[]}'
        self.fail_uncertain = False
        self.return_without_commit = False
        self.tamper_committed = False
        self.db = object()

    def create(self, session):
        if session in self.sessions:
            raise Conflict("already allocated")
        self.sessions.add(session)
        return session

    def history(self, session):
        if session not in self.sessions:
            raise Conflict("unknown session")
        result = []
        for (stored_session, _), row in self.turns.items():
            if stored_session == session:
                result.extend((
                    {"role": "user", "content": row["request_prompt"]},
                    {"role": "assistant", "content": row["result"]["text"]},
                ))
        return tuple(result)

    def close(self, session):
        if session not in self.sessions:
            raise Conflict("unknown session")
        if session in self.closed_sessions:
            return False
        self.closed_sessions.add(session)
        return True

    def replay(self, session, request_id, prompt, *, seed, temperature):
        if session not in self.sessions:
            raise Conflict("unknown session")
        row = self.turns.get((session, request_id))
        if row is None:
            return None
        if row["request_prompt"] != prompt:
            raise Conflict("request ID reused with another prompt")
        result = dict(row["result"])
        result["replayed"] = True
        if self.tamper_committed:
            result["text"] = "tampered outside ledger"
        return result

    def turn(self, session, request_id, prompt, *, seed, temperature):
        if session not in self.sessions or session in self.closed_sessions:
            raise Conflict("unknown or closed session")
        key = (session, request_id)
        if key in self.pending:
            raise Conflict("native effect pending and uncertain")
        self.pending.add(key)
        self.generations += 1
        if self.fail_uncertain:
            raise RuntimeError("native execution uncertain")
        text = self.generated_text
        result = {
            "session": session, "request_id": request_id,
            "model_sha256": MODEL, "tokenizer_sha256": TOKENIZER,
            "output_sha256": sha256(text.encode()).hexdigest(),
            "text": text, "prompt_tokens": 32,
            "generated_tokens": 40, "finish_reason": "stop",
            "replayed": False,
        }
        if not self.return_without_commit:
            self.turns[key] = {"request_prompt": prompt, "result": dict(result)}
            self.pending.remove(key)
        # A worker that produces output without a canonical commit leaves
        # the durable request pending, not safe for another generation.
        return result


class SimulatedWorker:
    def __init__(self, spine=None):
        self.spine = spine or SimulatedSpine()

    def turn(self, *args, **kwargs):
        return self.spine.turn(*args, **kwargs)


def request(text="respond", *, request_id="jeeves1", schema=None, max_tokens=128):
    return ModelRequest(
        request_id=request_id,
        messages=(ModelMessage("system", "You are Jeeves."),
                  ModelMessage("user", text)),
        max_tokens=max_tokens, response_schema=schema,
    )


class TestNativeProviderWiring(unittest.TestCase):
    def setUp(self):
        self.worker = SimulatedWorker()
        self.provider = NativeJeevesProvider(self.worker)

    def test_exact_principal_and_model(self):
        self.assertEqual(self.provider.identity.model_sha256, MODEL)
        self.assertEqual(self.provider.identity.subject, "operator")
        self.assertTrue(self.provider.available())
        self.assertEqual(self.provider.name, "jeeves_native")

    def test_one_generation_then_durable_replay(self):
        r = request()
        first = self.provider.complete(r)
        self.assertEqual(first.content, self.worker.spine.generated_text)
        self.assertEqual(self.worker.spine.generations, 1)
        self.assertEqual(first.prompt_tokens, 32)
        self.assertFalse(first.cached)
        again = NativeJeevesProvider(self.worker).complete(r)
        self.assertEqual(again.content, first.content)
        self.assertEqual(self.worker.spine.generations, 1)
        self.assertTrue(again.cached)

    def test_separate_ids_use_separate_sessions(self):
        r1 = self.provider.complete(request(request_id="alpha"))
        r2 = self.provider.complete(request(request_id="beta"))
        self.assertNotEqual(r1.metadata["native_session"], r2.metadata["native_session"])
        self.assertEqual(self.worker.spine.generations, 2)

    def test_changed_prompt_under_same_id_is_denied(self):
        self.provider.complete(request("hello", request_id="same"))
        with self.assertRaises(Conflict):
            self.provider.complete(request("altered prompt", request_id="same"))
        self.assertEqual(self.worker.spine.generations, 1)

    def test_tampered_committed_receipt_is_denied(self):
        self.provider.complete(request())
        self.worker.spine.tamper_committed = True
        with self.assertRaises(NativeReceiptError):
            NativeJeevesProvider(self.worker).complete(request())
        self.assertEqual(self.worker.spine.generations, 1)

    def test_invalid_schema_output_remains_committed_without_regeneration(self):
        schema = {"type": "object", "required": ["answer"],
                  "properties": {"answer": {"type": "string"}}}
        self.worker.spine.generated_text = '{"wrong":true}'
        with self.assertRaises(NativeSchemaError):
            self.provider.complete(request(schema=schema))
        self.assertEqual(self.worker.spine.generations, 1)
        with self.assertRaises(NativeSchemaError):
            self.provider.complete(request(schema=schema))
        self.assertEqual(self.worker.spine.generations, 1)

    def test_judgment_budget_below_native_ceiling_refused(self):
        with self.assertRaises(ProviderError):
            self.provider.complete(request(max_tokens=64))
        self.assertEqual(self.worker.spine.generations, 0)

    def test_uncertain_generation_does_not_repeat(self):
        self.worker.spine.fail_uncertain = True
        with self.assertRaises(RuntimeError):
            self.provider.complete(request())
        self.assertEqual(self.worker.spine.generations, 1)
        with self.assertRaises((Conflict, ProviderError)):
            self.provider.complete(request())
        self.assertEqual(self.worker.spine.generations, 1)

    def test_returned_native_text_without_sqlite_commit_is_held(self):
        self.worker.spine.return_without_commit = True
        with self.assertRaises(ProviderError):
            self.provider.complete(request(request_id="notcommitted"))
        self.assertEqual(self.worker.spine.generations, 1)
        with self.assertRaises(ProviderError):
            self.provider.complete(request(request_id="notcommitted"))
        self.assertEqual(self.worker.spine.generations, 1)

    def test_router_never_retries_uncertain_native(self):
        self.worker.spine.fail_uncertain = True
        router = native_provider_router(self.worker)
        with self.assertRaises(ProviderExhausted):
            router.complete(request())
        self.assertEqual(self.worker.spine.generations, 1)

    def test_model_identity_change_disables_provider(self):
        self.worker.spine.backend.model_digest = "c" * 64
        self.assertFalse(self.provider.available())
        with self.assertRaises(ProviderError):
            self.provider.complete(request())


class TestJeevesNativeControlLoop(unittest.TestCase):
    def setUp(self):
        self.worker = SimulatedWorker()
        self.bridge = NativeJeevesRuntime(self.worker)

    def test_bound_runner_allows_matched_principal(self):
        inputs = RunInputs(
            goal=Goal("simple", "Produce an answer"),
            tenant_id="local", user_id="operator",
            budget=Budget(max_steps=2, max_model_calls=2, max_tokens=2048),
        )
        self.bridge._validate(inputs)

    def test_wrong_tenant_refused_preinference(self):
        inputs = RunInputs(
            goal=Goal("simple", "Answer"), tenant_id="other", user_id="operator",
        )
        with self.assertRaises(NativeRuntimeHold):
            self.bridge.run(inputs)
        self.assertEqual(self.worker.spine.generations, 0)

    def test_wrong_subject_refused_preinference(self):
        inputs = RunInputs(
            goal=Goal("simple", "Answer"), tenant_id="local", user_id="other",
        )
        with self.assertRaises(NativeRuntimeHold):
            self.bridge.run(inputs)
        self.assertEqual(self.worker.spine.generations, 0)

    def test_hosted_provider_not_admitted(self):
        inputs = RunInputs(
            goal=Goal("simple", "Answer"), tenant_id="local", user_id="operator",
            preferred_provider="hosted_provider",
        )
        with self.assertRaises(NativeRuntimeHold):
            self.bridge.run(inputs)

    def test_oversized_config_refused(self):
        with self.assertRaises(NativeRuntimeHold):
            NativeJeevesRuntime(self.worker, config=AgentConfig(planner_max_tokens=4096))

    def test_no_device_release_or_cold_agent_claim(self):
        status = self.bridge.status()
        self.assertFalse(status["device_qualified"])
        self.assertFalse(status["release_certified"])
        self.assertFalse(status["restart_safe_jeeves_checkpoints"])


class TestSourceReadiness(unittest.TestCase):
    def test_simulation_is_not_installer_proof(self):
        result = inspect_native_jeeves(SimulatedWorker())
        self.assertFalse(result.source_receipt_bound)
        self.assertFalse(result.source_bridge_ready)
        self.assertFalse(result.real_turn_witnessed)
        self.assertFalse(result.device_qualified)

    def test_mocked_receipt_is_not_real_device_evidence(self):
        receipt = SimpleNamespace(
            content_verified=True, rights_approved=True,
            source_sha="test-only-source", archive_sha256="test-only-archive",
            model_sha256=MODEL,
        )
        result = inspect_native_jeeves(SimulatedWorker(), receipt)
        self.assertFalse(result.source_bridge_ready)
        self.assertFalse(result.source_receipt_bound)
        self.assertFalse(result.sqlite_spine_present)
        self.assertFalse(result.real_turn_witnessed)
        self.assertFalse(result.device_qualified)
        self.assertFalse(result.release_certified)


if __name__ == "__main__":
    unittest.main()
