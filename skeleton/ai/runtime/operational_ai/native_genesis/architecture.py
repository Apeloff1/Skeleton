"""Conservative native model memory estimate before physical allocation."""
from __future__ import annotations
from dataclasses import dataclass
from .policy import GenesisPolicy
from .vocabulary import NativeVocabulary
from .errors import refuse


@dataclass(frozen=True, slots=True)
class ArchitectureEstimate:
    parameters: int
    weight_bytes: int
    expanded_memory_bytes: int
    activation_estimate_bytes: int
    vocab_size: int
    context: int
    dimensions: int
    layer_count: int

    def report(self) -> dict:
        return {
            "schema": "skeleton.native-genesis.estimate.v1",
            **{key:getattr(self,key) for key in self.__dataclass_fields__},
            "estimate_only": True,
            "actual_peak_rss_measured": False,
            "gpu_admitted": False,
        }


def estimate(policy: GenesisPolicy, vocabulary: NativeVocabulary) -> ArchitectureEstimate:
    if type(policy) is not GenesisPolicy or type(vocabulary) is not NativeVocabulary:
        refuse("architecture-contract")
    d = policy.dim
    v = len(vocabulary.entries) + 1
    ff = policy.d_ff
    # Embeddings E, learned P, output projection, output bias.
    embedding = v*d + policy.ctx*d + v*d + v
    # Four attention projections, 2 layernorm affine sets,
    # GELU or SwiGLU feed-forward weights/biases.
    per_layer = 4*d*d + 4*d
    if ff:
        per_layer += ff*d + ff + d*ff + d
        # Actual implementation always allocates Wu and bu for both FFN kinds.
        per_layer += ff*d + ff
        per_layer += 2*d
    total = embedding + policy.n_layers * per_layer
    # Estimate reserves 8 bytes per parameter for pure-Python float storage
    # and a factor for object/list overhead, gradient arrays and checkpoint.
    weights = total * 8
    expanded = weights * 12
    activation = policy.ctx * policy.dim * policy.n_layers * 128
    predicted = expanded + activation
    if predicted > policy.maximum_model_bytes:
        refuse("estimated-model-budget")
    return ArchitectureEstimate(total, weights, predicted, activation,
                                v, policy.ctx, d, policy.n_layers)
