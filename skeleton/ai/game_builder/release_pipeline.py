"""Native game release gate: actual file evidence + independent signed review.

Signed reviewer opinions are not evidence that the distributed binary matches
the approved source. This gate *first* proves file-byte identity, *then*
evaluates role-scoped independent signatures. No legal release is authorized.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path

from .asset_credits import CreditsBundle
from .legal_paths import HomebrewLegalAssessment
from .native_release_intake import NativeIntakeReceipt, verify_native_release_intake
from .plagiarism_guard import OriginalityReport
from .release_assurance import (
    ReleaseCandidate, ReleaseReadiness, ReleaseReviewReceipt,
    ReviewAttestation, TrustedReviewer, evaluate_independent_review,
)
from .release_trust_anchor import (
    SignedReviewerRegistry, PinnedReviewerResult, evaluate_pinned_independent_review,
)


@dataclass(frozen=True, slots=True)
class NativeReleaseGateReport:
    project_id: str
    target_platform_id: str
    candidate_sha256: str
    intake: NativeIntakeReceipt
    signed_review: ReleaseReviewReceipt
    report_sha256: str
    bytes_and_review_bound: bool = True
    actual_native_execution_attested: bool = False
    legal_clearance_issued: bool = False
    release_authorized: bool = False

    def __post_init__(self) -> None:
        if any(getattr(self, flag) is not False for flag in (
            "actual_native_execution_attested", "legal_clearance_issued",
            "release_authorized",
        )):
            raise ValueError("native originality gate cannot grant a license or distribution rights")
        if self.bytes_and_review_bound is not True:
            raise ValueError("evidence gate cannot represent unchecked data as verified")
        if not isinstance(self.intake, NativeIntakeReceipt) or not isinstance(
            self.signed_review, ReleaseReviewReceipt
        ):
            raise ValueError("native release gate requires actual bytes plus independent review")
        if (
            self.intake.candidate_sha256 != self.candidate_sha256 or
            self.signed_review.candidate_sha256 != self.candidate_sha256
        ):
            raise ValueError("native intake and signed human reviews bind different games")
        expected = sha256(json.dumps({
            "schema":"skeleton.game_builder.native_release_gate.v1",
            "project_id":self.project_id,
            "target_platform_id":self.target_platform_id,
            "candidate_sha256":self.candidate_sha256,
            "intake_sha256":self.intake.intake_sha256,
            "review_receipt_sha256":self.signed_review.receipt_sha256,
        },sort_keys=True,separators=(",", ":")).encode()).hexdigest()
        if self.report_sha256 != expected:
            raise ValueError("native release composite receipt digest inconsistent with inputs")

    @property
    def review_signatures_structurally_complete(self) -> bool:
        """Signed by caller-supplied keys; external root is NOT authenticated."""
        return (
            self.signed_review.status is
            ReleaseReadiness.REVIEW_RECEIPTS_SATISFIED_PUBLICATION_PENDING
        )

    @property
    def independent_reviews_complete(self) -> bool:
        """Unpinned caller-supplied keys never establish independent trust."""
        return False

    def public_receipt(self) -> dict[str, object]:
        return {
            "schema":"skeleton.game_builder.native_release_gate.v1",
            "project_id":self.project_id,
            "target_platform_id":self.target_platform_id,
            "candidate_sha256":self.candidate_sha256,
            "intake_sha256":self.intake.intake_sha256,
            "signed_review_receipt_sha256":self.signed_review.receipt_sha256,
            "review_status":self.signed_review.status.value,
            "independent_reviews_complete":self.independent_reviews_complete,
            "review_signatures_structurally_complete":self.review_signatures_structurally_complete,
            "external_reviewer_root_pinned":False,
            "file_bytes_verified":self.intake.file_bytes_verified,
            "native_binary_boot_verified":False,
            "legal_clearance_issued":False,
            "actual_native_execution_attested":False,
            "publisher_approval_granted":False,
            "release_authorized":False,
            "report_sha256":self.report_sha256,
        }


def run_native_release_gate(
    *, source_directory: str | Path, compiled_binary: str | Path,
    build_evidence: str | Path, gameplay_evidence: str | Path,
    candidate: ReleaseCandidate, legal: HomebrewLegalAssessment,
    originality: OriginalityReport, credits: CreditsBundle,
    trust_registry: tuple[TrustedReviewer, ...],
    attestations: tuple[ReviewAttestation, ...],
    evaluation_utc: str,
) -> NativeReleaseGateReport:
    """Prove exact bytes before trusting independently signed review decisions."""
    intake = verify_native_release_intake(
        source_directory=source_directory, compiled_binary=compiled_binary,
        build_evidence=build_evidence, gameplay_evidence=gameplay_evidence,
        candidate=candidate, legal=legal, originality=originality, credits=credits,
    )
    review = evaluate_independent_review(
        candidate, legal, originality, trust_registry=trust_registry,
        attestations=attestations, evaluation_utc=evaluation_utc,
    )
    canonical = json.dumps({
        "schema":"skeleton.game_builder.native_release_gate.v1",
        "project_id":candidate.project_id,
        "target_platform_id":candidate.target_platform_id,
        "candidate_sha256":candidate.digest,
        "intake_sha256":intake.intake_sha256,
        "review_receipt_sha256":review.receipt_sha256,
    }, sort_keys=True,separators=(",", ":")).encode()
    return NativeReleaseGateReport(
        project_id=candidate.project_id,
        target_platform_id=candidate.target_platform_id,
        candidate_sha256=candidate.digest,
        intake=intake,signed_review=review,
        report_sha256=sha256(canonical).hexdigest(),
    )


@dataclass(frozen=True, slots=True)
class PinnedNativeReleaseGateReport:
    """Actual file-byte intake AND independently pinned, signed reviewer trust."""
    project_id: str
    target_platform_id: str
    candidate_sha256: str
    intake: NativeIntakeReceipt
    pinned_review: PinnedReviewerResult
    report_sha256: str
    release_authorized: bool = False
    executable_boot_verified: bool = False
    legal_noninfringement_certified: bool = False

    def __post_init__(self) -> None:
        if any(getattr(self, flag) is not False for flag in (
            "release_authorized", "executable_boot_verified",
            "legal_noninfringement_certified",
        )):
            raise ValueError("pinned game review cannot issue release, boot or legal clearance")
        if (
            not isinstance(self.intake, NativeIntakeReceipt) or
            not isinstance(self.pinned_review, PinnedReviewerResult) or
            self.intake.candidate_sha256 != self.candidate_sha256 or
            self.pinned_review.candidate_sha256 != self.candidate_sha256
        ):
            raise ValueError("pinned reviewer and actual-byte intake concern different games")
        core = {
            "schema":"skeleton.game_builder.native_pinned_release_gate.v1",
            "project_id":self.project_id,
            "target_platform_id":self.target_platform_id,
            "candidate_sha256":self.candidate_sha256,
            "intake_sha256":self.intake.intake_sha256,
            "pinned_review_sha256":self.pinned_review.evaluation_sha256,
        }
        digest = sha256(json.dumps(core,sort_keys=True,
                                  separators=(",", ":")).encode()).hexdigest()
        if digest != self.report_sha256:
            raise ValueError("pinned game review composite digest mismatch")

    @property
    def independent_reviews_complete(self) -> bool:
        return (
            self.pinned_review.review.status is
            ReleaseReadiness.REVIEW_RECEIPTS_SATISFIED_PUBLICATION_PENDING
        )

    def public_receipt(self) -> dict[str, object]:
        return {
            "schema":"skeleton.game_builder.native_pinned_release_gate.v1",
            "project_id":self.project_id,
            "target_platform_id":self.target_platform_id,
            "candidate_sha256":self.candidate_sha256,
            "intake_sha256":self.intake.intake_sha256,
            "root_key_sha256":self.pinned_review.trust_root_sha256,
            "root_registry_sha256":self.pinned_review.trust_registry_sha256,
            "root_policy_epoch":self.pinned_review.trusted_policy_epoch,
            "signed_review_sha256":self.pinned_review.review.receipt_sha256,
            "independent_reviews_complete":self.independent_reviews_complete,
            "real_file_bytes_checked":True,
            "external_reviewer_root_pinned":True,
            "executable_boot_verified":False,
            "copyright_legally_certified":False,
            "publisher_approval_granted":False,
            "release_authorized":False,
            "report_sha256":self.report_sha256,
        }


def run_pinned_native_release_gate(
    *, source_directory: str | Path, compiled_binary: str | Path,
    build_evidence: str | Path, gameplay_evidence: str | Path,
    candidate: ReleaseCandidate, legal: HomebrewLegalAssessment,
    originality: OriginalityReport, credits: CreditsBundle,
    registry: SignedReviewerRegistry, attestations: tuple[ReviewAttestation, ...],
    evaluation_utc: str, expected_root_key_sha256: str,
    minimum_policy_epoch: int,
) -> PinnedNativeReleaseGateReport:
    """Require actual reviewed game bytes and authenticated independent keyset."""
    intake = verify_native_release_intake(
        source_directory=source_directory, compiled_binary=compiled_binary,
        build_evidence=build_evidence, gameplay_evidence=gameplay_evidence,
        candidate=candidate, legal=legal, originality=originality, credits=credits,
    )
    pinned = evaluate_pinned_independent_review(
        candidate, legal, originality, registry=registry,
        attestations=attestations, evaluation_utc=evaluation_utc,
        expected_root_key_sha256=expected_root_key_sha256,
        minimum_policy_epoch=minimum_policy_epoch,
    )
    core = {
        "schema":"skeleton.game_builder.native_pinned_release_gate.v1",
        "project_id":candidate.project_id,
        "target_platform_id":candidate.target_platform_id,
        "candidate_sha256":candidate.digest,
        "intake_sha256":intake.intake_sha256,
        "pinned_review_sha256":pinned.evaluation_sha256,
    }
    digest = sha256(json.dumps(core,sort_keys=True,
                               separators=(",", ":")).encode()).hexdigest()
    return PinnedNativeReleaseGateReport(
        project_id=candidate.project_id,
        target_platform_id=candidate.target_platform_id,
        candidate_sha256=candidate.digest,
        intake=intake, pinned_review=pinned, report_sha256=digest,
    )
