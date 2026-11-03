"""Actual source-derived native model; no pretrained weights or mock responses."""
from __future__ import annotations
from dataclasses import dataclass
from skeleton.cortex.transformer import TinyTransformer
from skeleton.ai.model_runtime.native_llm_runtime import NativeLLMRuntime
from .source import SourceScope,prepare_source
from .policy import SupervisedPolicy
from .vocabulary import AlignedVocabulary,build_aligned_vocabulary
from .architecture import Capacity,estimate
from .canonical import bytes_sha
from .errors import reject
from .token_coverage import inspect as inspect_coverage, require_admitted


@dataclass(frozen=True,slots=True)
class AlignedGenesis:
    source:SourceScope
    policy:SupervisedPolicy
    vocabulary:AlignedVocabulary
    capacity:Capacity
    runtime:NativeLLMRuntime
    initial_checkpoint:bytes
    initial_checkpoint_sha256:str

    def report(self)->dict:
        return {
            "schema":"skeleton.native-supervised.genesis.v1",
            "source_sha256":self.source.corpus_sha256,
            "policy_sha256":self.policy.sha256,
            "vocabulary_sha256":self.vocabulary.schema_sha256,
            "model_sha256":self.runtime.model_digest,
            "tokenizer_sha256":self.runtime.tokenizer.digest,
            "checkpoint_sha256":self.initial_checkpoint_sha256,
            "checkpoint_bytes":len(self.initial_checkpoint),
            "initialized_native_weights":True,
            "trained_sgd_steps":0,"candidate_only":True,
            "device_qualified":False,
            "production_authorized":False,
        }


def initialize_aligned_model(policy:SupervisedPolicy)->AlignedGenesis:
    if type(policy) is not SupervisedPolicy:
        reject("boot-policy-required")
    source=prepare_source()
    vocab=build_aligned_vocabulary(source,policy)
    capacity=estimate(policy,vocab)
    model=TinyTransformer(
        vocab=vocab.terms,dim=policy.dimension,ctx=policy.context,
        seed=policy.seed,n_heads=policy.heads,n_layers=policy.layers,
        d_ff=policy.feed_forward,norm="ln",ffn_kind="gelu",
        position_mode="rope",
    )
    runtime=NativeLLMRuntime(model)
    runtime.assert_model_unchanged()
    coverage=inspect_coverage(runtime.model,source)
    require_admitted(coverage,policy)
    if runtime.device.actual!="cpu" or runtime.device.resident:
        reject("native-bootstrap-device")
    if len(model.itos)!=len(vocab.terms)+1:
        reject("native-bootstrap-vocabulary")
    if runtime.model_bytes>policy.max_checkpoint_bytes:
        reject("native-bootstrap-byte-budget")
    raw=runtime.checkpoint_json().encode("utf-8")
    if len(raw)>policy.max_checkpoint_bytes:
        reject("native-bootstrap-checkpoint-budget")
    replay=NativeLLMRuntime.restore_json(raw.decode("utf-8"))
    if replay.model_digest!=runtime.model_digest or replay.tokenizer.digest!=runtime.tokenizer.digest:
        reject("native-bootstrap-roundtrip")
    return AlignedGenesis(source,policy,vocab,capacity,runtime,raw,bytes_sha(raw))
