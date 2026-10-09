"""Evidence-aware legal risk routing for homebrew hardware and spiritual successors.

This is conservative PROJECT POLICY, not a legal opinion or proof of legality.
Decisions distinguish independent creative design, third-party expression,
hardware access, DRM/TPM, licensing, SDK contracts, and release distribution.
A historical platform being catalogued NEVER grants rights to commercial games.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
from importlib.resources import files
import json
import re

from .platform_registry import PlatformRegistry, PlatformRegistryError, default_registry
from .plagiarism_guard import OriginalityReport, OriginalityDisposition

_SHA = re.compile(r"^[0-9a-f]{64}$")
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_RISK_AREAS = frozenset({
    "code", "art", "characters", "story_dialogue", "music_audio",
    "level_maps", "interface_appearance", "marketing_brand",
    "patent_trade_secrets", "platform_sdk", "hardware_tpm",
    "distribution_contract",
})


class HomebrewPolicyError(ValueError):
    """Invalid assertions or missing evidence in a rights-aware project."""


class Jurisdiction(str, Enum):
    NO = "NO"
    EU_EEA = "EU_EEA"
    US = "US"
    OTHER = "OTHER"


class CreativeMode(str, Enum):
    ORIGINAL = "original_homebrew"
    SPIRITUAL_SUCCESSOR = "spiritual_successor"
    ORIGINAL_MECHANICS_STUDY = "mechanics_study"
    LICENSED_ADAPTATION = "licensed_adaptation"
    THIRD_PARTY_GAME_PORT = "third_party_game_port"


class LegalDisposition(str, Enum):
    DESIGN_ALLOWED_RELEASE_NOT_CERTIFIED = "design_allowed_release_not_certified"
    REVIEW_REQUIRED = "review_required"
    POLICY_BLOCKED = "policy_blocked"


class MaterialKind(str, Enum):
    FACTS_AND_IDEAS = "facts_and_ideas"
    ORIGINAL_EXPRESSION = "original_expression"
    LICENSED_THIRD_PARTY = "licensed_third_party"
    UNLICENSED_THIRD_PARTY = "unlicensed_third_party"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class MaterialRecord:
    """Independently identified source contribution; a digest is only a reference."""
    material_id: str
    category: str
    kind: MaterialKind
    evidence_sha256: str | None = None
    license_identifier: str | None = None
    attribution_required: bool = False
    attribution_recorded: bool = False
    permission_satisfies_proposed_use: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.material_id, str) or not _ID.fullmatch(self.material_id):
            raise HomebrewPolicyError("invalid material identifier")
        if self.category not in _RISK_AREAS:
            raise HomebrewPolicyError("unrecognized material/risk category")
        if not isinstance(self.kind, MaterialKind):
            raise HomebrewPolicyError("invalid material kind")
        if self.evidence_sha256 is not None and (
            not isinstance(self.evidence_sha256, str) or not _SHA.fullmatch(self.evidence_sha256)
        ):
            raise HomebrewPolicyError("evidence must be lowercase SHA-256")
        if any(type(v) is not bool for v in (
            self.attribution_required, self.attribution_recorded,
            self.permission_satisfies_proposed_use,
        )):
            raise HomebrewPolicyError("material flags must be explicit booleans")


@dataclass(frozen=True, slots=True)
class HardwareAccessFacts:
    """Separate platform compatibility from permission to use a game on it."""
    uses_public_documented_interfaces: bool = True
    requires_tpm_or_secure_boot_bypass: bool = False
    requires_keys_or_proprietary_firmware: bool = False
    requires_proprietary_sdk: bool = False
    sdk_rights_verified: bool = False
    distro_channel_contract_verified: bool = False
    device_hardware_owned_or_authorized: bool = False

    def __post_init__(self) -> None:
        if any(type(getattr(self, name)) is not bool for name in self.__dataclass_fields__):
            raise HomebrewPolicyError("hardware access flags must be boolean")


@dataclass(frozen=True, slots=True)
class InteroperabilityFacts:
    """Conditions here are legal review *inputs*, never granted exemptions."""
    code_examined: bool = False
    lawful_program_access: bool = False
    information_not_readily_available: bool = False
    strictly_necessary_parts_only: bool = False
    independently_developed_target: bool = False
    information_used_only_for_interoperability: bool = False
    original_expression_not_reproduced: bool = False

    def __post_init__(self) -> None:
        if any(type(getattr(self, name)) is not bool for name in self.__dataclass_fields__):
            raise HomebrewPolicyError("interoperability facts must be boolean")

    @property
    def narrow_conditions_asserted(self) -> bool:
        return all((
            self.lawful_program_access, self.information_not_readily_available,
            self.strictly_necessary_parts_only, self.independently_developed_target,
            self.information_used_only_for_interoperability,
            self.original_expression_not_reproduced,
        ))


@dataclass(frozen=True, slots=True)
class HomebrewLegalRequest:
    project_id: str
    source_platform_id: str
    target_platform_id: str
    mode: CreativeMode
    jurisdictions: tuple[Jurisdiction, ...]
    materials: tuple[MaterialRecord, ...]
    hardware: HardwareAccessFacts
    interoperability: InteroperabilityFacts = InteroperabilityFacts()
    rights_packet_sha256: str | None = None
    release_requested: bool = False
    uses_franchise_title_or_marks: bool = False
    implies_official_affiliation: bool = False
    distinctive_visual_or_narrative_similarity: bool = False
    patent_or_design_rights_uncertain: bool = False
    confidential_information_used: bool = False
    originality_report: OriginalityReport | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.project_id, str) or not _ID.fullmatch(self.project_id):
            raise HomebrewPolicyError("project identity invalid")
        if not isinstance(self.mode, CreativeMode):
            raise HomebrewPolicyError("invalid creative mode")
        if (not isinstance(self.jurisdictions, tuple) or not self.jurisdictions
            or any(not isinstance(j, Jurisdiction) for j in self.jurisdictions)
            or len(set(self.jurisdictions)) != len(self.jurisdictions)):
            raise HomebrewPolicyError("named jurisdictions required without duplicates")
        if not isinstance(self.materials, tuple) or not self.materials or any(
            not isinstance(m, MaterialRecord) for m in self.materials
        ):
            raise HomebrewPolicyError("typed material/provenance inventory required")
        if len({m.material_id for m in self.materials}) != len(self.materials):
            raise HomebrewPolicyError("duplicate material identity")
        if not isinstance(self.hardware, HardwareAccessFacts) or not isinstance(
            self.interoperability, InteroperabilityFacts
        ):
            raise HomebrewPolicyError("typed hardware and interoperability facts required")
        if self.rights_packet_sha256 is not None and (
            not isinstance(self.rights_packet_sha256, str)
            or not _SHA.fullmatch(self.rights_packet_sha256)
        ):
            raise HomebrewPolicyError("rights evidence needs stable SHA-256")
        if self.originality_report is not None and (
            not isinstance(self.originality_report, OriginalityReport) or
            self.originality_report.project_id != self.project_id
        ):
            raise HomebrewPolicyError("originality evidence is from another project")
        for name in (
            "release_requested", "uses_franchise_title_or_marks",
            "implies_official_affiliation",
            "distinctive_visual_or_narrative_similarity",
            "patent_or_design_rights_uncertain", "confidential_information_used",
        ):
            if type(getattr(self, name)) is not bool:
                raise HomebrewPolicyError("invalid legal fact: " + name)


@dataclass(frozen=True, slots=True)
class HomebrewLegalAssessment:
    project_id: str
    source_platform_id: str
    target_platform_id: str
    disposition: LegalDisposition
    issues: tuple[str, ...]
    blocking_issues: tuple[str, ...]
    review_issues: tuple[str, ...]
    authority_ids: tuple[str, ...]
    policy_controls: tuple[str, ...]
    assessment_digest: str
    rights_packet_sha256: str | None = None
    legal_conclusion: bool = False
    toolchain_qualified: bool = False
    release_authorized: bool = False

    @property
    def design_admissible(self) -> bool:
        return self.disposition is LegalDisposition.DESIGN_ALLOWED_RELEASE_NOT_CERTIFIED


def _digest(obj: dict[str, object]) -> str:
    return sha256(json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def legal_authorities() -> dict[str, object]:
    raw = files("skeleton.ai.game_builder").joinpath("legal_authorities.json").read_text(encoding="utf-8")
    document = json.loads(raw)
    if type(document.get("schema_version")) is not int or document["schema_version"] != 1:
        raise HomebrewPolicyError("invalid cited legal authorities schema")
    items = document.get("authorities")
    if not isinstance(items, list) or len(items) < 10:
        raise HomebrewPolicyError("missing relevant legal authorities")
    ids = [a["id"] for a in items]
    if len(set(ids)) != len(ids) or any(
        not isinstance(a.get("url"), str) or not a["url"].startswith("https://") for a in items
    ):
        raise HomebrewPolicyError("duplicate or non-public legal source")
    return document


def assess_homebrew(
    request: HomebrewLegalRequest, *, registry: PlatformRegistry | None = None,
) -> HomebrewLegalAssessment:
    """Assess PROJECT POLICY using explicit facts, without certifying any jurisdiction."""
    if not isinstance(request, HomebrewLegalRequest):
        raise HomebrewPolicyError("typed legal request required")
    registry = default_registry() if registry is None else registry
    if not isinstance(registry, PlatformRegistry):
        raise HomebrewPolicyError("validated platform registry required")
    registry.get(request.source_platform_id)
    registry.get(request.target_platform_id)
    authority_book = legal_authorities()
    authority_ids = tuple(sorted({
        ref for j in request.jurisdictions
        for ref in authority_book["jurisdictions"][j.value]["sources"]
    }))
    blocked: set[str] = set()
    review: set[str] = set()

    # The entitlement to write software does not grant copyright in another game.
    if request.mode is CreativeMode.THIRD_PARTY_GAME_PORT:
        blocked.add("THIRD_PARTY_GAME_PORT_REQUIRES_GAME_RIGHTSHOLDER_PERMISSION")
    if request.mode is CreativeMode.LICENSED_ADAPTATION and request.rights_packet_sha256 is None:
        blocked.add("LICENSED_ADAPTATION_REQUIRES_GENUINE_REUSE_PERMISSION")
    for material in request.materials:
        if material.kind is MaterialKind.UNLICENSED_THIRD_PARTY:
            blocked.add("UNLICENSED_PROTECTED_EXPRESSION:" + material.material_id)
        elif material.kind is MaterialKind.UNKNOWN:
            review.add("UNKNOWN_ORIGIN:" + material.material_id)
        elif material.kind is MaterialKind.LICENSED_THIRD_PARTY:
            if not (material.evidence_sha256 and material.license_identifier
                    and material.permission_satisfies_proposed_use):
                review.add("UNVERIFIED_LICENSE_SCOPE:" + material.material_id)
            if material.attribution_required and not material.attribution_recorded:
                review.add("ATTRIBUTION_MISSING:" + material.material_id)
        elif material.kind is MaterialKind.ORIGINAL_EXPRESSION:
            if not material.evidence_sha256:
                review.add("ORIGINAL_AUTHORSHIP_NOT_DOCUMENTED:" + material.material_id)

    if request.originality_report is not None:
        scan = request.originality_report
        if scan.blockers or scan.disposition is OriginalityDisposition.BLOCKED:
            blocked.add("ORIGINALITY_PROTECTED_COPY_OR_FALSE_AUTHORSHIP_BLOCKED")
        elif not scan.design_admissible or scan.overlap_findings or scan.media_overlap_findings:
            review.add("ORIGINALITY_UNRESOLVED_SIMILARITY_OR_CREDIT_REVIEW")
    elif request.release_requested:
        review.add("ORIGINALITY_SCREEN_NOT_ATTACHED_TO_RELEASE_REQUEST")

    # Treat trademark / trade dress risks separately from copyright of mechanics.
    if request.implies_official_affiliation:
        blocked.add("MISLEADING_OFFICIAL_AFFILIATION")
    if request.uses_franchise_title_or_marks:
        review.add("TRADEMARK_TITLE_AND_BRANDING_CLEARANCE")
    if request.distinctive_visual_or_narrative_similarity:
        review.add("PROTECTED_EXPRESSION_SUBSTANTIAL_SIMILARITY_REVIEW")
    if request.patent_or_design_rights_uncertain:
        review.add("PATENT_DESIGN_RIGHTS_REVIEW")
    if request.confidential_information_used:
        blocked.add("CONFIDENTIAL_OR_TRADE_SECRET_MATERIAL")

    h = request.hardware
    if h.requires_keys_or_proprietary_firmware:
        blocked.add("PROPRIETARY_KEYS_OR_FIRMWARE_MUST_NOT_BE_INCLUDED")
    if h.requires_tpm_or_secure_boot_bypass:
        review.add("HARDWARE_TPM_ANTI_CIRCUMVENTION_LEGAL_REVIEW")
    if h.requires_proprietary_sdk and not h.sdk_rights_verified:
        review.add("PROPRIETARY_SDK_LICENSE_NOT_VERIFIED")
    if request.interoperability.code_examined:
        if not request.interoperability.narrow_conditions_asserted:
            review.add("INTEROPERABILITY_EXCEPTION_CONDITIONS_NOT_ESTABLISHED")
        else:
            review.add("INTEROPERABILITY_EXCEPTION_NEEDS_JURISDICTION_SPECIFIC_REVIEW")
    if Jurisdiction.OTHER in request.jurisdictions:
        review.add("UNSUPPORTED_JURISDICTION_REQUIRES_LOCAL_COUNSEL")
    if request.rights_packet_sha256 is None:
        review.add("INDEPENDENT_RIGHTS_PACKET_REQUIRED")
    if request.release_requested:
        if not h.device_hardware_owned_or_authorized:
            review.add("DEVICE_ACCESS_AUTHORIZATION_NOT_VERIFIED")
        if not h.distro_channel_contract_verified:
            review.add("DISTRIBUTION_CHANNEL_TERMS_NOT_VERIFIED")
        review.add("NATIVE_TARGET_BUILD_AND_PLAYBACK_NOT_ATTESTED")
        review.add("HUMAN_LEGAL_AND_RELEASE_SIGNOFF_REQUIRED")

    issues = tuple(sorted(blocked | review))
    disposition = (
        LegalDisposition.POLICY_BLOCKED if blocked else
        LegalDisposition.REVIEW_REQUIRED if review else
        LegalDisposition.DESIGN_ALLOWED_RELEASE_NOT_CERTIFIED
    )
    controls = (
        "Build only newly authored code/assets or material with independently established permission.",
        "Hardware documentation does not grant commercial game rights, SDK rights or platform bypass rights.",
        "Evaluate protected appearance, characters, story, music, levels and trade dress independently from gameplay rules.",
        "Treat anti-circumvention, security keys and platform distribution terms as independent release gates.",
        "Require human legal review, machine-specific toolchain validation and provenance before any release.",
    )
    canonical = {
        "project_id":request.project_id,
        "source_platform_id":request.source_platform_id,
        "target_platform_id":request.target_platform_id,
        "mode":request.mode.value,
        "jurisdictions":[j.value for j in request.jurisdictions],
        "materials":[{
            "material_id":m.material_id,"category":m.category,"kind":m.kind.value,
            "evidence_sha256":m.evidence_sha256,"license_identifier":m.license_identifier,
            "attribution_required":m.attribution_required,"attribution_recorded":m.attribution_recorded,
            "permission_satisfies_proposed_use":m.permission_satisfies_proposed_use,
        } for m in request.materials],
        "hardware":{k:getattr(h,k) for k in h.__dataclass_fields__},
        "interoperability":{k:getattr(request.interoperability,k)
                            for k in request.interoperability.__dataclass_fields__},
        "rights_packet_sha256":request.rights_packet_sha256,
        "originality_screen_digest":request.originality_report.screen_digest if request.originality_report else None,
        "originality_artifact_digest":request.originality_report.artifact_sha256 if request.originality_report else None,
        "release_requested":request.release_requested,
        "uses_franchise_title_or_marks":request.uses_franchise_title_or_marks,
        "implies_official_affiliation":request.implies_official_affiliation,
        "distinctive_visual_or_narrative_similarity":request.distinctive_visual_or_narrative_similarity,
        "patent_or_design_rights_uncertain":request.patent_or_design_rights_uncertain,
        "confidential_information_used":request.confidential_information_used,
        "disposition":disposition.value,"issues":list(issues),"authority_ids":list(authority_ids),
    }
    return HomebrewLegalAssessment(
        project_id=request.project_id,
        source_platform_id=request.source_platform_id,
        target_platform_id=request.target_platform_id,
        disposition=disposition, issues=issues, blocking_issues=tuple(sorted(blocked)),
        review_issues=tuple(sorted(review)), authority_ids=authority_ids,
        policy_controls=controls, assessment_digest=_digest(canonical),
        rights_packet_sha256=request.rights_packet_sha256,
    )


def hardware_rights_matrix(
    source_platform_id: str, destination_ids: tuple[str, ...], *,
    request: HomebrewLegalRequest,
    registry: PlatformRegistry | None = None,
) -> tuple[HomebrewLegalAssessment, ...]:
    """Compare rights risks for each destination; no blanket license assumption."""
    from dataclasses import replace
    if not isinstance(destination_ids, tuple) or not destination_ids or len(destination_ids) > 1000:
        raise HomebrewPolicyError("1-1000 destinations required")
    if not isinstance(request, HomebrewLegalRequest) or request.source_platform_id != source_platform_id:
        raise HomebrewPolicyError("source rights and comparison source must match")
    return tuple(assess_homebrew(replace(request, target_platform_id=dest), registry=registry)
                 for dest in destination_ids)
