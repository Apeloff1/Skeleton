"""The archived contract package must not fork canonical type identity."""
import pytest

from skeleton.frontier import contracts
from skeleton.frontier.runtime import contracts as canonical


def test_recovered_package_preserves_public_contract_identity():
    for name in ("AgentContract", "MemoryContract", "ProvenanceRecord", "stable_content_digest"):
        assert getattr(contracts, name) is getattr(canonical, name)
    receipt = contracts.ProvenanceRecord.for_artifact(
        source_repository="Apeloff1/Skeleton", payload={"result": "ok"},
    )
    assert receipt.content_sha256 == canonical.stable_content_digest({"result": "ok"})


@pytest.mark.parametrize("accepted", [1, "true", None])
def test_admission_requires_explicit_evidence(accepted):
    with pytest.raises(ValueError):
        contracts.AdmissionContract("job", accepted, "review")


@pytest.mark.parametrize("attempts", [-1, True, 1001, 1.5])
def test_recovery_requires_bounded_attempts(attempts):
    with pytest.raises(ValueError):
        contracts.RecoveryContract("job", attempts, True)


def test_contracts_accept_valid_evidence():
    assert contracts.AdmissionContract("job", True, "reviewed").accepted
    assert contracts.RecoveryContract("job", 2, True).recovered
