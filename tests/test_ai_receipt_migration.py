from __future__ import annotations

from dataclasses import replace
import pytest

from skeleton.ai.runtime.provenance.algorithm_lifecycle import AlgorithmPolicy
from skeleton.ai.runtime.provenance.execution_receipt import ExecutionReceipt
from skeleton.ai.runtime.provenance.receipt_migration import (
    CORE_INVARIANTS,
    MigrationResult,
    migrate_receipt,
    verify_migration,
)

def _receipt() -> ExecutionReceipt:
    return ExecutionReceipt("a"*64,"b"*64,"c"*64,"d"*64)

def test_retirement_can_stop_issuance_while_preserving_historical_verification() -> None:
    policy=AlgorithmPolicy("sha256",2020,issue_until=2039,verify_until=2099)
    assert policy.can_issue(2039)
    assert not policy.can_issue(2040)
    assert policy.can_verify(2040)
    assert policy.can_verify(2099)
    assert not policy.can_verify(2100)

def test_policy_rejects_verification_retiring_before_issuance() -> None:
    with pytest.raises(ValueError,match="verification"):
        AlgorithmPolicy("sha256",2020,issue_until=2050,verify_until=2040)

def test_migration_preserves_every_declared_core_invariant() -> None:
    source=_receipt()
    result=migrate_receipt(source,algorithm="sha3-256")
    assert set(result.preserved)=={item.name for item in CORE_INVARIANTS}
    assert verify_migration(result,source)

def test_migration_result_rejects_missing_semantic_declaration() -> None:
    source=_receipt()
    target=source.reattest(algorithm="sha3-256")
    with pytest.raises(ValueError,match="all core invariants"):
        MigrationResult(source.digest,target,("semantic_request_identity",))

def test_migration_verifier_rejects_source_substitution() -> None:
    source=_receipt()
    result=migrate_receipt(source,algorithm="sha3-256")
    substituted=replace(source,semantic_request_digest="e"*64)
    assert not verify_migration(result,substituted)
