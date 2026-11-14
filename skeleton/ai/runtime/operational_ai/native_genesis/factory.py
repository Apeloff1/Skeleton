"""Real CPU-native TinyTransformer initialization from original train-only vocab."""
from __future__ import annotations
from dataclasses import dataclass
import platform

from skeleton.cortex.transformer import TinyTransformer
from skeleton.ai.model_runtime.native_llm_runtime import NativeLLMRuntime
from .architecture import estimate, ArchitectureEstimate
from .canonical import bytes_sha
from .policy import GenesisPolicy
from .source import verify_source, GenesisSource
from .vocabulary import NativeVocabulary, build_vocabulary
from .errors import refuse


@dataclass(frozen=True, slots=True)
class GenesisInstance:
    runtime: NativeLLMRuntime
    policy: GenesisPolicy
    source: GenesisSource
    vocabulary: NativeVocabulary
    capacity: ArchitectureEstimate
    checkpoint: bytes
    checkpoint_sha256: str

    def report(self) -> dict:
        return {
            "schema": "skeleton.native-genesis.initialization.v1",
            "policy_sha256": self.policy.digest,
            "source_sha256": self.source.source_sha256,
            "partition_sha256": self.source.partitions_sha256,
            "rights_sha256": self.source.rights_sha256,
            "vocabulary_sha256": self.vocabulary.digest,
            "model_sha256": self.runtime.model_digest,
            "tokenizer_sha256": self.runtime.tokenizer.digest,
            "checkpoint_sha256": self.checkpoint_sha256,
            "checkpoint_bytes": len(self.checkpoint),
            "architecture": self.capacity.report(),
            "python_version": platform.python_version(),
            "bootstrap_kind": "original-native-initialization",
            "parameters_initialized": self.capacity.parameters,
            "actual_sgd_steps": 0,
            "weights_trained": False,
            "candidate_only": True,
            "automatically_served": False,
            "model_quality_verified": False,
            "release_certified": False,
        }


def initialize_native(policy: GenesisPolicy) -> GenesisInstance:
    if type(policy) is not GenesisPolicy:
        refuse("genesis-policy-required")
    source = verify_source()
    vocabulary = build_vocabulary(source, policy)
    capacity = estimate(policy, vocabulary)
    # Native runtime own tokenizer grammar/weights, no remote model or fake backend.
    model = TinyTransformer(
        vocab=vocabulary.entries, dim=policy.dim, ctx=policy.ctx, seed=policy.seed,
        n_heads=policy.n_heads, n_layers=policy.n_layers, d_ff=policy.d_ff,
        norm=policy.norm, ffn_kind=policy.ffn_kind,
        position_mode=policy.position_mode,
    )
    if len(model.itos) != capacity.vocab_size:
        refuse("genesis-vocabulary-identity")
    if set(model.itos) != set(vocabulary.entries) | {"__unk__"}:
        refuse("genesis-token-corpus-mismatch")
    runtime = NativeLLMRuntime(model)
    runtime.assert_model_unchanged()
    if runtime.device.actual != "cpu" or runtime.device.resident:
        refuse("genesis-device-drift")
    if runtime.model_bytes > policy.maximum_model_bytes:
        refuse("genesis-model-storage-over-budget")
    checkpoint = runtime.checkpoint_json().encode("utf-8")
    if len(checkpoint) > policy.maximum_model_bytes:
        refuse("genesis-checkpoint-over-budget")
    reconstructed = NativeLLMRuntime.restore_json(checkpoint.decode("utf-8"))
    if reconstructed.model_digest != runtime.model_digest:
        refuse("genesis-checkpoint-roundtrip")
    if reconstructed.tokenizer.digest != runtime.tokenizer.digest:
        refuse("genesis-tokenizer-roundtrip")
    return GenesisInstance(runtime, policy, source, vocabulary, capacity,
                           checkpoint, bytes_sha(checkpoint))
