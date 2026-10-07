"""Convert native deterministic replay receipts into portable attestations."""
from __future__ import annotations
from typing import Mapping
from skeleton.ai.model_runtime.runtime_contracts import ReplayReceipt
from .attestation import Attestation,Subject
from .commitments import Commitment

def attestation_from_replay(
    receipt:ReplayReceipt,
    *,
    context_digest:str|None=None,
    admission_policy_digest:str|None=None,
    extra:Mapping[str,object]|None=None,
)->Attestation:
    subjects=(
        Subject("native-runtime-receipt",Commitment.of(receipt.to_dict())),
        Subject("model",Commitment("sha256",receipt.model_digest)),
        Subject("tokenizer",Commitment("sha256",receipt.tokenizer_digest)),
        Subject("output",Commitment("sha256",receipt.output_digest)),
    )
    predicate:dict[str,object]={
        "runtime_schema":receipt.schema,
        "request_digest":receipt.request_digest,
        "architecture_digest":receipt.architecture_digest,
        "config_digest":receipt.config_digest,
        "device_digest":receipt.device_digest,
        "seed":receipt.seed,
        "context_digest":context_digest,
        "admission_policy_digest":admission_policy_digest,
    }
    if extra:
        reserved=set(predicate)
        overlap=reserved & set(extra)
        if overlap: raise ValueError(f"extra predicate cannot replace reserved fields: {sorted(overlap)}")
        predicate.update(extra)
    return Attestation(subjects,predicate)

def verify_replay_binding(attestation:Attestation,receipt:ReplayReceipt)->bool:
    by_name={subject.name:subject.commitment for subject in attestation.subjects}
    expected={
        "native-runtime-receipt":Commitment.of(receipt.to_dict()),
        "model":Commitment("sha256",receipt.model_digest),
        "tokenizer":Commitment("sha256",receipt.tokenizer_digest),
        "output":Commitment("sha256",receipt.output_digest),
    }
    return by_name==expected and attestation.predicate.get("request_digest")==receipt.request_digest

__all__=["attestation_from_replay","verify_replay_binding"]
