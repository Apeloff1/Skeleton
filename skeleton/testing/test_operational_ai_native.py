"""Real native transformer acceptance; source fixture is untrained, not a quality model.

This test runs in the full Skeleton checkout with its executable native model
owner present. It is not a mock model, no hosted inference, no game systems.
"""
from __future__ import annotations
import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from skeleton.cortex.transformer import TinyTransformer
from skeleton.ai.model_runtime.native_llm_runtime import NativeLLMRuntime
from skeleton.ai.model_runtime.chat_engine import NativeChatEngine
from skeleton.ai.model_runtime.offline_chat import OfflineChatStore
from skeleton.ai.runtime.operational_ai.authority.identity import Actor
from skeleton.ai.runtime.operational_ai.authority.budgets import Limits
from skeleton.ai.runtime.operational_ai.context.memory import MemoryStore
from skeleton.ai.runtime.operational_ai.persistence.journal import EventJournal
from skeleton.ai.runtime.operational_ai.model.catalog import ModelCatalog, ModelArtifact
from skeleton.ai.runtime.operational_ai.model.native import from_checkpoint
from skeleton.ai.runtime.operational_ai.model.gateway import ModelGateway
from skeleton.ai.runtime.operational_ai.orchestration.service import OfflineAIService


class NativeE2E(unittest.TestCase):
    def test_checkpoint_to_gateway_to_durable_chat_to_restart_replay(self):
        with TemporaryDirectory(prefix="operational-native-") as tmp:
            root=Path(tmp)
            checkpoint=root/"native.json"
            runtime=NativeLLMRuntime(TinyTransformer(
                vocab=list(" abcdefghijklmnopqrstuvwxyz!?"),dim=8,ctx=768,seed=5))
            raw=runtime.checkpoint_json().encode("utf-8")
            checkpoint.write_bytes(raw)
            artifact=ModelArtifact("native","native.json",hashlib.sha256(raw).hexdigest(),
                                   len(raw),"test-fixture-untrained")
            native=from_checkpoint(ModelCatalog(root,[artifact]),"native")
            self.assertEqual(native.model_digest,runtime.model_digest)
            self.assertEqual(native.tokenizer_digest,runtime.tokenizer.digest)
            with OfflineChatStore(root/"chat.sqlite") as chat,MemoryStore(root/"memory.sqlite") as memory, \
                 EventJournal(root/"audit.sqlite") as journal:
                actor=Actor("local","tester",native.model_digest,native.tokenizer_digest)
                service=OfflineAIService(actor=actor,gateway=ModelGateway(native),chat_store=chat,
                          memory=memory,journal=journal,
                          limits=Limits(input_bytes=4096,context_tokens=768,
                                        output_tokens=2,output_bytes=2048))
                sid=service.create(system="Be precise.")
                first=service.turn(session=sid,request_id="r1",question="hello",seed=2)
                self.assertEqual(first.revision,1)
                self.assertEqual(service.history(sid)["messages"][-2]["content"],"hello")
                second=service.turn(session=sid,request_id="r1",question="hello",seed=2)
                self.assertTrue(second.replayed)
                self.assertEqual(second.output_digest,first.output_digest)
                self.assertEqual(journal.head(sid)[0],1)
            with OfflineChatStore(root/"chat.sqlite") as reopened:
                loaded=reopened.load(sid,native.model_digest,native.tokenizer_digest)
                self.assertEqual(loaded.revision,1)
                self.assertEqual(loaded.transcript.messages[-1].content,first.text)

if __name__=="__main__":unittest.main()
