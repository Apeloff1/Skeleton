"""Adversarial native byte-intake for real file bundles, not paper receipts.

The MZ bytes here are synthetic test fixtures. They prove input consistency, NOT
Windows loader success. Actual executable/emulator runs need external evidence.
"""
from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
import json

import pytest

from skeleton.ai.game_builder.asset_credits import (
    compile_game_credits, export_game_credits,
)
from skeleton.ai.game_builder.legal_native_export import (
    compile_originality_gated_desktop, export_rights_aware_desktop,
)
from skeleton.ai.game_builder.legal_paths import (
    CreativeMode, HardwareAccessFacts, HomebrewLegalRequest,
    Jurisdiction, MaterialKind, MaterialRecord,
)
from skeleton.ai.game_builder.native_release_intake import (
    NativeIntakeError, verify_native_release_intake,
)
from skeleton.ai.game_builder.plagiarism_guard import (
    AssetDeclaration, AssetDisposition, AttributionStatus,
    ExpressionSample, UseBasis, audit_game_originality,
)
from skeleton.ai.game_builder.port_planner import HomebrewSource
from skeleton.ai.game_builder.playable_world import GameBuildIntent, generate_playable_world
from skeleton.ai.game_builder.release_assurance import (
    ReleaseCandidate, ReleaseChannel,
)


def _digest(b: bytes | str):
    return sha256(b.encode() if isinstance(b,str) else b).hexdigest()


def _setup(tmp_path):
    project = "another-new-original"
    proof = "a"*64
    art = "b"*64
    world = generate_playable_world(GameBuildIntent(
        project_id=project,title="Original Arcade Odyssey",
        subtitle="Author-owned characters",seed=20261010,width=11,height=11,
        levels=1,collectibles_per_level=1,hazards_per_level=0,
    ), authorized=True)
    authored_text = (
        "A floating lantern observed unfamiliar constellations over the violet "
        "desert while a silent stone creature sketched an original map."
    )
    unlike = (
        "The engineer installed wooden bridges over a crystal river and "
        "carefully counted the distant fishing boats at dawn."
    )
    categories = (
        "source_code", "artwork", "music_audio", "characters",
        "story_dialogue", "level_maps", "interface_appearance", "marketing_brand",
    )
    assets = tuple(AssetDeclaration(
        modality=m,
        disposition=AssetDisposition.INCLUDED if m=="story_dialogue" else AssetDisposition.NOT_USED,
        basis=UseBasis.OWN_CREATION if m=="story_dialogue" else None,
        provenance_sha256=art if m=="story_dialogue" else None,
        author_identity="actual-game-author" if m=="story_dialogue" else None,
        attribution=AttributionStatus.NOT_REQUIRED,
    ) for m in categories)
    orig = audit_game_originality(
        project, assets=assets,
        candidate_samples=(ExpressionSample("our-story","story_dialogue",authored_text,art),),
        references=(ExpressionSample("unrelated","story_dialogue",unlike),),
        artifact_sha256=world.digest,
    )
    assert orig.design_admissible
    material = MaterialRecord("script","story_dialogue",MaterialKind.ORIGINAL_EXPRESSION,art)
    credits = compile_game_credits(
        project,"windows_modern",materials=(material,),third_party=(),
        original_authors=("actual-game-author",),
    )
    source = HomebrewSource(
        project,"sega_dreamcast","project_owned",proof,
        ("new expressive title","independently developed game"),
    )
    facts = HomebrewLegalRequest(
        project_id=project,source_platform_id="sega_dreamcast",
        target_platform_id="windows_modern",mode=CreativeMode.ORIGINAL,
        jurisdictions=(Jurisdiction.NO,Jurisdiction.EU_EEA),
        materials=(material,),hardware=HardwareAccessFacts(),
        rights_packet_sha256=proof,originality_report=orig,
    )
    native = compile_originality_gated_desktop(
        world, source, facts,originality=orig,credits=credits,authorized=True,
    )
    root = export_rights_aware_desktop(native,tmp_path/"src",authorized=True)
    # Synthetic DOS/PE magic *only*. Real compiler validation is deliberately
    # never inferred from these bytes.
    binary_bytes = b"MZ" + b"\x00"*2046
    binary = tmp_path/"game.exe"
    binary.write_bytes(binary_bytes)
    build = tmp_path/"build-evidence.json"
    build.write_text(json.dumps({
        "schema":"synthetic-evidence-v1",
        "binary_sha256":_digest(binary_bytes),
        "actual_compiler_execution_verified":False,
    }))
    play = tmp_path/"gameplay-evidence.json"
    play.write_text(json.dumps({
        "schema":"synthetic-evidence-v1",
        "world_sha256":world.digest,
        "actual_native_execution_verified":False,
    }))
    candidate = ReleaseCandidate(
        project_id=project,target_platform_id="windows_modern",
        world_sha256=world.digest,
        native_source_sha256=native.project.content_digest,
        native_binary_sha256=_digest(binary_bytes),
        rights_evidence_sha256=source.evidence_sha256,
        legal_assessment_sha256=native.assessment.assessment_digest,
        originality_screen_sha256=orig.screen_digest,
        credits_bundle_sha256=credits.bundle_sha256,
        channel=ReleaseChannel.DIRECT_DOWNLOAD,
        jurisdictions=("NO","EU_EEA"),
        author_ids=("actual-game-author",),builder_ids=("native-build-operator",),
        native_build_evidence_sha256=_digest(build.read_bytes()),
        native_gameplay_evidence_sha256=_digest(play.read_bytes()),
    )
    return {
        "source_directory":root,"compiled_binary":binary,
        "build_evidence":build,"gameplay_evidence":play,
        "candidate":candidate,"legal":native.assessment,
        "originality":orig,"credits":credits,
    }


def test_real_native_files_are_bound_to_source_rights_and_binary_bytes(tmp_path):
    inputs = _setup(tmp_path)
    receipt = verify_native_release_intake(**inputs)
    assert receipt.candidate_sha256 == inputs["candidate"].digest
    assert receipt.native_binary_sha256 == _digest(inputs["compiled_binary"].read_bytes())
    assert receipt.native_source_sha256 == inputs["candidate"].native_source_sha256
    assert receipt.rights_notices_sha256 == inputs["credits"].bundle_sha256
    assert receipt.bound_world_sha256 == inputs["candidate"].world_sha256
    assert len(receipt.byte_verified_files) == 10
    assert receipt.bin_bytes == 2048
    assert receipt == verify_native_release_intake(**inputs)
    assert receipt.file_bytes_verified is True
    assert receipt.compiler_execution_verified is False
    assert receipt.emulator_or_hardware_execution_verified is False
    assert receipt.copyrights_independently_verified is False
    assert receipt.release_authorized is False
    d = json.loads(receipt.to_json())
    assert d["schema"] == "skeleton.game_builder.native_byte_intake.v1"
    assert d["release_authorized"] is False


@pytest.mark.parametrize("filename",[
    "game.c","CMakeLists.txt","manifest.json",
    "legal_review.json","rights/CREDITS.md","rights/THIRD_PARTY_NOTICES.txt",
    "rights/material_inventory.json",
])
def test_modified_project_files_cannot_inherit_old_native_clearance(tmp_path,filename):
    inputs = _setup(tmp_path)
    target = inputs["source_directory"] / filename
    target.write_bytes(target.read_bytes() + b"\npost-review change")
    with pytest.raises(NativeIntakeError):
        verify_native_release_intake(**inputs)


@pytest.mark.parametrize("field",["compiled_binary","build_evidence","gameplay_evidence"])
def test_modified_real_binary_build_or_replay_blocks_old_signatures(tmp_path,field):
    inputs = _setup(tmp_path)
    target = inputs[field]
    target.write_bytes(target.read_bytes() + b"x")
    with pytest.raises(NativeIntakeError):
        verify_native_release_intake(**inputs)


def test_mismatched_binary_format_cannot_be_fixed_by_forging_hash(tmp_path):
    inputs = _setup(tmp_path)
    data = b"not-a-native-executable" + b"\x00"*2048
    inputs["compiled_binary"].write_bytes(data)
    inputs["candidate"] = replace(inputs["candidate"],native_binary_sha256=_digest(data))
    with pytest.raises(NativeIntakeError,match="binary header"):
        verify_native_release_intake(**inputs)


def test_changed_declared_review_jurisdictions_fail_even_with_matching_files(tmp_path):
    inputs = _setup(tmp_path)
    inputs["candidate"] = replace(inputs["candidate"],jurisdictions=("US",))
    with pytest.raises(NativeIntakeError,match="provenance"):
        verify_native_release_intake(**inputs)


def test_changed_rights_or_originality_evidence_rejected(tmp_path):
    inputs = _setup(tmp_path)
    inputs["candidate"] = replace(inputs["candidate"],rights_evidence_sha256="f"*64)
    with pytest.raises(NativeIntakeError):
        verify_native_release_intake(**inputs)


def test_native_game_directory_symlink_is_not_followed(tmp_path):
    inputs = _setup(tmp_path)
    original = inputs["source_directory"]
    linked = tmp_path/"linked"
    linked.symlink_to(original, target_is_directory=True)
    inputs["source_directory"] = linked
    with pytest.raises(NativeIntakeError):
        verify_native_release_intake(**inputs)


def test_native_content_symlink_is_not_followed(tmp_path):
    inputs = _setup(tmp_path)
    path = inputs["source_directory"]/"game.c"
    original = inputs["source_directory"]/"hidden.c"
    path.rename(original)
    path.symlink_to(original)
    with pytest.raises(NativeIntakeError):
        verify_native_release_intake(**inputs)


def test_binary_symlink_is_refused(tmp_path):
    inputs = _setup(tmp_path)
    linked = tmp_path/"linked.exe"
    linked.symlink_to(inputs["compiled_binary"])
    inputs["compiled_binary"] = linked
    with pytest.raises(NativeIntakeError):
        verify_native_release_intake(**inputs)


def test_missing_credit_directory_or_gameplay_evidence_fails_closed(tmp_path):
    inputs = _setup(tmp_path)
    (inputs["source_directory"]/"rights"/"CREDITS.md").unlink()
    with pytest.raises(NativeIntakeError):
        verify_native_release_intake(**inputs)


def test_required_intake_receipt_cannot_forge_hardware_or_legal_certification(tmp_path):
    receipt = verify_native_release_intake(**_setup(tmp_path))
    for flag in ("release_authorized","copyrights_independently_verified",
                 "compiler_execution_verified","emulator_or_hardware_execution_verified"):
        with pytest.raises(NativeIntakeError):
            replace(receipt, **{flag:True})



def test_symlinked_parent_directory_of_binary_is_rejected(tmp_path):
    inputs = _setup(tmp_path)
    alias = tmp_path / "compiled-artifacts"
    alias.symlink_to(tmp_path, target_is_directory=True)
    inputs["compiled_binary"] = alias / "game.exe"
    with pytest.raises(NativeIntakeError):
        verify_native_release_intake(**inputs)


def test_symlinked_parent_directory_of_build_evidence_is_rejected(tmp_path):
    inputs = _setup(tmp_path)
    alias = tmp_path / "untrusted-evidence"
    alias.symlink_to(tmp_path, target_is_directory=True)
    inputs["build_evidence"] = alias / "build-evidence.json"
    with pytest.raises(NativeIntakeError):
        verify_native_release_intake(**inputs)


def test_relative_ancestor_traversal_in_native_file_path_is_rejected(tmp_path):
    inputs = _setup(tmp_path)
    inputs["compiled_binary"] = (
        inputs["source_directory"] / ".." / "game.exe"
    )
    with pytest.raises(NativeIntakeError):
        verify_native_release_intake(**inputs)
