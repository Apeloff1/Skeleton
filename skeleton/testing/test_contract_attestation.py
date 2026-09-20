import pytest

from skeleton.contracts.attestation import ContractAttestation, validate_attestation, verify_digest


def valid_attestation():
    return ContractAttestation(
        repository="Apeloff1/Skeleton",
        commit_sha="a" * 40,
        catalog_digest="b" * 64,
        execution_order=("a", "b"),
        contract_fingerprints={"a": "c" * 64, "b": "d" * 64},
    )


def test_attestation_is_canonical_and_digest_stable():
    left = valid_attestation()
    right = ContractAttestation(
        repository="Apeloff1/Skeleton",
        commit_sha="A" * 40,
        catalog_digest="B" * 64,
        execution_order=("a", "b"),
        contract_fingerprints={"b": "d" * 64, "a": "c" * 64},
    )
    validate_attestation(left)
    validate_attestation(right)
    assert left.canonical_bytes() == right.canonical_bytes()
    assert left.digest() == right.digest()
    assert verify_digest(left, left.digest())


@pytest.mark.parametrize("sha", ["", "a" * 39, "g" * 40])
def test_attestation_rejects_invalid_commit_sha(sha):
    item = valid_attestation()
    bad = ContractAttestation(
        repository=item.repository,
        commit_sha=sha,
        catalog_digest=item.catalog_digest,
        execution_order=item.execution_order,
        contract_fingerprints=item.contract_fingerprints,
    )
    with pytest.raises(ValueError, match="commit sha"):
        validate_attestation(bad)


def test_attestation_requires_exact_fingerprint_coverage():
    item = valid_attestation()
    bad = ContractAttestation(
        repository=item.repository,
        commit_sha=item.commit_sha,
        catalog_digest=item.catalog_digest,
        execution_order=("a", "b"),
        contract_fingerprints={"a": "c" * 64},
    )
    with pytest.raises(ValueError, match="coverage mismatch"):
        validate_attestation(bad)


def test_attestation_rejects_duplicate_execution_identity():
    item = valid_attestation()
    bad = ContractAttestation(
        repository=item.repository,
        commit_sha=item.commit_sha,
        catalog_digest=item.catalog_digest,
        execution_order=("a", "a"),
        contract_fingerprints={"a": "c" * 64},
    )
    with pytest.raises(ValueError, match="duplicate contract"):
        validate_attestation(bad)


def test_digest_verification_fails_for_tampering():
    item = valid_attestation()
    assert not verify_digest(item, "0" * 64)
    assert not verify_digest(item, "short")
