"""Calculate bounded native CPU model capacity before any allocation."""
from __future__ import annotations
from dataclasses import dataclass
from .policy import SupervisedPolicy
from .vocabulary import AlignedVocabulary
from .errors import reject


@dataclass(frozen=True,slots=True)
class Capacity:
    parameters:int
    estimated_bytes:int
    working_set_bytes:int
    vocabulary_size:int
    model_context:int
    architecture_sha256:str

    def record(self)->dict:
        return {
            "schema":"skeleton.native-supervised.capacity.v1",
            **{k:getattr(self,k) for k in self.__dataclass_fields__},
            "estimate_not_measured_rss":True,"gpu_qualified":False,
        }


def estimate(policy:SupervisedPolicy,vocab:AlignedVocabulary)->Capacity:
    from .canonical import digest
    if type(policy) is not SupervisedPolicy or type(vocab) is not AlignedVocabulary:
        reject("capacity-policy-vocab")
    d=policy.dimension
    v=len(vocab.terms)+1
    f=policy.feed_forward
    # Explicitly account for Wq/Wk/Wv/Wo, FFN gate/up and LN arrays.
    weights=v*d*2+policy.context*d+v
    per_layer=4*d*d+4*d+(2*f*d+f+d if f else 0)
    per_layer+=(f*d+f if f else 0)+2*d
    weights+=policy.layers*per_layer
    logical_bytes=weights*8
    working_bytes=logical_bytes*14+policy.context*d*policy.layers*256
    if working_bytes>policy.max_checkpoint_bytes:
        reject("capacity-over-byte-budget")
    return Capacity(weights,logical_bytes,working_bytes,v,policy.context,
                    digest({"dimension":d,"context":policy.context,"heads":policy.heads,
                            "layers":policy.layers,"feed_forward":f,"vocabulary_sha256":vocab.schema_sha256}))
