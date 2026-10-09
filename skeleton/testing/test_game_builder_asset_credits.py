"""Original author credits, third-party notices and license evidence checks."""
from __future__ import annotations

from dataclasses import replace
import json

import pytest

from skeleton.ai.game_builder.asset_credits import (
    AttributionEntry, CreditsError, compile_game_credits, export_game_credits,
)
from skeleton.ai.game_builder.legal_paths import MaterialKind, MaterialRecord

PROOF = "b"*64
LICENSE = "c"*64
RELEASE = "d"*64


def own():
    return MaterialRecord("original-code", "code", MaterialKind.ORIGINAL_EXPRESSION, PROOF)


def licensed():
    return MaterialRecord(
        "sprite-font", "art", MaterialKind.LICENSED_THIRD_PARTY, PROOF,
        license_identifier="MIT", attribution_required=True,
        attribution_recorded=True, permission_satisfies_proposed_use=True,
    )


def credit():
    return AttributionEntry(
        material_id="sprite-font", original_author="Independent artist",
        source_title="Artist's UI font", rights_holder="Independent artist",
        license_id="MIT", license_url="https://opensource.org/license/mit",
        attribution_text="Copyright 2024 Independent artist; MIT license.",
        license_text_sha256=LICENSE,
        adaptation_description="Original glyph metrics reorganized for handheld",
        permitted_medium="windows-modern",
        release_permission_evidence_sha256=RELEASE,
        permission_externally_verified=True,
    )


def generate(materials=None, credits=None):
    return compile_game_credits(
        "my-original-game", "windows_modern",
        materials=(own(),licensed()) if materials is None else materials,
        third_party=(credit(),) if credits is None else credits,
        original_authors=("Author of original homebrew game",),
    )


def test_usable_credits_bundle_has_integrity_and_missing_release_consent():
    bundle = generate()
    assert "Artist's UI font" in bundle.credits_md
    assert "MIT" in bundle.third_party_notices_txt
    assert "THIRD-PARTY MATERIAL NOTICES" in bundle.third_party_notices_txt
    assert bundle.bundle_sha256 == generate().bundle_sha256
    assert "FINAL_HUMAN_LICENSE_AND_DISTRIBUTION_REVIEW_REQUIRED" in bundle.review_issues
    assert not bundle.release_authorized
    assert not bundle.licensed_material_independently_cleared
    data = json.loads(bundle.inventory_json)
    assert data["legal_clearance_granted"] is False
    assert len(data["third_party_records"]) == 2
    assert bundle.as_receipt()["third_party_licenses_legally_certified"] is False


def test_original_only_has_explicit_author_notice_and_no_copied_components():
    bundle = generate(materials=(own(),),credits=())
    assert "Independently authored work" in bundle.credits_md
    assert "Artist's UI font" not in bundle.credits_md
    assert bundle.release_authorized is False
    assert json.loads(bundle.inventory_json)["third_party_records"][0]["rights_basis"] == "original_expression"


def test_credits_export_writes_real_files_once_and_never_replaces_notice(tmp_path):
    bundle = generate()
    path = export_game_credits(bundle, tmp_path/"credits", authorized=True)
    assert {p.name for p in path.iterdir()} == {
        "CREDITS.md","THIRD_PARTY_NOTICES.txt","material_inventory.json",
    }
    assert (path/"CREDITS.md").read_text() == bundle.credits_md
    with pytest.raises(FileExistsError):
        export_game_credits(bundle, path, authorized=True)
    with pytest.raises(PermissionError):
        export_game_credits(bundle, tmp_path/"new", authorized=False)


@pytest.mark.parametrize("materials,credits", [
    ((own(), licensed()), ()),
    ((own(),), (credit(),)),
    ((own(), licensed(), licensed()), (credit(),)),
    ((own(),MaterialRecord("ripped-rom", "code", MaterialKind.UNLICENSED_THIRD_PARTY)), ()),
    ((own(),MaterialRecord("uncertain", "art", MaterialKind.UNKNOWN)), ()),
])
def test_copying_unknown_and_uncredited_materials_are_refused(materials,credits):
    with pytest.raises(CreditsError):
        generate(materials=materials,credits=credits)


def test_scope_mismatch_missing_credit_and_false_external_verification_create_holds():
    incomplete = replace(licensed(), attribution_recorded=False,
                         permission_satisfies_proposed_use=False)
    bogus = replace(credit(), license_id="CC-BY-NC-SA-4.0",
                    permission_externally_verified=False, license_text_sha256=None)
    report = generate(materials=(own(),incomplete),credits=(bogus,))
    assert any("RIGHTS_OR_LICENSE_SCOPE_UNVERIFIED" in s for s in report.review_issues)
    assert any("ATTRIBUTION_OBLIGATIONS_UNVERIFIED" in s for s in report.review_issues)
    assert any("PERMISSION_EVIDENCE_NEEDS_INDEPENDENT_REVIEW" in s for s in report.review_issues)
    assert any("SHAREALIKE_COPYLEFT_OR_NONCOMMERCIAL_SCOPE_REVIEW" in s for s in report.review_issues)
    assert any("LICENSE_TEXT_NOT_BOUND_TO_NOTICE" in s for s in report.review_issues)


def test_markdown_injection_in_untrusted_credit_names_is_escaped():
    escape = replace(credit(), source_title="[spoof](https://evil.example)")
    bundle = generate(credits=(escape,))
    assert "\\[spoof\\]" in bundle.credits_md
    assert "[spoof](https://evil.example)" not in bundle.credits_md


def test_original_author_strings_and_url_provenance_are_bounded():
    with pytest.raises(CreditsError):
        replace(credit(), original_author="author\nmalicious marker")
    with pytest.raises(CreditsError):
        replace(credit(), license_url="file:///etc/secret")
    with pytest.raises(CreditsError):
        replace(credit(), release_permission_evidence_sha256="invalid")
    with pytest.raises(CreditsError):
        compile_game_credits("my-original-game","windows_modern",materials=(own(),),
                             third_party=(), original_authors=("same","same"))



def test_guarded_native_game_source_embeds_original_author_notices(tmp_path):
    from skeleton.ai.game_builder.playable_world import GameBuildIntent, generate_playable_world
    from skeleton.ai.game_builder.port_planner import HomebrewSource
    from skeleton.ai.game_builder.legal_paths import (
        CreativeMode, HardwareAccessFacts, HomebrewLegalRequest, Jurisdiction,
    )
    from skeleton.ai.game_builder.legal_native_export import (
        ClearedSourceExportError, compile_rights_aware_desktop,
        export_rights_aware_desktop,
    )
    world = generate_playable_world(GameBuildIntent(
        project_id="my-original-game", title="Fresh Handheld Quest",
        subtitle="New original IP", seed=4567, width=11, height=11,
        levels=1, collectibles_per_level=1, hazards_per_level=0,
    ), authorized=True)
    source = HomebrewSource(
        "my-original-game", "sega_dreamcast", "project_owned",
        "a"*64, ("independent protagonist", "custom platform physics"),
    )
    rights = HomebrewLegalRequest(
        project_id="my-original-game", source_platform_id="sega_dreamcast",
        target_platform_id="windows_modern", mode=CreativeMode.ORIGINAL,
        jurisdictions=(Jurisdiction.NO, Jurisdiction.EU_EEA),
        materials=(own(),), hardware=HardwareAccessFacts(),
        rights_packet_sha256="a"*64,
    )
    credits = generate(materials=(own(),), credits=())
    package = compile_rights_aware_desktop(world, source, rights,
                                           credits=credits, authorized=True)
    assert package.legal_receipt()["attribution_bundle_sha256"] == credits.bundle_sha256
    assert package.legal_receipt()["attribution_notices_embedded"] is True
    assert package.legal_receipt()["release_authorized"] is False
    with pytest.raises(ClearedSourceExportError):
        replace(package, project=replace(package.project, game_c=package.project.game_c + "/* stolen payload */"))
    with pytest.raises(ClearedSourceExportError):
        replace(package, project=replace(package.project, cmake_lists="evil custom build"))
    with pytest.raises(ClearedSourceExportError):
        replace(package, release_authorized=True)
    with pytest.raises(ClearedSourceExportError):
        replace(package, native_executable_compiled=True)
    with pytest.raises(ClearedSourceExportError):
        replace(package, package_content_sha256="f"*64)
    path = export_rights_aware_desktop(package, tmp_path/"native", authorized=True)
    assert (path/"rights"/"CREDITS.md").is_file()
    assert (path/"rights"/"THIRD_PARTY_NOTICES.txt").is_file()
    assert (path/"rights"/"material_inventory.json").is_file()
    assert json.loads((path/"legal_review.json").read_text())["attribution_notices_embedded"] is True
    with pytest.raises(ClearedSourceExportError):
        compile_rights_aware_desktop(
            world, source, rights, credits=replace(credits, project_id="unrelated"),
            authorized=True,
        )
    with pytest.raises(ClearedSourceExportError):
        compile_rights_aware_desktop(
            world, source, rights, credits=generate(), authorized=True,
        )



def test_attribution_notices_are_immutable_and_cannot_fake_license_clearance():
    original = generate(materials=(own(),), credits=())
    with pytest.raises(CreditsError):
        replace(original, credits_md=original.credits_md + "\nnew, unreviewed author claim")
    with pytest.raises(CreditsError):
        replace(original, third_party_notices_txt="tampered")
    with pytest.raises(CreditsError):
        replace(original, bundle_sha256="f"*64)
    with pytest.raises(CreditsError):
        replace(original, release_authorized=True)
    with pytest.raises(CreditsError):
        replace(original, licensed_material_independently_cleared=True)
    with pytest.raises(CreditsError):
        replace(original, target_platform_id="sega_dreamcast")
