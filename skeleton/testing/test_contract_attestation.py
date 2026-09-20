import pytest

from skeleton.contracts.attestation import (AttestationChain, AttestationQuorum, ContractAttestation, append_attestation, checkpoint, quorum_digest, quorum_satisfied, validate_attestation, validate_quorum, verify_checkpoint, verify_digest, verify_extension)


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


def attestation_for(commit_char, catalog_char="b"):
    return ContractAttestation(
        repository="Apeloff1/Skeleton",
        commit_sha=commit_char * 40,
        catalog_digest=catalog_char * 64,
        execution_order=("a",),
        contract_fingerprints={"a": "c" * 64},
    )


def test_attestation_chain_links_exact_predecessor_digest():
    first = attestation_for("a")
    second = attestation_for("b")
    chain = append_attestation(None, first)
    chain = append_attestation(chain, second)
    chain.validate()
    assert chain.previous_digests == (None, first.digest())
    assert chain.head_digest() == second.digest()


def test_attestation_chain_rejects_broken_link():
    first = attestation_for("a")
    second = attestation_for("b")
    chain = AttestationChain(
        attestations=(first, second),
        previous_digests=(None, "0" * 64),
    )
    with pytest.raises(ValueError, match="discontinuity"):
        chain.validate()


def test_attestation_chain_rejects_duplicate_commit():
    first = attestation_for("a")
    duplicate = attestation_for("a", "d")
    chain = AttestationChain(
        attestations=(first, duplicate),
        previous_digests=(None, first.digest()),
    )
    with pytest.raises(ValueError, match="duplicate commit"):
        chain.validate()


def test_attestation_chain_rejects_root_predecessor():
    first = attestation_for("a")
    chain = AttestationChain((first,), ("0" * 64,))
    with pytest.raises(ValueError, match="root"):
        chain.validate()


def test_attestation_chain_rejects_shape_mismatch():
    first = attestation_for("a")
    chain = AttestationChain((first,), ())
    with pytest.raises(ValueError, match="length mismatch"):
        chain.validate()


def test_checkpoint_binds_head_length_repository_and_commit():
    chain = append_attestation(None, attestation_for("a"))
    cp = checkpoint(chain)
    assert cp.length == 1
    assert cp.repository == "Apeloff1/Skeleton"
    assert cp.head_commit_sha == "a" * 40
    assert verify_checkpoint(chain, cp)


def test_checkpoint_rejects_truncated_or_extended_chain():
    first = append_attestation(None, attestation_for("a"))
    cp = checkpoint(first)
    second = append_attestation(first, attestation_for("b"))
    assert not verify_checkpoint(second, cp)
    assert verify_extension(cp, second)


def test_extension_rejects_rewritten_trusted_prefix():
    original = append_attestation(None, attestation_for("a"))
    cp = checkpoint(original)
    rewritten = append_attestation(None, attestation_for("c"))
    rewritten = append_attestation(rewritten, attestation_for("b"))
    assert not verify_extension(cp, rewritten)


def test_extension_rejects_checkpoint_beyond_candidate_length():
    chain = append_attestation(None, attestation_for("a"))
    cp = checkpoint(append_attestation(chain, attestation_for("b")))
    assert not verify_extension(cp, chain)


def test_extension_accepts_exact_checkpoint_without_growth():
    chain = append_attestation(None, attestation_for("a"))
    assert verify_extension(checkpoint(chain), chain)


def test_quorum_requires_exact_threshold_of_distinct_witnesses():
    cp = checkpoint(append_attestation(None, attestation_for("a")))
    quorum = AttestationQuorum(cp, ("ci", "security", "readiness"), 2)
    digest = quorum_digest(quorum)
    assert quorum_satisfied(quorum, {"ci": digest, "security": digest})
    assert not quorum_satisfied(quorum, {"ci": digest})


def test_quorum_rejects_digest_for_different_policy():
    cp = checkpoint(append_attestation(None, attestation_for("a")))
    strict = AttestationQuorum(cp, ("ci", "security", "readiness"), 3)
    loose = AttestationQuorum(cp, ("ci", "security", "readiness"), 2)
    loose_digest = quorum_digest(loose)
    assert not quorum_satisfied(strict, {
        "ci": loose_digest,
        "security": loose_digest,
        "readiness": loose_digest,
    })


def test_quorum_rejects_duplicate_witnesses():
    cp = checkpoint(append_attestation(None, attestation_for("a")))
    with pytest.raises(ValueError, match="duplicate"):
        validate_quorum(AttestationQuorum(cp, ("ci", "ci"), 1))


@pytest.mark.parametrize("threshold", [0, 3, True])
def test_quorum_rejects_invalid_threshold(threshold):
    cp = checkpoint(append_attestation(None, attestation_for("a")))
    with pytest.raises(ValueError, match="threshold"):
        validate_quorum(AttestationQuorum(cp, ("ci", "security"), threshold))


def test_quorum_identity_is_order_independent_for_witness_set():
    cp = checkpoint(append_attestation(None, attestation_for("a")))
    left = AttestationQuorum(cp, ("ci", "security"), 2)
    right = AttestationQuorum(cp, ("security", "ci"), 2)
    assert quorum_digest(left) == quorum_digest(right)
