from __future__ import annotations

import pytest

from skeleton.ai.runtime.provenance.execution_receipt import (
    ExecutionReceipt,
    ProofAttestation,
    SUPPORTED_DIGESTS,
    verify_chain,
)

D="a"*64
R="b"*64
C="c"*64
P="d"*64

def _receipt(**kwargs) -> ExecutionReceipt:
    values={"semantic_request_digest":D,"runtime_receipt_digest":R,"context_digest":C,"admission_policy_digest":P}
    values.update(kwargs)
    return ExecutionReceipt(**values)

@pytest.mark.parametrize("algorithm",SUPPORTED_DIGESTS)
def test_receipt_supports_algorithm_agility(algorithm: str) -> None:
    receipt=_receipt(digest_algorithm=algorithm)
    assert len(receipt.digest)==64
    assert receipt.verify_offline()

def test_reattest_preserves_semantics_and_links_predecessor() -> None:
    original=_receipt()
    migrated=original.reattest(algorithm="sha3-256")
    assert migrated.predecessor_digest==original.digest
    assert migrated.semantic_request_digest==original.semantic_request_digest
    assert migrated.runtime_receipt_digest==original.runtime_receipt_digest
    assert verify_chain((original,migrated))

def test_chain_rejects_semantic_substitution() -> None:
    original=_receipt()
    forged=ExecutionReceipt(semantic_request_digest="e"*64,runtime_receipt_digest=R,context_digest=C,admission_policy_digest=P,predecessor_digest=original.digest)
    assert not verify_chain((original,forged))

def test_chain_rejects_broken_predecessor() -> None:
    original=_receipt()
    forged=_receipt(predecessor_digest="f"*64)
    assert not verify_chain((original,forged))

def test_multi_proof_receipt_is_order_canonical() -> None:
    a=ProofAttestation("signature","verifier-a","1"*64)
    b=ProofAttestation("transparency","verifier-b","2"*64,algorithm="sha3-256")
    assert _receipt(proofs=(a,b)).digest==_receipt(proofs=(b,a)).digest

def test_duplicate_proof_authority_fails_closed() -> None:
    proof=ProofAttestation("signature","same","1"*64)
    with pytest.raises(ValueError,match="unique"):
        _receipt(proofs=(proof,proof))

def test_receipt_binds_admission_policy_identity() -> None:
    assert _receipt(admission_policy_digest="1"*64).digest != _receipt(admission_policy_digest="2"*64).digest

def test_receipt_binds_context_identity() -> None:
    assert _receipt(context_digest="1"*64).digest != _receipt(context_digest="2"*64).digest

def test_unknown_algorithm_fails_closed() -> None:
    with pytest.raises(ValueError,match="unsupported"):
        _receipt(digest_algorithm="future-mystery")
