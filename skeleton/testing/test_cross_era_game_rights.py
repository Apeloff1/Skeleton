"""Executable cross-era game rights, fidelity and portability admission."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

from skeleton.ai.runtime.game_platform_catalog import (
    TARGETS, CATALOG_SHA256, GamePlatformError, catalog_summary,
    plan_game_targets,
)
from skeleton.ai.runtime.game_rights import (
    GameRightsError, SCHEMA as RIGHTS_SCHEMA, admit_game_rights,
)
from skeleton.ai.runtime.game_project_capsule import (
    GameCapsuleError, make_game_capsule, verify_game_capsule,
)
from skeleton.ai.runtime.gameplay_capabilities import compile_level
from scripts.game.game_project import main as game_cli


TILES = [
    "#######",
    "#S...G#",
    "#.....#",
    "#.....#",
    "#######",
]


def rights(
    tiles=TILES, *, source_kind="original", allowed_uses=None,
    third_party=False, protected=False, trademark=False,
    source_game=None, sdk=None,
):
    return {
        "schema_version": RIGHTS_SCHEMA,
        "project_id": "clean-game",
        "title": "Independent original map",
        "rights_contact": "author-asserted-unverified",
        "assets": [{
            "asset_id": "tilemap",
            "sha256": compile_level({"tiles": tiles})["tile_digest"],
            "source_kind": source_kind,
            "licensor": "author-asserted-unverified",
            "license_reference": "original-work-v1"
            if source_kind == "original" else "written-license-reference-2026",
            "allowed_uses": (
                ["embed", "modify", "distribute"]
                if allowed_uses is None else allowed_uses
            ),
            "contains_third_party_content": third_party,
            "contains_trademarks": trademark,
            "contains_technological_protection": protected,
        }],
        "source_game_reference": source_game,
        "sdk_authorization": sdk,
    }


def capsule(*, edits=None, target_ids=None, manifest=None, action="original_game"):
    return make_game_capsule(
        source_tiles=TILES,
        rights_manifest=rights() if manifest is None else manifest,
        target_ids=(
            ["game-boy", "nes-famicom", "playstation-5", "windows-11"]
            if target_ids is None else target_ids
        ),
        required_features=["tile2d", "input"],
        action=action,
        jurisdiction="NO",
        edits=edits,
    )


def _resign(c):
    import hashlib
    clone = {
        key: val for key, val in c.items()
        if key not in ("capsule_sha256", "capsule_bytes")
    }
    payload = json.dumps(
        clone, sort_keys=True, separators=(",", ":"),
        ensure_ascii=True, allow_nan=False,
    ).encode("ascii")
    c["capsule_sha256"] = hashlib.sha256(payload).hexdigest()
    c["capsule_bytes"] = len(payload)
    return c


def test_catalog_represents_over_150_named_systems_and_all_historical_eras():
    assert len(TARGETS) >= 150
    report = catalog_summary()
    assert report["target_count"] == len(TARGETS)
    assert report["catalog_sha256"] == CATALOG_SHA256
    assert len(report["eras"]) == 8
    assert all(number >= 2 for number in report["eras"].values())
    assert report["native_console_exporter_count"] == 0
    assert report["catalog_equivalent_to_native_platform_support"] is False
    assert report["distribution_law_verified"] is False
    assert report["ready_own_original_universal_scene_json"] is True
    for platform in (
        "edsac-oxo", "pdp1-spacewar", "atari-2600", "nes-famicom",
        "commodore-64", "zx-spectrum", "amiga-ocs", "game-boy",
        "sega-genesis-mega-drive", "super-nintendo-snes",
        "playstation-1", "nintendo-64", "sega-dreamcast",
        "playstation-2", "original-xbox", "game-boy-advance",
        "nintendo-ds", "playstation-3", "xbox-360", "playstation-vita",
        "playstation-4", "nintendo-switch", "windows-11", "linux-desktop",
        "playstation-5", "xbox-series-x", "nintendo-switch-2",
        "steam-deck", "meta-quest", "android-modern", "ios-modern",
        "pico8", "playdate",
    ):
        assert platform in TARGETS
        row = TARGETS[platform].as_dict()
        assert row["native_export_implemented"] is False
        assert row["sdk_access_verified"] is False
        assert row["rights_clearance_certified"] is False
        assert row["real_hardware_validated"] is False


def test_platform_plan_never_conflates_intended_era_with_actual_native_build():
    plan = plan_game_targets(
        target_ids=["game-boy", "nintendo-switch-2", "playstation-5"],
        required_features=["tile2d", "input", "scene3d"],
        sdk_authorizations={"playstation-5": "local-signed-contract-reference"},
    )
    assert plan["native_binaries_ready"] == 0
    assert plan["rom_images_created"] == 0
    assert plan["training_examples_created"] == 0
    assert plan["design_only"] is True
    assert plan["targets"][0]["unmodeled_design_features"] == ["scene3d"]
    assert plan["targets"][1]["toolchain_authorization_review_required"] is True
    assert plan["targets"][2]["sdk_reference_attested"] is True
    assert plan["targets"][2]["sdk_independent_authorization_verified"] is False
    assert all(x["unimplemented_native_export_is_blocker"]
               and not x["export_approved"] for x in plan["targets"])


@pytest.mark.parametrize("targets, features", [
    ([], ["tile2d"]),
    (["unknown-console"], ["tile2d"]),
    (["game-boy", "game-boy"], ["tile2d"]),
    (["game-boy"], ["unsupported-feature"]),
    (["game-boy"], ["tile2d", "tile2d"]),
    (["game-boy"], [False]),
    (["game-boy"], "tile2d"),
])
def test_target_admission_fails_closed_for_false_or_repeated_claims(targets, features):
    with pytest.raises(GamePlatformError):
        plan_game_targets(target_ids=targets, required_features=features)


def test_original_game_rights_are_attested_not_declared_legally_certified():
    receipt = admit_game_rights(
        rights(), action="original_game", jurisdiction="NO",
    )
    assert receipt["asset_count"] == 1
    assert len(receipt["manifest_sha256"]) == 64
    assert receipt["rights_assertion_only"] is True
    assert receipt["legal_compliance_certified"] is False
    assert receipt["all_licenses_independently_verified"] is False
    assert receipt["distribution_authorized"] is False
    assert receipt["training_authorized"] is False
    assert receipt["human_legal_review_completed"] is False
    assert receipt["requires_human_review_for_release"] is True


@pytest.mark.parametrize("kind", [
    "pirated_rom", "leaked_sdk", "extracted_firmware",
    "unlicensed_commercial_asset", "circumvention_output",
    "unknown",
])
def test_known_prohibited_asset_sources_are_rejected(kind):
    with pytest.raises(GameRightsError):
        admit_game_rights(
            rights(source_kind=kind), action="original_game", jurisdiction="NO",
        )


def test_original_work_cannot_launder_third_party_content_or_protected_media():
    with pytest.raises(GameRightsError, match="original classification"):
        admit_game_rights(
            rights(third_party=True), action="original_game", jurisdiction="NO",
        )
    with pytest.raises(GameRightsError, match="protected"):
        admit_game_rights(
            rights(protected=True), action="original_game", jurisdiction="NO",
        )


def test_independent_recreation_cannot_embed_external_game_assets():
    with pytest.raises(GameRightsError, match="independent mechanics"):
        admit_game_rights(
            rights(source_kind="licensed", third_party=True),
            action="independent_mechanics", jurisdiction="NO",
        )
    with pytest.raises(GameRightsError, match="source-game dependency"):
        admit_game_rights(
            rights(source_game="1988 proprietary arcade game"),
            action="independent_mechanics", jurisdiction="NO",
        )


def test_modified_original_game_requires_source_reference_and_edit_rights():
    licensed = rights(
        source_kind="licensed", third_party=True,
        source_game="licensed-owner-work-1987",
        allowed_uses=["modify"],
    )
    result = admit_game_rights(
        licensed, action="modify_authorized", jurisdiction="NO",
    )
    assert result["action"] == "modify_authorized"
    assert result["legal_compliance_certified"] is False
    licensed["source_game_reference"] = None
    with pytest.raises(GameRightsError, match="identify"):
        admit_game_rights(
            licensed, action="modify_authorized", jurisdiction="NO",
        )


def test_research_observations_cannot_become_distributable_game_or_training_data():
    observations = rights(
        source_kind="interoperability_research",
        third_party=True, source_game="interoperability-study",
        allowed_uses=["modify"],
    )
    with pytest.raises(GameRightsError, match="permissions|interoperability"):
        admit_game_rights(observations, action="publish", jurisdiction="EEA")
    with pytest.raises(GameCapsuleError, match="segregated"):
        make_game_capsule(
            source_tiles=TILES, rights_manifest=observations,
            target_ids=["windows-11"], required_features=["tile2d"],
            action="interoperability_study", jurisdiction="EEA",
        )


def test_publication_with_trademarks_is_not_automatically_authorized():
    with pytest.raises(GameRightsError, match="trademark"):
        admit_game_rights(
            rights(trademark=True), action="publish", jurisdiction="US",
        )
    result = admit_game_rights(
        rights(), action="publish", jurisdiction="US",
    )
    assert result["distribution_authorized"] is False


def test_legitimate_original_capsule_contains_real_scene_and_modifiable_map():
    game = capsule(edits=[{"x": 3, "y": 2, "tile": "#"}])
    assert game["schema_version"] == "skeleton.game.portable_capsule.v1"
    assert len(game["capsule_sha256"]) == 64
    assert game["source_tilemap"] == TILES
    assert game["rights_manifest"]["assets"][0]["sha256"] == game["source_tile_sha256"]
    assert game["tilemap"][2][3] == "#"
    assert game["source_tile_sha256"] != game["edited_tile_sha256"]
    assert game["scene"]["solid_tiles_covered"] > 0
    assert game["scene"]["entities"][0]["kind"] == "controllable_actor"
    assert game["playability"]["grid_goal_reachable"] is True
    assert game["playability"]["actual_controller_replay_qualified"] == (
        game["playability"]["controller_search_status"] == "playable"
    )
    assert game["console_rom_or_native_export_generated"] is False
    assert game["legal_release_authorized"] is False
    assert game["training_examples_added"] == 0
    assert verify_game_capsule(game)["scene_recomputed"] is True


def test_capsule_same_inputs_produce_exact_same_identity_and_target_plan():
    a, b = capsule(), capsule()
    assert a == b
    assert a["capsule_sha256"] == b["capsule_sha256"]
    assert a["target_plan"]["requested_targets"] == 4
    assert a["target_plan"]["native_binaries_ready"] == 0


@pytest.mark.parametrize("bad", [
    [{"x": 1, "y": 1, "tile": "X"}],
    [{"x": True, "y": 1, "tile": "#"}],
    [{"x": 1, "y": 1, "tile": "#"}, {"x": 1, "y": 1, "tile": "."}],
    [{"x": -1, "y": 2, "tile": "."}],
    [{"x": 1, "y": 1, "tile": "."}],
    [{"x": 1, "y": 1, "tile": "#"}],
])
def test_malformed_or_source_destroying_modifications_are_rejected(bad):
    with pytest.raises(GameCapsuleError):
        capsule(edits=bad)


def test_capsule_cannot_be_reauthorized_with_self_recomputed_hashes():
    game = capsule()
    attacks = (
        lambda x: x.update({"legal_release_authorized": True}),
        lambda x: x["target_plan"]["targets"][0].update({
            "native_export_implemented": True, "export_approved": True,
        }),
        lambda x: x["rights_receipt"].update({
            "distribution_authorized": True,
        }),
        lambda x: x["scene"]["entities"][0].update({
            "position": {"x": 0, "y": 0},
        }),
        lambda x: x["source_tilemap"].__setitem__(2, "#######"),
        lambda x: x["modifications"].append(
            {"x": 3, "y": 2, "tile": "#"}
        ),
    )
    for attack in attacks:
        forged = copy.deepcopy(game)
        attack(forged)
        _resign(forged)
        with pytest.raises(GameCapsuleError):
            verify_game_capsule(forged)


def test_capsule_requires_source_hash_bound_to_rights_manifest():
    forged = rights()
    forged["assets"][0]["sha256"] = "f" * 64
    with pytest.raises(GameCapsuleError, match="tilemap rights"):
        capsule(manifest=forged)


def test_game_cli_creates_and_verifies_original_project_without_native_rom(
    tmp_path: Path, capsys,
):
    output = tmp_path / "portable-game.json"
    assert game_cli([
        "--demo-project", str(output), "--seed", "42",
        "--targets", "game-boy,super-nintendo-snes,playstation-5,windows-11",
    ]) == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["scene_recomputed"] is True
    assert summary["target_native_binaries_built"] == 0
    assert summary["no_native_console_binary_created"] is True
    source = json.loads(output.read_text("utf-8"))
    assert source["output_kind"] == "engine_neutral_json_project"
    assert source["rights_receipt"]["legal_compliance_certified"] is False
    assert game_cli(["--verify-capsule", str(output)]) == 0
    assert json.loads(capsys.readouterr().out)["scene_recomputed"] is True
    assert game_cli(["--demo-project", str(output)]) == 1
    assert "new file" in capsys.readouterr().err


def test_game_cli_plans_many_systems_but_does_not_mint_native_toolchains(
    tmp_path: Path, capsys,
):
    assert game_cli(["--catalog"]) == 0
    catalog = json.loads(capsys.readouterr().out)
    assert catalog["target_count"] >= 150
    inp = tmp_path / "targets.json"
    inp.write_text(json.dumps({
        "target_ids": ["atari-2600", "playstation-5", "windows-11"],
        "required_features": ["tile2d", "input"],
    }), "utf-8")
    assert game_cli(["--plan", str(inp)]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["requested_targets"] == 3
    assert report["native_binaries_ready"] == 0
    assert report["copyright_compliance_certified"] is False


def test_game_cli_rejects_duplicate_keys_symlinks_and_wrong_formats(
    tmp_path: Path, capsys,
):
    original = tmp_path / "duplicate.json"
    original.write_text(
        '{"target_ids":["game-boy"],"target_ids":["playstation-5"],'
        '"required_features":["tile2d"]}', encoding="utf-8",
    )
    assert game_cli(["--plan", str(original)]) == 1
    assert "duplicate" in capsys.readouterr().err
    symlink = tmp_path / "symlink.json"
    try:
        symlink.symlink_to(original)
    except OSError:
        pytest.skip("filesystem does not allow symlinks")
    assert game_cli(["--plan", str(symlink)]) == 1
    assert "regular" in capsys.readouterr().err
    assert game_cli(["--seed", "7", "--catalog"]) == 2


def test_original_data_bank_does_not_grow_when_modifying_projects(tmp_path: Path):
    root = Path(__file__).resolve().parents[2] / (
        "skeleton/ai/training/datasets/offline_foundations_v1"
    )
    before = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in root.iterdir() if path.is_file()
    }
    capsule(edits=[{"x": 2, "y": 2, "tile": "#"}])
    game_cli(["--demo-project", str(tmp_path / "original.json")])
    assert before == {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in root.iterdir() if path.is_file()
    }


def test_capsule_embeds_reviewable_rights_evidence_not_merely_an_opaque_hash():
    project = capsule()
    assert project["rights_manifest"]["schema_version"] == RIGHTS_SCHEMA
    assert len(project["rights_manifest"]["assets"]) == 1
    assert project["rights_manifest"]["assets"][0]["asset_id"] == "tilemap"
    assert project["rights_manifest"]["assets"][0]["sha256"] == project["source_tile_sha256"]
    assert verify_game_capsule(project)["scene_recomputed"] is True


def test_rehashed_attacker_modification_cannot_strip_embedded_license_permissions():
    game = capsule()
    attacks = [
        lambda p: p["rights_manifest"]["assets"][0].update({
            "allowed_uses": ["modify"],
        }),
        lambda p: p["rights_manifest"]["assets"][0].update({
            "source_kind": "licensed",
            "contains_third_party_content": True,
        }),
        lambda p: p["rights_manifest"]["assets"][0].update({
            "sha256": "f" * 64,
        }),
        lambda p: p["rights_manifest"].update({
            "source_game_reference": "unauthorized-1980s-reference",
        }),
        lambda p: p["rights_manifest"]["assets"][0].update({
            "contains_technological_protection": True,
        }),
        lambda p: p["rights_manifest"]["assets"][0].update({
            "license_reference": "fake-new-license",
        }),
    ]
    for change in attacks:
        forged = copy.deepcopy(game)
        change(forged)
        _resign(forged)
        with pytest.raises(GameCapsuleError):
            verify_game_capsule(forged)
