"""Cross-jurisdiction homebrew legal paths, hardware access and port admission.

These tests validate conservative release POLICY, not legal conclusions.
"""
from __future__ import annotations

from dataclasses import replace
import json

import pytest

from skeleton.ai.game_builder.legal_paths import (
    CreativeMode, HardwareAccessFacts, HomebrewLegalRequest, HomebrewPolicyError,
    InteroperabilityFacts, Jurisdiction, LegalDisposition, MaterialKind,
    MaterialRecord, assess_homebrew, hardware_rights_matrix, legal_authorities,
)
from skeleton.ai.game_builder.legal_port_bridge import propose_rights_aware_port
from skeleton.ai.game_builder.legal_native_export import (
    ClearedSourceExportError, compile_rights_aware_desktop, export_rights_aware_desktop,
)
from skeleton.ai.game_builder.playable_world import GameBuildIntent, generate_playable_world
from skeleton.ai.game_builder.legal_census import catalog_rights_census
from skeleton.ai.game_builder.port_planner import HomebrewSource, PortMode


PROOF = "a" * 64
EXPRESSION = "b" * 64


def authored(name: str = "new-artwork") -> MaterialRecord:
    return MaterialRecord(name, "art", MaterialKind.ORIGINAL_EXPRESSION, EXPRESSION)


def request(
    *,
    source: str = "sega_dreamcast",
    target: str = "windows_modern",
    mode: CreativeMode = CreativeMode.SPIRITUAL_SUCCESSOR,
    jurisdictions: tuple[Jurisdiction, ...] = (Jurisdiction.NO, Jurisdiction.EU_EEA),
    material: MaterialRecord | None = None,
    release_requested: bool = False,
) -> HomebrewLegalRequest:
    return HomebrewLegalRequest(
        project_id="authored-next-age-game", source_platform_id=source,
        target_platform_id=target, mode=mode, jurisdictions=jurisdictions,
        materials=(material or authored(),),
        hardware=HardwareAccessFacts(),
        rights_packet_sha256=PROOF,
        release_requested=release_requested,
    )


def owned_source() -> HomebrewSource:
    return HomebrewSource(
        "authored-next-age-game", "sega_dreamcast", "project_owned", PROOF,
        ("fresh characters", "different level topology", "new soundtrack"),
    )


def test_cited_matrix_contains_legitimate_sources_for_no_eea_and_us():
    authorities = legal_authorities()
    assert len(authorities["authorities"]) >= 12
    assert "NO-AWL-42" in authorities["jurisdictions"]["NO"]["sources"]
    assert "EU-NINTENDO-PCBOX-355-12" in authorities["jurisdictions"]["EU_EEA"]["sources"]
    assert "US-DMCA-1201" in authorities["jurisdictions"]["US"]["sources"]
    assert authorities["no_global_license_exemption"] is True


@pytest.mark.parametrize("mode", [
    CreativeMode.ORIGINAL, CreativeMode.SPIRITUAL_SUCCESSOR,
    CreativeMode.ORIGINAL_MECHANICS_STUDY,
])
def test_unlicensed_independent_game_can_be_designed_without_franchise_license(mode):
    # No proprietary expression has been imported and hardware isn't bypassed.
    result = assess_homebrew(request(mode=mode))
    assert result.disposition is LegalDisposition.DESIGN_ALLOWED_RELEASE_NOT_CERTIFIED
    assert result.design_admissible
    assert result.legal_conclusion is False
    assert result.release_authorized is False
    assert result.toolchain_qualified is False
    assert "NO-AWL-42" in result.authority_ids


def test_spiritual_successor_can_retarget_to_discontinued_console_as_design_only():
    facts = request(target="bandai_wonderswan")
    result = assess_homebrew(facts)
    assert result.design_admissible
    proposal = propose_rights_aware_port(owned_source(), facts, mode=PortMode.REVERSE_CONSTRAINED)
    assert proposal.design_stage_admitted and not proposal.release_certified
    assert proposal.technical_blueprint is not None
    assert proposal.technical_blueprint.target_platform_id == "bandai_wonderswan"
    assert not proposal.native_build_verified


def test_unlicensed_game_rom_copy_and_commercial_remake_are_not_homebrew():
    bad = MaterialRecord("commercial_rom", "code", MaterialKind.UNLICENSED_THIRD_PARTY)
    result = assess_homebrew(request(material=bad))
    assert result.disposition is LegalDisposition.POLICY_BLOCKED
    assert not result.design_admissible
    assert any("UNLICENSED_PROTECTED_EXPRESSION" in x for x in result.blocking_issues)
    proposal = propose_rights_aware_port(owned_source(), request(material=bad))
    assert proposal.technical_blueprint is None
    assert proposal.design_stage_admitted is False


def test_third_party_port_requires_permission_even_when_original_art_is_supplied():
    result = assess_homebrew(request(mode=CreativeMode.THIRD_PARTY_GAME_PORT))
    assert result.disposition is LegalDisposition.POLICY_BLOCKED
    assert "THIRD_PARTY_GAME_PORT_REQUIRES_GAME_RIGHTSHOLDER_PERMISSION" in result.issues


def test_trademark_risk_and_deceptive_official_affiliation_are_separate():
    marks = assess_homebrew(replace(request(), uses_franchise_title_or_marks=True))
    assert marks.disposition is LegalDisposition.REVIEW_REQUIRED
    assert "TRADEMARK_TITLE_AND_BRANDING_CLEARANCE" in marks.issues
    impostor = assess_homebrew(replace(request(), implies_official_affiliation=True))
    assert impostor.disposition is LegalDisposition.POLICY_BLOCKED
    assert "MISLEADING_OFFICIAL_AFFILIATION" in impostor.blocking_issues


def test_look_and_feel_is_not_automatically_safe_even_when_code_is_fresh():
    risk = assess_homebrew(replace(request(), distinctive_visual_or_narrative_similarity=True))
    assert risk.disposition is LegalDisposition.REVIEW_REQUIRED
    assert "PROTECTED_EXPRESSION_SUBSTANTIAL_SIMILARITY_REVIEW" in risk.issues


def test_license_requires_actual_scope_attribution_and_author_evidence():
    licensed = MaterialRecord(
        "licensed_track", "music_audio", MaterialKind.LICENSED_THIRD_PARTY,
        evidence_sha256=EXPRESSION, license_identifier="SPDX:CC-BY-4.0",
        permission_satisfies_proposed_use=True,
        attribution_required=True, attribution_recorded=False,
    )
    result = assess_homebrew(request(material=licensed))
    assert result.disposition is LegalDisposition.REVIEW_REQUIRED
    assert "ATTRIBUTION_MISSING:licensed_track" in result.issues
    good = assess_homebrew(request(material=replace(licensed, attribution_recorded=True)))
    assert good.design_admissible


def test_unknown_game_source_is_quarantined_not_automatically_promoted():
    unknown = MaterialRecord("old_clip", "music_audio", MaterialKind.UNKNOWN)
    result = assess_homebrew(request(material=unknown))
    assert result.disposition is LegalDisposition.REVIEW_REQUIRED
    assert "UNKNOWN_ORIGIN:old_clip" in result.issues


def test_technical_bypass_is_separate_from_creating_original_game():
    hardware = replace(HardwareAccessFacts(), requires_tpm_or_secure_boot_bypass=True)
    result = assess_homebrew(replace(request(), hardware=hardware))
    assert result.disposition is LegalDisposition.REVIEW_REQUIRED
    assert "HARDWARE_TPM_ANTI_CIRCUMVENTION_LEGAL_REVIEW" in result.issues
    assert result.legal_conclusion is False
    risky = replace(hardware, requires_keys_or_proprietary_firmware=True)
    result = assess_homebrew(replace(request(), hardware=risky))
    assert result.disposition is LegalDisposition.POLICY_BLOCKED
    assert "PROPRIETARY_KEYS_OR_FIRMWARE_MUST_NOT_BE_INCLUDED" in result.blocking_issues


def test_proprietary_sdk_and_platform_channel_are_release_specific():
    hardware = replace(HardwareAccessFacts(), requires_proprietary_sdk=True)
    result = assess_homebrew(replace(request(), hardware=hardware))
    assert "PROPRIETARY_SDK_LICENSE_NOT_VERIFIED" in result.review_issues
    hardware = replace(hardware, sdk_rights_verified=True)
    result = assess_homebrew(replace(request(release_requested=True), hardware=hardware))
    assert "PROPRIETARY_SDK_LICENSE_NOT_VERIFIED" not in result.issues
    assert "DISTRIBUTION_CHANNEL_TERMS_NOT_VERIFIED" in result.issues
    assert "NATIVE_TARGET_BUILD_AND_PLAYBACK_NOT_ATTESTED" in result.issues
    assert result.release_authorized is False


def test_interoperability_is_not_a_general_decompilation_permission():
    incomplete = InteroperabilityFacts(code_examined=True, lawful_program_access=True)
    result = assess_homebrew(replace(request(), interoperability=incomplete))
    assert "INTEROPERABILITY_EXCEPTION_CONDITIONS_NOT_ESTABLISHED" in result.review_issues
    complete = InteroperabilityFacts(
        code_examined=True, lawful_program_access=True,
        information_not_readily_available=True,
        strictly_necessary_parts_only=True,
        independently_developed_target=True,
        information_used_only_for_interoperability=True,
        original_expression_not_reproduced=True,
    )
    assert complete.narrow_conditions_asserted
    result = assess_homebrew(replace(request(), interoperability=complete))
    assert result.disposition is LegalDisposition.REVIEW_REQUIRED
    assert "INTEROPERABILITY_EXCEPTION_NEEDS_JURISDICTION_SPECIFIC_REVIEW" in result.issues


def test_jurisdiction_unknown_does_not_inherit_norwegian_exception():
    result = assess_homebrew(request(jurisdictions=(Jurisdiction.OTHER,)))
    assert result.disposition is LegalDisposition.REVIEW_REQUIRED
    assert "UNSUPPORTED_JURISDICTION_REQUIRES_LOCAL_COUNSEL" in result.issues
    assert result.authority_ids == ()


def test_multi_target_analysis_respects_independent_platform_identities():
    facts = request()
    targets = ("windows_modern", "bandai_wonderswan", "sony_ps5", "arcade_sega_model2")
    outcomes = hardware_rights_matrix("sega_dreamcast", targets, request=facts)
    assert tuple(x.target_platform_id for x in outcomes) == targets
    assert len({x.assessment_digest for x in outcomes}) == len(targets)
    assert all(x.release_authorized is False for x in outcomes)


def test_rights_aware_port_refuses_source_and_evidence_substitutions():
    with pytest.raises(HomebrewPolicyError):
        propose_rights_aware_port(replace(owned_source(), evidence_sha256="b" * 64), request())
    with pytest.raises(HomebrewPolicyError):
        propose_rights_aware_port(owned_source(), replace(request(), project_id="another"))
    with pytest.raises(HomebrewPolicyError):
        propose_rights_aware_port(owned_source(), replace(request(), source_platform_id="sega_saturn"))


def test_legal_assessment_is_stable_and_content_bound():
    first = assess_homebrew(request())
    second = assess_homebrew(request())
    assert first == second
    changed = assess_homebrew(request(target="linux_desktop"))
    assert first.assessment_digest != changed.assessment_digest
    assert first.assessment_digest == assess_homebrew(request()).assessment_digest


@pytest.mark.parametrize("invalid", [
    lambda r: replace(r, jurisdictions=()),
    lambda r: replace(r, jurisdictions=(Jurisdiction.US, Jurisdiction.US)),
    lambda r: replace(r, materials=()),
    lambda r: replace(r, rights_packet_sha256="invalid"),
    lambda r: replace(r, release_requested="yes"),
])
def test_malformed_rights_assertions_are_rejected(invalid):
    with pytest.raises(HomebrewPolicyError):
        invalid(request())


def test_material_validation_rejects_unsupported_rights_category():
    with pytest.raises(HomebrewPolicyError):
        MaterialRecord("malicious", "bios_rom", MaterialKind.ORIGINAL_EXPRESSION, EXPRESSION)
    with pytest.raises(HomebrewPolicyError):
        MaterialRecord("duplicated", "art", MaterialKind.ORIGINAL_EXPRESSION, "invalid")
    duplicated = MaterialRecord("duplicated", "art", MaterialKind.ORIGINAL_EXPRESSION, EXPRESSION)
    with pytest.raises(HomebrewPolicyError):
        replace(request(), materials=(duplicated, duplicated))


def test_proprietary_adaptation_never_certifies_release_even_if_assertions_are_positive():
    params = request(mode=CreativeMode.LICENSED_ADAPTATION, release_requested=True)
    hardware = replace(params.hardware, device_hardware_owned_or_authorized=True,
                       distro_channel_contract_verified=True, sdk_rights_verified=True)
    result = assess_homebrew(replace(params, hardware=hardware))
    assert not result.release_authorized
    assert not result.toolchain_qualified
    assert "HUMAN_LEGAL_AND_RELEASE_SIGNOFF_REQUIRED" in result.issues


def test_every_catalogued_historical_system_has_a_legal_review_profile():
    census = catalog_rights_census()
    summary = census.summary()
    assert summary["catalogued_record_count"] >= 524
    assert summary["dated_sample_records"] >= 94
    assert summary["claim_of_global_archive_completeness"] is False
    assert summary["target_specific_legal_reviews_completed"] == 0
    assert summary["legal_release_certifications"] == 0
    assert len(census.records) == sum(summary["categories"].values())
    assert len(census.select(kind="mechanical")) >= 1
    assert len(census.select(kind="electromechanical")) >= 1
    assert all(x.design_inspiration_available for x in census.records.values())
    assert all(x.distribution_cleared is False for x in census.records.values())
    assert all(x.native_toolchain_status == "unverified" for x in census.records.values())
    assert all(x.legal_release_status == "unreviewed_requires_case_specific_authority"
               for x in census.records.values())
    assert all("jurisdiction_and_current_statutory_exceptions" in x.review_questions
               for x in census.records.values())



def _original_world():
    return generate_playable_world(GameBuildIntent(
        project_id="authored-next-age-game", title="Fresh Successor", subtitle="Cross-era",
        seed=10087, width=11, height=11, levels=1, collectibles_per_level=1,
        hazards_per_level=0, theme="space",
    ), authorized=True)


def test_legally_guarded_desktop_source_bundles_explicit_nonrelease_receipt(tmp_path):
    world = _original_world()
    package = compile_rights_aware_desktop(world, owned_source(), request(), authorized=True)
    again = compile_rights_aware_desktop(world, owned_source(), request(), authorized=True)
    assert package == again
    assert package.project.output_kind == "native_sdl2_source_project"
    assert package.native_executable_compiled is False
    assert package.release_authorized is False
    receipt = package.legal_receipt()
    assert receipt["legal_policy_disposition"] == "design_allowed_release_not_certified"
    assert receipt["full_release_legality_certified"] is False
    assert receipt["real_toolchain_run_verified"] is False
    assert receipt["source_project_id"] == world.intent.project_id
    assert len(receipt["combined_sha256"]) == 64
    path = export_rights_aware_desktop(package, tmp_path / "native", authorized=True)
    files = {p.name for p in path.iterdir()}
    assert files == {"game.c", "CMakeLists.txt", "manifest.json", "legal_review.json"}
    assert json.loads((path / "legal_review.json").read_text()) == receipt
    with pytest.raises(FileExistsError):
        export_rights_aware_desktop(package, path, authorized=True)


@pytest.mark.parametrize("fact_change", [
    {"distinctive_visual_or_narrative_similarity": True},
    {"uses_franchise_title_or_marks": True},
    {"implies_official_affiliation": True},
    {"release_requested": True},
])
def test_guarded_native_source_refuses_unknown_clearance_or_release_requests(fact_change):
    with pytest.raises(ClearedSourceExportError):
        compile_rights_aware_desktop(
            _original_world(), owned_source(), replace(request(), **fact_change),
            authorized=True,
        )


def test_guarded_export_fails_closed_on_illegal_assets_and_other_project():
    ripped = MaterialRecord("ripped", "art", MaterialKind.UNLICENSED_THIRD_PARTY)
    with pytest.raises(ClearedSourceExportError):
        compile_rights_aware_desktop(
            _original_world(), owned_source(), request(material=ripped), authorized=True,
        )
    with pytest.raises(ClearedSourceExportError):
        compile_rights_aware_desktop(
            _original_world(), owned_source(),
            replace(request(), project_id="different-project"), authorized=True,
        )
    with pytest.raises(PermissionError):
        compile_rights_aware_desktop(_original_world(), owned_source(), request(), authorized=False)



def _originality_for_legal_policy(*, plagiarized: bool = False):
    from skeleton.ai.game_builder.plagiarism_guard import (
        AssetDeclaration, AssetDisposition, AttributionStatus, ExpressionSample,
        UseBasis, audit_game_originality,
    )
    src = "a newly invented game story written about an amber observatory with ten unique telescopes"
    reference = src if plagiarized else "another independently invented narrative about tiny ships and frozen gardens"
    modes = ("source_code", "artwork", "music_audio", "characters", "story_dialogue",
             "level_maps", "interface_appearance", "marketing_brand")
    assets = tuple(
        AssetDeclaration(
            m, AssetDisposition.INCLUDED if m == "story_dialogue" else AssetDisposition.NOT_USED,
            basis=UseBasis.OWN_CREATION if m == "story_dialogue" else None,
            provenance_sha256="b"*64 if m == "story_dialogue" else None,
            author_identity="new creator" if m == "story_dialogue" else None,
            attribution=AttributionStatus.NOT_REQUIRED,
        ) for m in modes
    )
    return audit_game_originality(
        "authored-next-age-game", assets=assets,
        candidate_samples=(ExpressionSample("mine", "story_dialogue", src, "b"*64),),
        references=(ExpressionSample("prior", "story_dialogue", reference),),
    )


def test_plagiarism_audit_escalates_through_general_homebrew_legal_assessment():
    safe = _originality_for_legal_policy()
    assert safe.design_admissible
    reviewed = assess_homebrew(replace(request(), originality_report=safe))
    assert reviewed.design_admissible
    assert reviewed.assessment_digest != assess_homebrew(request()).assessment_digest
    copied = _originality_for_legal_policy(plagiarized=True)
    assert not copied.design_admissible
    assessment = assess_homebrew(replace(request(), originality_report=copied))
    assert assessment.disposition is LegalDisposition.REVIEW_REQUIRED
    assert "ORIGINALITY_UNRESOLVED_SIMILARITY_OR_CREDIT_REVIEW" in assessment.issues
    proposal = propose_rights_aware_port(owned_source(), replace(request(), originality_report=copied))
    assert proposal.design_stage_admitted is False
    assert proposal.technical_blueprint is None


def test_plagiarism_audit_cannot_be_attached_to_unrelated_project():
    scanned = _originality_for_legal_policy()
    with pytest.raises(HomebrewPolicyError):
        replace(request(), project_id="some-other-game", originality_report=scanned)


def test_releasing_without_plagiarism_audit_is_explicitly_unverified():
    assessment = assess_homebrew(request(release_requested=True))
    assert "ORIGINALITY_SCREEN_NOT_ATTACHED_TO_RELEASE_REQUEST" in assessment.issues
    assert assessment.release_authorized is False
