"""Release artifact plane: evidence manifests and fail-closed provenance gates."""

from skeleton.release.evidence import (
    SCHEMA_ID,
    SCHEMA_VERSION,
    ArtifactLocator,
    ArtifactRecord,
    DigestMismatchError,
    DuplicateArtifactError,
    EvidenceSchemaError,
    GateResult,
    ReleaseEvidence,
    ReleaseEvidenceError,
    UploadMetadata,
    build_evidence,
    canonical_dumps,
    evidence_digest,
    evaluate_release_ready,
    from_v1_provenance,
    parse_evidence,
    require_release_ready,
    serialize_evidence,
)

__all__ = [
    "SCHEMA_ID",
    "SCHEMA_VERSION",
    "ArtifactLocator",
    "ArtifactRecord",
    "DigestMismatchError",
    "DuplicateArtifactError",
    "EvidenceSchemaError",
    "GateResult",
    "ReleaseEvidence",
    "ReleaseEvidenceError",
    "UploadMetadata",
    "build_evidence",
    "canonical_dumps",
    "evidence_digest",
    "evaluate_release_ready",
    "from_v1_provenance",
    "parse_evidence",
    "require_release_ready",
    "serialize_evidence",
]

from skeleton.release.slo_loop import (
    ReleaseDecisionReceipt,
    ReleaseSLOError,
    ReleaseSLOLoop,
    ReleaseSLOPolicy,
)

__all__ += [
    "ReleaseDecisionReceipt",
    "ReleaseSLOError",
    "ReleaseSLOLoop",
    "ReleaseSLOPolicy",
]
