"""Real native AI chat session recoverability and exactly-once stream commits.

Exercises actual local transformer attention/generation, not mocked inference.
A tiny untrained CPU network verifies execution and serialization contracts,
not trained-model quality, a provider, application API or installed release.
"""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import tempfile
import unittest

from skeleton.cortex.transformer import TinyTransformer
from skeleton.ai.model_runtime.native_llm_runtime import (
    NativeLLMRuntime, NativeConversationSession)
from skeleton.ai.model_runtime.runtime_contracts import (
    DevicePolicy, GenerationConfig, RuntimeContractError)


class NativeConversationRecoveryJourneyTests(unittest.TestCase):
    def setUp(self):
        model=TinyTransformer(
            vocab=("hello","world","original","game","quest","npc"),
            dim=8,ctx=18,seed=47,n_heads=2,n_layers=2,d_ff=12)
        self.runtime=NativeLLMRuntime(
            model,device_policy=DevicePolicy(requested="cpu"))
        self.config=GenerationConfig(
            max_new_tokens=2,seed=42,temperature=0.8,top_k=3)

    def test_actual_two_turn_conversation_restores_and_replays_same_next_turn(self):
        session=NativeConversationSession(self.runtime)
        first=session.generate("hello",self.config)
        second=session.generate("original game",self.config)
        self.assertEqual(session.turns,2)
        self.assertGreater(session.context_used,0)
        self.assertLessEqual(session.context_used,
                             self.runtime.limits.max_context)
        self.assertEqual(len(first.generated_ids),2)
        self.assertEqual(len(second.generated_ids),2)
        snapshot=session.snapshot()
        before=session.history_digest()
        with tempfile.TemporaryDirectory() as scratch:
            root=Path(scratch)
            runtime_path=root/"reviewed_native_model.json"
            session_path=root/"canonical_native_session.json"
            runtime_path.write_text(self.runtime.checkpoint_json(),encoding="utf-8")
            session_path.write_text(json.dumps(snapshot,sort_keys=True),encoding="utf-8")
            recovery=NativeLLMRuntime.restore_json(
                runtime_path.read_text(encoding="utf-8"))
            restored=NativeConversationSession.restore(
                recovery,json.loads(session_path.read_text(encoding="utf-8")))
        self.assertEqual(restored.turns,2)
        self.assertEqual(restored.history_digest(),before)
        self.assertEqual(restored.snapshot(),snapshot)
        response=session.generate("world",self.config)
        restored_response=restored.generate("world",self.config)
        self.assertEqual(response.generated_ids,restored_response.generated_ids)
        self.assertEqual(response.output_digest,restored_response.output_digest)
        self.assertEqual(session.history_digest(),restored.history_digest())
        self.assertEqual(session.turns,3)
        self.assertEqual(restored.turns,3)

    def test_stream_does_not_commit_until_explicitly_accepted_once(self):
        session=NativeConversationSession(self.runtime)
        before=session.history_digest()
        stream=session.stream_turn("quest",self.config)
        events=list(stream)
        self.assertTrue(events)
        self.assertIsNotNone(stream.result)
        self.assertEqual(session.turns,0)
        self.assertEqual(session.history_digest(),before)
        result=session.commit_stream(stream)
        self.assertEqual(result.output_digest,stream.result.output_digest)
        self.assertEqual(session.turns,1)
        self.assertNotEqual(session.history_digest(),before)
        with self.assertRaises(RuntimeContractError):
            session.commit_stream(stream)
        self.assertEqual(session.turns,1)

    def test_cancelled_stream_is_not_accepted_or_durable(self):
        session=NativeConversationSession(self.runtime)
        before=session.snapshot()
        stream=session.stream_turn("npc",self.config)
        next(stream)
        stream.close()
        with self.assertRaises(RuntimeContractError):
            session.commit_stream(stream)
        self.assertEqual(session.snapshot(),before)
        self.assertEqual(session.turns,0)

    def test_corrupt_session_snapshot_and_model_drift_fail_closed(self):
        session=NativeConversationSession(self.runtime)
        session.generate("original",self.config)
        snapshot=session.snapshot()
        for mutate in (
            lambda x: x.update(digest="f"*64),
            lambda x: x.update(turns=2),
            lambda x: x.update(token_ids=[True]),
            lambda x: x.update(model_digest="f"*64),
        ):
            tampered=deepcopy(snapshot)
            mutate(tampered)
            with self.subTest(tampered=tampered),self.assertRaises(RuntimeContractError):
                NativeConversationSession.restore(self.runtime,tampered)
        self.runtime.model.E[0][0]+=0.5
        with self.assertRaises(RuntimeContractError):
            session.generate("hello",self.config)


if __name__=="__main__":
    unittest.main()
