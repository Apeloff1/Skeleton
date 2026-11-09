"""Rights-gated desktop C game source generation with review receipt.

This high-level entrypoint is the guarded path from legal project facts to a
native SDL2 source project. Lower-level original-world compiler capabilities
remain non-distribution authoritites and do not certify release legality.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path

from .desktop_native_export import (
    NativeDesktopExportError, NativeDesktopSourceProject,
    compile_native_desktop, export_native_desktop_source,
)
from .legal_paths import (
    HomebrewLegalAssessment, HomebrewLegalRequest, LegalDisposition,
)
from .legal_port_bridge import propose_rights_aware_port
from .plagiarism_guard import OriginalityReport, OriginalityDisposition
from .asset_credits import CreditsBundle, export_game_credits
from .platform_registry import default_registry
from .port_planner import HomebrewSource, PortMode
from .playable_world import PlayableWorld


class ClearedSourceExportError(ValueError):
    """Native source request failed legal/design/build admission policy."""


@dataclass(frozen=True, slots=True)
class LegalNativeDesktopSource:
    project: NativeDesktopSourceProject
    assessment: HomebrewLegalAssessment
    evidence_sha256: str
    package_content_sha256: str
    originality: OriginalityReport | None = None
    credits: CreditsBundle | None = None
    native_executable_compiled: bool = False
    release_authorized: bool = False
    legal_advice_or_certificate: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.project, NativeDesktopSourceProject) or not isinstance(
            self.assessment, HomebrewLegalAssessment
        ):
            raise ClearedSourceExportError("typed game source and rights assessment required")
        if any(getattr(self, f) is not False for f in (
            "native_executable_compiled", "release_authorized",
            "legal_advice_or_certificate",
        )):
            raise ClearedSourceExportError("native source cannot fabricate execution or release")
        expected_source = sha256((
            self.project.game_c + "\0" + self.project.cmake_lists + "\0" +
            self.project.manifest_json
        ).encode("utf-8")).hexdigest()
        if expected_source != self.project.content_digest:
            raise ClearedSourceExportError("native game source changed after compilation")
        try:
            manifest = json.loads(self.project.manifest_json)
        except (TypeError, ValueError) as exc:
            raise ClearedSourceExportError("invalid native source manifest") from exc
        if (manifest.get("source_project_id") != self.assessment.project_id or
            manifest.get("target_platform_id") != self.assessment.target_platform_id or
            manifest.get("source_rights_evidence_sha256") != self.evidence_sha256 or
            manifest.get("executable_built") is not False or
            manifest.get("releasable") is not False):
            raise ClearedSourceExportError("native package and licensing evidence mismatch")
        if self.originality is not None:
            if (not isinstance(self.originality, OriginalityReport) or
                self.originality.project_id != self.assessment.project_id or
                self.originality.artifact_sha256 != manifest.get("world_digest") or
                not self.originality.design_admissible):
                raise ClearedSourceExportError("originality evidence invalid or stale")
        if self.credits is not None:
            if (not isinstance(self.credits, CreditsBundle) or
                self.credits.project_id != self.assessment.project_id or
                self.credits.target_platform_id != self.assessment.target_platform_id or
                self.credits.review_issues):
                raise ClearedSourceExportError("credit licence evidence invalid or stale")
        combined = sha256((
            self.project.content_digest + ":" + self.assessment.assessment_digest +
            ":" + (self.credits.bundle_sha256 if self.credits else "")
        ).encode("ascii")).hexdigest()
        if combined != self.package_content_sha256:
            raise ClearedSourceExportError("game package changed after legal/credit review")

    def legal_receipt(self) -> dict[str, object]:
        return {
            "schema": "skeleton.game_builder.legal_native_source.v1",
            "target_platform_id": self.project.target_platform_id,
            "source_project_id": self.assessment.project_id,
            "legal_assessment_digest": self.assessment.assessment_digest,
            "legal_policy_disposition": self.assessment.disposition.value,
            "source_rights_reference": self.evidence_sha256,
            "native_source_sha256": self.project.content_digest,
            "combined_sha256": self.package_content_sha256,
            "game_content_and_assets_independently_verified": False,
            "real_toolchain_run_verified": False,
            "attribution_notices_embedded": self.credits is not None,
            "attribution_bundle_sha256": self.credits.bundle_sha256 if self.credits else None,
            "plagiarism_screened": self.originality is not None,
            "originality_screen_digest": self.originality.screen_digest if self.originality else None,
            "originality_artifact_bound": (
                self.originality.artifact_sha256 == json.loads(self.project.manifest_json)["world_digest"]
                if self.originality is not None else False
            ),
            "false_claim_of_plagiarism_free": False,
            "full_release_legality_certified": False,
            "release_authorized": False,
            "human_legal_review_required": True,
            "legal_citations": list(self.assessment.authority_ids),
        }


def compile_rights_aware_desktop(
    world: PlayableWorld, source: HomebrewSource, request: HomebrewLegalRequest,
    *, authorized: bool,
    originality: OriginalityReport | None = None,
    credits: CreditsBundle | None = None,
) -> LegalNativeDesktopSource:
    """Refuse review holds and prohibited reuse before emitting source code."""
    if type(authorized) is not bool or not authorized:
        raise PermissionError("guarded native game generation requires authorization")
    if not isinstance(world, PlayableWorld) or not isinstance(request, HomebrewLegalRequest):
        raise ClearedSourceExportError("typed original game world and project rights required")
    if world.intent.project_id != request.project_id:
        raise ClearedSourceExportError("generated world and rights packet project mismatch")
    if request.release_requested:
        raise ClearedSourceExportError("native source generation is not legal release certification")
    if originality is not None:
        if not isinstance(originality, OriginalityReport):
            raise ClearedSourceExportError("typed originality screen required")
        if originality.project_id != request.project_id or originality.artifact_sha256 != world.digest:
            raise ClearedSourceExportError("plagiarism screen does not belong to exact game artifact")
        if not originality.design_admissible or originality.blockers or (
            originality.disposition is not OriginalityDisposition.DESIGN_ADMISSIBLE_NOT_LEGAL_CLEARANCE
        ):
            raise ClearedSourceExportError("potential plagiarism or missing provenance requires review")
    if credits is not None:
        if not isinstance(credits, CreditsBundle):
            raise ClearedSourceExportError("typed attribution and credit bundle required")
        if credits.project_id != request.project_id or credits.target_platform_id != request.target_platform_id:
            raise ClearedSourceExportError("attribution package does not belong to exact destination game")
        if credits.review_issues:
            raise ClearedSourceExportError("unresolved asset/notice licence concerns prevent guarded export")
    proposal = propose_rights_aware_port(source, request, mode=PortMode.ENHANCED)
    if not proposal.design_stage_admitted or proposal.technical_blueprint is None:
        raise ClearedSourceExportError(
            "unresolved legal policy requires independent review before native source export"
        )
    if proposal.legal.disposition is not LegalDisposition.DESIGN_ALLOWED_RELEASE_NOT_CERTIFIED:
        raise ClearedSourceExportError("unverified legal policy admission")
    output = compile_native_desktop(
        world, source, request.target_platform_id, authorized=True,
    )
    combined = sha256((
        output.content_digest + ":" + proposal.legal.assessment_digest +
        ":" + (credits.bundle_sha256 if credits else "")
    ).encode("ascii")).hexdigest()
    return LegalNativeDesktopSource(
        project=output, assessment=proposal.legal,
        evidence_sha256=source.evidence_sha256,
        package_content_sha256=combined,
        originality=originality, credits=credits,
    )


def compile_originality_gated_desktop(
    world: PlayableWorld, source: HomebrewSource, request: HomebrewLegalRequest,
    *, originality: OriginalityReport, authorized: bool,
    credits: CreditsBundle | None = None,
) -> LegalNativeDesktopSource:
    """Required originality screen for release-bound native prototype workflows.

    Does not approve final release. Fresh work may still infringe uncatalogued
    references or violate other rights, contracts and platform measures.
    """
    if not isinstance(originality, OriginalityReport):
        raise ClearedSourceExportError("mandatory comprehensive originality screen absent")
    return compile_rights_aware_desktop(
        world, source, request, originality=originality, credits=credits, authorized=authorized,
    )


def export_rights_aware_desktop(
    bundle: LegalNativeDesktopSource, destination: str | Path, *,
    authorized: bool,
) -> Path:
    """Add legal receipt to an entirely new native source project directory."""
    if type(authorized) is not bool or not authorized:
        raise PermissionError("guarded export requires authorization")
    if not isinstance(bundle, LegalNativeDesktopSource):
        raise ClearedSourceExportError("typed guarded source bundle required")
    path = export_native_desktop_source(bundle.project, destination, authorized=True)
    if bundle.credits is not None:
        export_game_credits(bundle.credits, path / "rights", authorized=True)
    receipt = bundle.legal_receipt()
    with (path / "legal_review.json").open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(receipt, sort_keys=True, indent=2) + "\n")
    return path
