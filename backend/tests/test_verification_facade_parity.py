from core.citation_integrity import (
    CitationBinding as BackendCitationBinding,
    _numbers as backend_numbers,
    CitationIntegrityEngine as BackendCitationIntegrityEngine,
    CitationIntegrityReport as BackendCitationIntegrityReport,
)
from core.claim_identity import (
    ClaimFingerprint as BackendClaimFingerprint,
    _clean as backend_clean,
    ClaimIdentityEngine as BackendClaimIdentityEngine,
    ClaimMatch as BackendClaimMatch,
    fingerprint_claim as backend_fingerprint_claim,
)
from skeleton.verification.citation_integrity import (
    CitationBinding,
    _numbers,
    CitationIntegrityEngine,
    CitationIntegrityReport,
)
from skeleton.verification.claim_identity import (
    ClaimFingerprint,
    _clean,
    ClaimIdentityEngine,
    ClaimMatch,
    fingerprint_claim,
)


def test_claim_identity_backend_exports_are_canonical_objects() -> None:
    assert BackendClaimFingerprint is ClaimFingerprint
    assert BackendClaimIdentityEngine is ClaimIdentityEngine
    assert BackendClaimMatch is ClaimMatch
    assert backend_fingerprint_claim is fingerprint_claim


def test_citation_integrity_backend_exports_are_canonical_objects() -> None:
    assert BackendCitationBinding is CitationBinding
    assert BackendCitationIntegrityEngine is CitationIntegrityEngine
    assert BackendCitationIntegrityReport is CitationIntegrityReport


def test_backend_and_canonical_claim_identity_have_identical_behavior() -> None:
    claim = "Algorithm A decreases latency by 10 percent."
    backend = BackendClaimIdentityEngine().canonical_id(claim)
    canonical = ClaimIdentityEngine().canonical_id(claim)
    assert backend == canonical
    assert len(canonical) == 64


def test_backend_and_canonical_citation_attestations_are_identical() -> None:
    binding = CitationBinding(
        claim="Algorithm A decreases latency by 10 percent.",
        source_id="study-a",
        locator="doi:study-a#result",
        binding_method="direct_quote",
        evidence_span=(
            "Algorithm A decreases latency by 10 percent compared with control."
        ),
        supports=True,
        provenance_verified=True,
        source_content_sha256="a" * 64,
    )
    backend = BackendCitationIntegrityEngine().validate(binding)
    canonical = CitationIntegrityEngine().validate(binding)
    assert backend == canonical
    assert backend.attestation_sha256 == canonical.attestation_sha256


def test_backend_private_helper_compatibility_is_preserved() -> None:
    assert backend_clean is _clean
    assert backend_numbers is _numbers
    assert backend_clean("A 10% result.") == _clean("A 10% result.")
    assert backend_numbers("10 and 2.5") == _numbers("10 and 2.5")
