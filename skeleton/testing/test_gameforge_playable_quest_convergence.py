"""Executable Godot archetype sidecars and original native quests in one build.

No external engine, network, model provider or project publication is used.
This is a focused source and emit qualification, not native device validation.
"""
from __future__ import annotations

from copy import deepcopy

import pytest

from backend.routes.skeleton_gameforge import RunRequest, run
from skeleton.ai.game_builder.godot_quest_bridge import verify_native_quest
from skeleton.context import pipeline
from skeleton.forge.archetype_content import (
    COMPLETE_MARKER,
    FAILED_MARKER,
    archetype_files,
    attach_archetype_content,
    content_archetypes,
)
from skeleton.forge.eras import compile_era
from skeleton.forge.gdscript_check import check_ok
from skeleton.forge.godot_emit import emit_godot
from skeleton.forge.source_manifest import source_manifest
from skeleton.forge.playable_portal import SCRIPT_PATH, verify_playable_portal


def base() -> dict[str, str]:
    return emit_godot(compile_era("extraction_now"))


@pytest.mark.parametrize("archetype", content_archetypes())
def test_each_gameplay_archetype_produces_actual_godot_loop_scripts(archetype: str) -> None:
    original = base()
    frozen = deepcopy(original)
    generated = attach_archetype_content(original, archetype)
    assert original == frozen
    assert len(generated) == len(original) + 3
    expected = archetype_files(archetype)
    assert set(expected).issubset(generated)
    assert all(generated[name] == body for name, body in expected.items())
    assert COMPLETE_MARKER in generated[f"scripts/archetypes/{archetype}/core_loop.gd"]
    assert FAILED_MARKER in generated[f"scripts/archetypes/{archetype}/core_loop.gd"]
    assert "func _physics_process" in generated[f"scripts/archetypes/{archetype}/player_controller.gd"]
    loop = generated[f"scripts/archetypes/{archetype}/core_loop.gd"]
    assert "ForgeGameplayHUD" in loop and "TouchControls" in loop
    assert "func _draw_objectives() -> void:" in loop
    assert "func _hud_status() -> String:" in loop
    assert "draw_circle(player.global_position" in loop
    assert 'Input.action_press(action)' in loop
    assert 'Input.action_release(action)' in loop
    assert 'DisplayServer.get_name() == "headless"' in loop
    if archetype in {"crafting", "puzzle", "racing", "stealth", "survival"}:
        assert '_add_direction(controls, "ui_accept", "USE",' in loop
        assert '"ui_right", "ui_accept"]' in loop
        assert "if not finished and hud_label != null:" in loop
    assert "CharacterBody2D" in generated[f"scenes/archetypes/{archetype}/main.tscn"]
    ok, problems = check_ok(generated)
    assert ok, problems
    manifest = source_manifest(generated)
    assert manifest["file_count"] == len(generated)


def test_eight_real_playable_scene_prototypes_not_158_engines() -> None:
    assert content_archetypes() == (
        "combat_loop", "crafting", "extraction", "pipeline", "puzzle",
        "racing", "stealth", "survival",
    )
    generated = attach_archetype_content(base(), "auto")
    assert "scenes/archetypes/extraction/main.tscn" in generated
    assert "scenes/archetypes/auto/main.tscn" not in generated


def test_playable_archetype_and_native_room_quest_coexist_at_emit(monkeypatch) -> None:
    monkeypatch.setattr(pipeline, "_commit", lambda *args, **kwargs: None)
    before = base()
    ctx = {
        "era": "extraction_now", "target": "godot",
        "archetype": "pipeline", "files": deepcopy(before),
        "playable_content": True, "quest_content": True, "quest_length": 5,
        "project_root": None, "playtest_mode": "off",
    }
    response = pipeline._stage_emit(ctx)
    assert response["emitted"] is True
    assert ctx["playable_archetype"] == "pipeline"
    assert ctx["native_quest_receipt"]["steps"] == 5
    assert ctx["native_quest_receipt"]["replay_verified"] is True
    assert verify_native_quest(ctx["files"])
    assert "scenes/archetypes/pipeline/main.tscn" in ctx["files"]
    assert verify_playable_portal(ctx["files"], "pipeline")
    assert ctx["playable_portal_receipt"]["return_supported"] is True
    assert ctx["playable_portal_receipt"]["headless_inert"] is True
    assert SCRIPT_PATH in ctx["files"]
    assert ctx["file_count"] == len(before) + 3 + 1 + 2
    assert source_manifest(ctx["files"])["file_count"] == len(before) + 3 + 1 + 2
    ok, problems = check_ok(ctx["files"])
    assert ok, problems


def test_no_playable_opt_in_keeps_source_outputs_unchanged(monkeypatch) -> None:
    monkeypatch.setattr(pipeline, "_commit", lambda *args, **kwargs: None)
    originals = base()
    ctx = {
        "era": "extraction_now", "target": "godot",
        "archetype": "pipeline", "files": dict(originals),
        "project_root": None, "playtest_mode": "off",
    }
    pipeline._stage_emit(ctx)
    assert ctx["files"] == originals
    assert "playable_archetype" not in ctx
    assert "native_quest_receipt" not in ctx


def test_http_route_forwards_both_independent_opt_ins_and_defaults(monkeypatch) -> None:
    from skeleton.context.pipeline import GameForgeRun
    seen: list[dict] = []

    class Stub:
        def execute(self, vision, **kwargs):
            seen.append(kwargs)
            return {"succeeded": True, "files": {"project.godot": "fixture"}}

    monkeypatch.setattr(GameForgeRun, "live", lambda: Stub())
    baseline = run(RunRequest(vision="An original game"))
    assert baseline["succeeded"]
    assert "playable_content" not in seen[-1]
    assert "quest_content" not in seen[-1]
    combined = run(RunRequest(
        vision="An original game", archetype="pipeline", target="godot",
        playable_content=True, quest_content=True, quest_length=5,
        operator_axes={"tempo": 0.61},
    ))
    assert combined["succeeded"]
    assert seen[-1]["playable_content"] is True
    assert seen[-1]["quest_content"] is True
    assert seen[-1]["quest_length"] == 5
    assert seen[-1]["operator_axes"] == {"tempo": 0.61}


def test_json_target_cannot_generate_native_playable_scenes():
    from skeleton.context.pipeline import GameForgeRun
    with pytest.raises(ValueError, match="Godot target"):
        GameForgeRun().execute(
            "An original blueprint", target="json",
            playable_content=True,
        )


@pytest.mark.parametrize("archetype,axes,expected", [
    ("extraction", {"tempo": 0.0, "risk": 1.0, "scarcity": 1.0, "agency": 0.0},
     ("speed: float = 195.0", "HEAT_PER_SECOND := 10.00", "HEAT_LIMIT := 70.00", "PICKUP_RADIUS := 8.00")),
    ("combat_loop", {"tempo": 1.0, "lethality": 1.0, "grind": 1.0, "agency": 1.0},
     ("speed: float = 300.0", "CONTACT_DAMAGE := 5", "WAVES := 5", "ATTACK_RANGE := 40.00")),
    ("pipeline", {"tempo": 0.0, "risk": 1.0, "grind": 1.0, "agency": 1.0},
     ("speed: float = 240.0", "MAX_FRAMES := 3600", "QUOTA := 8", "RADIUS := 20.00")),
])
def test_operator_knobs_generate_distinct_native_mechanics(archetype, axes, expected):
    from skeleton.forge.archetype_content import archetype_files, verify_archetype_content
    tuned = archetype_files(archetype, operator_axes=axes)
    baseline = archetype_files(archetype)
    assert tuned != baseline
    source = tuned[f"scripts/archetypes/{archetype}/core_loop.gd"]
    player = tuned[f"scripts/archetypes/{archetype}/player_controller.gd"]
    assert expected[0] in player
    assert all(part in source for part in expected[1:])
    attached = attach_archetype_content(base(), archetype, operator_axes=axes)
    assert verify_archetype_content(attached, archetype, operator_axes=axes)
    assert not verify_archetype_content(attached, archetype)


@pytest.mark.parametrize("invalid", [
    {"risk": float("nan")}, {"tempo": float("inf")}, {"risk": -0.001},
    {"tempo": 1.001}, {"agency": True}, {"unsupported": 0.5},
    {f"axis_{i}": 0.5 for i in range(11)},
])
def test_native_mechanics_reject_unbounded_or_unknown_axes(invalid):
    from skeleton.forge.archetype_content import archetype_files
    with pytest.raises(ValueError):
        archetype_files("extraction", operator_axes=invalid)


def test_final_mechanics_attestation_rejects_quest_writer_modification(monkeypatch):
    from skeleton.ai.game_builder import godot_quest_bridge
    monkeypatch.setattr(pipeline, "_commit", lambda *args, **kwargs: None)
    original = godot_quest_bridge.attach_native_quest

    def tamper(files, *, length=3):
        generated, receipt = original(files, length=length)
        generated["scripts/archetypes/pipeline/core_loop.gd"] += "\n# tamper"
        return generated, receipt

    monkeypatch.setattr(godot_quest_bridge, "attach_native_quest", tamper)
    ctx = {
        "era": "extraction_now", "target": "godot", "archetype": "pipeline",
        "playable_content": True, "quest_content": True,
        "operator_axes": {"tempo": 0.8, "grind": 1.0},
        "files": base(), "playtest_mode": "off", "project_root": None,
    }
    with pytest.raises(RuntimeError, match="final native playable mechanics verification failed"):
        pipeline._stage_emit(ctx)


@pytest.mark.parametrize("mode,axes,expected", [
    ("extraction", {"tempo": 0.0, "grind": 1.0, "risk": 1.0, "scarcity": 1.0, "agency": 0.0,
                    "authorial": 0.5},
     {"player.speed": 195.0, "extraction.caches_required": 6.0, "extraction.heat_per_second": 10.0,
      "extraction.heat_limit": 70.0, "extraction.pickup_radius": 8.0}),
    ("combat_loop", {"tempo": 1.0, "lethality": 1.0, "grind": 1.0, "agency": 1.0, "authorial": 0.5},
     {"player.speed": 300.0, "combat_loop.contact_damage": 5.0, "combat_loop.waves": 5.0,
      "combat_loop.attack_range": 40.0}),
    ("pipeline", {"tempo": 0.0, "risk": 1.0, "grind": 1.0, "agency": 1.0, "scarcity": 0.0,
                  "authorial": 0.5},
     {"player.speed": 240.0, "pipeline.frame_budget": 3600.0, "pipeline.shipment_quota": 8.0,
      "pipeline.interaction_radius": 20.0, "pipeline.cargo_capacity": 3.0}),
])
def test_original_native_modes_seal_effective_literals_and_unmapped_axes(mode, axes, expected):
    import json
    from skeleton.forge.playable_tuning import SOURCE_PATH
    from skeleton.forge.archetype_content import verify_archetype_content
    files = archetype_files(mode, operator_axes=axes)
    receipt = json.loads(files[SOURCE_PATH])
    assert receipt["mode"] == mode
    assert receipt["axes"] == axes
    assert receipt["applied"] == expected
    assert receipt["mapped_axes"] == sorted(set(axes) - {"authorial"})
    assert receipt["unmapped_axes"] == ["authorial"]
    assert verify_archetype_content(files, mode, operator_axes=axes)
    receipt["applied"]["player.speed"] = -1
    files[SOURCE_PATH] = json.dumps(receipt)
    assert not verify_archetype_content(files, mode, operator_axes=axes)


@pytest.mark.parametrize("mode", content_archetypes())
def test_all_modes_reserve_tuning_artifact_and_deny_unexpected_authority(mode):
    from skeleton.forge.playable_tuning import SOURCE_PATH
    from skeleton.forge.archetype_content import verify_archetype_content
    baseline = archetype_files(mode)
    assert SOURCE_PATH not in baseline
    assert verify_archetype_content(baseline, mode)
    assert not verify_archetype_content({**baseline, SOURCE_PATH: "{}"}, mode)
    with pytest.raises(ValueError, match="tuning receipt collides"):
        attach_archetype_content({**base(), SOURCE_PATH.upper(): "{}"}, mode)
    tuned = archetype_files(mode, operator_axes={"authorial": 0.5})
    assert not verify_archetype_content(tuned, mode)
    assert verify_archetype_content(tuned, mode, operator_axes={"authorial": 0.5})
    assert not verify_archetype_content({**tuned, SOURCE_PATH.upper(): tuned[SOURCE_PATH]},
                                        mode, operator_axes={"authorial": 0.5})


def test_emit_original_native_receipt_matches_exact_source_manifest(monkeypatch):
    import json
    from skeleton.forge.playable_tuning import SOURCE_PATH
    monkeypatch.setattr(pipeline, "_commit", lambda *args, **kwargs: None)
    ctx = {
        "era": "extraction_now", "target": "godot", "archetype": "pipeline",
        "files": base(), "playable_content": True, "project_root": None,
        "playtest_mode": "off", "operator_axes": {"grind": 1.0, "scarcity": 0.0, "authorial": 1.0},
    }
    assert pipeline._stage_emit(ctx)["emitted"]
    receipt = json.loads(ctx["files"][SOURCE_PATH])
    assert receipt == ctx["playable_tuning_receipt"]
    assert receipt["applied"] == {"pipeline.cargo_capacity": 3.0, "pipeline.shipment_quota": 8.0}
    assert ctx["playable_mechanics_receipt"]["applied_axes"] == {"grind": 1.0, "scarcity": 0.0}
    assert SOURCE_PATH in source_manifest(ctx["files"])["files"]


@pytest.mark.parametrize("paths", [
    {"project.godot": "ok", "Assets": "leaf", "assets/item.txt": "child"},
    {"project.godot": "ok", "assets/item.txt": "child", "Assets": "leaf"},
    {"project.godot": "ok", "Assets/a.txt": "a", "assets/b.txt": "b"},
    {"project.godot": "ok", "assets/../bad.txt": "bad"},
    {"project.godot": "ok", "assets/invalid.txt": "\ud800"},
    {"assets/item.txt": "missing project"},
    {"project.godot": "ok", 7: "foreign key"},
    {"project.godot": "ok", "assets/item.txt": None},
])
def test_portable_server_source_budget_rejects_invalid_inventories(paths):
    from backend.routes.skeleton_gameforge import _portable_source_size
    assert _portable_source_size(paths) is None


def test_portable_server_source_byte_count_is_bounded_and_unicode_exact(monkeypatch):
    from backend.routes import skeleton_gameforge as route
    assert route._portable_source_size({"project.godot": "å😀", "data/a.txt": "界"}) == 9
    monkeypatch.setattr(route, "_MAX_PORTABLE_SOURCE_BYTES", 8)
    assert route._portable_source_size({"project.godot": "界" * 3}) is None
    assert route._portable_source_size({"project.godot": "a" * 9}) is None
    assert route._portable_source_size({"project.godot": "a" * 8}) == 8
    monkeypatch.setattr(route, "_MAX_PORTABLE_ZIP_BYTES", 24)
    assert route._portable_source_size({"project.godot": "ok"}) is None


def _portable_zip(files, *, compression=0):
    import io
    import zipfile
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=compression) as archive:
        for name, body in files:
            archive.writestr(name, body)
    return stream.getvalue()


@pytest.mark.parametrize("mode", content_archetypes())
def test_portable_zip_reopens_exact_native_source_without_execution(tmp_path, mode):
    from scripts.verify_gameforge_source_zip import reopen_archive
    files = attach_archetype_content(base(), mode, operator_axes={"tempo": 0.5, "grind": 0.75})
    digest = source_manifest(files)["sha256"]
    archive = tmp_path / "project.zip"
    archive.write_bytes(_portable_zip(sorted(files.items())))
    report = reopen_archive(archive, digest)
    assert report["source_manifest"] == source_manifest(files)
    assert report["source_verified"] and not report["native_execution_qualified"]
    assert report["reopened"] is False
    output = tmp_path / "reopened"
    report = reopen_archive(archive, digest, output)
    assert report["reopened"]
    assert {p.relative_to(output).as_posix(): p.read_bytes().decode("utf-8")
            for p in output.rglob("*") if p.is_file()} == files


@pytest.mark.parametrize("damage", ["foreign_digest", "truncated_digest", "changed_source",
                                    "duplicate", "traversal", "directory_alias", "file_directory",
                                    "invalid_unicode", "compressed", "missing_project"])
def test_portable_zip_rejects_invalid_source_without_creating_output(tmp_path, damage):
    import zipfile
    from scripts.verify_gameforge_source_zip import PortableSourceError, reopen_archive
    files = {"project.godot": "config_version=5", "data/x.txt": "original"}
    digest = source_manifest(files)["sha256"]
    rows = list(files.items())
    compression = zipfile.ZIP_STORED
    if damage == "foreign_digest":
        digest = "f" * 64
    elif damage == "truncated_digest":
        digest = digest[:16]
    elif damage == "changed_source":
        rows[-1] = ("data/x.txt", "modified")
    elif damage == "duplicate":
        rows.append(("data/x.txt", "duplicate"))
    elif damage == "traversal":
        rows.append(("../private.txt", "bad"))
    elif damage == "directory_alias":
        rows.append(("Data/y.txt", "alias"))
    elif damage == "file_directory":
        rows.append(("data", "leaf"))
    elif damage == "invalid_unicode":
        rows[-1] = ("data/x.txt", bytes([255]))
    elif damage == "compressed":
        compression = zipfile.ZIP_DEFLATED
    elif damage == "missing_project":
        rows = rows[1:]
    archive = tmp_path / "bad.zip"
    if damage == "duplicate":
        with pytest.warns(UserWarning, match="Duplicate name"):
            archive.write_bytes(_portable_zip(rows, compression=compression))
    else:
        archive.write_bytes(_portable_zip(rows, compression=compression))
    output = tmp_path / "not-created"
    with pytest.raises(PortableSourceError):
        reopen_archive(archive, digest, output)
    assert not output.exists()


def test_portable_zip_does_not_replace_existing_project(tmp_path):
    from scripts.verify_gameforge_source_zip import PortableSourceError, reopen_archive
    files = {"project.godot": "config_version=5"}
    archive = tmp_path / "source.zip"
    archive.write_bytes(_portable_zip(files.items()))
    destination = tmp_path / "existing"
    destination.mkdir()
    marker = destination / "project.godot"
    marker.write_text("original", encoding="utf-8")
    with pytest.raises(PortableSourceError, match="already exists"):
        reopen_archive(archive, source_manifest(files)["sha256"], destination)
    assert marker.read_text(encoding="utf-8") == "original"


@pytest.mark.parametrize("damage", ["prefix", "suffix", "local_crc", "local_flags",
                                    "local_size", "local_name", "central_offset",
                                    "central_disk"])
def test_portable_zip_rejects_hidden_or_divergent_container_bytes(damage):
    import struct
    from scripts.verify_gameforge_source_zip import PortableSourceError, inspect_archive
    files = {"project.godot": "config_version=5", "data/x.txt": "valid"}
    raw = bytearray(_portable_zip(files.items()))
    if damage == "prefix":
        raw = bytearray(b"hidden-prefix") + raw
    elif damage == "suffix":
        raw.extend(b"hidden-suffix")
    elif damage == "local_crc":
        struct.pack_into("<I", raw, 14, 0)
    elif damage == "local_flags":
        struct.pack_into("<H", raw, 6, 8)
    elif damage == "local_size":
        struct.pack_into("<I", raw, 18, 0)
    elif damage == "local_name":
        raw[30] = ord("P")
    elif damage == "central_offset":
        end = len(raw) - 22
        struct.pack_into("<I", raw, end + 16, struct.unpack_from("<I", raw, end + 16)[0] - 1)
    elif damage == "central_disk":
        end = len(raw) - 22
        struct.pack_into("<H", raw, end + 6, 1)
    with pytest.raises(PortableSourceError):
        inspect_archive(bytes(raw), source_manifest(files)["sha256"])


def test_portable_zip_refuses_symlink_and_nonregular_input(tmp_path):
    from scripts.verify_gameforge_source_zip import PortableSourceError, reopen_archive
    files = {"project.godot": "config_version=5"}
    archive = tmp_path / "source.zip"
    archive.write_bytes(_portable_zip(files.items()))
    alias = tmp_path / "alias.zip"
    try:
        alias.symlink_to(archive)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable on this host")
    with pytest.raises(PortableSourceError, match="regular file"):
        reopen_archive(alias, source_manifest(files)["sha256"])
    with pytest.raises(PortableSourceError, match="not a file"):
        reopen_archive(tmp_path, source_manifest(files)["sha256"])


@pytest.mark.parametrize("mode", content_archetypes())
def test_portable_project_inspection_reconciles_native_template(mode):
    from scripts.verify_gameforge_source_zip import inspect_archive
    files = attach_archetype_content(base(), mode, operator_axes={"tempo": 0.5, "grind": 0.75})
    _, receipt = inspect_archive(_portable_zip(sorted(files.items())), source_manifest(files)["sha256"])
    inspection = receipt["project_inspection"]
    assert inspection["native_template"] == "verified"
    assert inspection["tuning"] == "verified"
    assert inspection["current_template_compatible"]
    assert not inspection["native_execution_qualified"]
    assert inspection["playable_modes"] == [mode]


def test_portable_project_verifies_galaxy_override_and_profile_without_execution():
    from scripts.verify_gameforge_source_zip import inspect_archive
    from skeleton.context.galaxy_profile import (
        MATRIX_FIELDS, SCHEMA, attach_galaxy_profile, compile_galaxy_playable_axes,
        seal_galaxy_playable_controls,
    )
    from skeleton.forge.playable_portal import attach_playable_portal
    config = {name: {} for name in MATRIX_FIELDS}
    config.update(title="Recovered factory", genre="simulation", narrative_phases={},
                  extra_params={}, style_params={})
    config["mechanics_matrix"]["building"] = {"count": 1000}
    profile = {"schema": SCHEMA, "config": config}
    axes, pending = compile_galaxy_playable_axes(profile, "pipeline", {"grind": 0.0})
    files = attach_archetype_content(base(), "pipeline", operator_axes=axes)
    files = attach_galaxy_profile(files, profile)
    files, _ = seal_galaxy_playable_controls(files, pending)
    _, receipt = inspect_archive(_portable_zip(sorted(files.items())), source_manifest(files)["sha256"])
    inspection = receipt["project_inspection"]
    assert inspection["galaxy_profile"] == "verified"
    assert inspection["galaxy_controls"] == "verified"
    assert inspection["mapped_matrix_dials"] == 1
    assert inspection["applied"]["pipeline.shipment_quota"] == 2
    assert inspection["current_template_compatible"]


@pytest.mark.parametrize("mutation", ["script", "duplicate_json", "foreign_mode", "invented_effect"])
def test_portable_project_preserves_historical_source_but_strict_mode_refuses(tmp_path, mutation):
    import json
    from scripts.verify_gameforge_source_zip import PortableSourceError, reopen_archive
    from skeleton.forge.playable_tuning import SOURCE_PATH
    files = attach_archetype_content(base(), "pipeline", operator_axes={"grind": 1.0})
    if mutation == "script":
        files["scripts/archetypes/pipeline/core_loop.gd"] += "\n# historical"
    elif mutation == "duplicate_json":
        files[SOURCE_PATH] = files[SOURCE_PATH].replace('"mode":"pipeline"', '"mode":"pipeline","mode":"pipeline"')
    else:
        receipt = json.loads(files[SOURCE_PATH])
        if mutation == "foreign_mode":
            receipt["mode"] = "racing"
        else:
            receipt["applied"]["pipeline.shipment_quota"] = 999
        files[SOURCE_PATH] = json.dumps(receipt)
    archive = tmp_path / "source.zip"
    archive.write_bytes(_portable_zip(sorted(files.items())))
    digest = source_manifest(files)["sha256"]
    report = reopen_archive(archive, digest)
    assert report["source_verified"]
    assert not report["project_inspection"]["current_template_compatible"]
    output = tmp_path / "strict"
    with pytest.raises(PortableSourceError, match="current native template"):
        reopen_archive(archive, digest, output, require_current_template=True)
    assert not output.exists()


def test_portable_zip_comparison_reports_source_changes_without_source_bodies(tmp_path):
    from scripts.verify_gameforge_source_zip import compare_archives
    before = {"project.godot": "config_version=5", "data/removed.txt": "private removed",
              "data/changed.txt": "private before", "data/same.txt": "same"}
    after = {"project.godot": "config_version=5", "data/added.txt": "private added",
             "data/changed.txt": "private after", "data/same.txt": "same"}
    left, right = tmp_path / "before.zip", tmp_path / "after.zip"
    left.write_bytes(_portable_zip(before.items()))
    right.write_bytes(_portable_zip(after.items()))
    result = compare_archives(left, source_manifest(before)["sha256"], right, source_manifest(after)["sha256"])
    assert result["counts"] == {"added": 1, "removed": 1, "modified": 1, "unchanged": 2}
    assert result["added"][0]["path"] == "data/added.txt"
    assert result["removed"][0]["path"] == "data/removed.txt"
    assert result["modified"][0]["path"] == "data/changed.txt"
    assert not result["source_identical"]
    assert not result["native_effects_comparable"] and result["native_effect_changes"] is None
    assert "private" not in str(result)


def test_portable_zip_comparison_reports_verified_native_literal_changes(tmp_path):
    from scripts.verify_gameforge_source_zip import compare_archives
    left, right = tmp_path / "old.zip", tmp_path / "new.zip"
    before = attach_archetype_content(base(), "pipeline", operator_axes={"grind": 0.0, "scarcity": 1.0})
    after = attach_archetype_content(base(), "pipeline", operator_axes={"grind": 1.0, "scarcity": 0.0})
    left.write_bytes(_portable_zip(sorted(before.items())))
    right.write_bytes(_portable_zip(sorted(after.items())))
    result = compare_archives(left, source_manifest(before)["sha256"], right, source_manifest(after)["sha256"])
    assert result["native_effects_comparable"]
    assert result["native_effect_changes"] == [
        {"effect": "pipeline.cargo_capacity", "before": 1.0, "after": 3.0},
        {"effect": "pipeline.shipment_quota", "before": 2.0, "after": 8.0},
    ]
    assert not result["native_execution_qualified"]


def test_portable_zip_comparison_requires_both_independent_identities(tmp_path):
    from scripts.verify_gameforge_source_zip import PortableSourceError, compare_archives
    files = {"project.godot": "config_version=5"}
    archive = tmp_path / "project.zip"
    archive.write_bytes(_portable_zip(files.items()))
    digest = source_manifest(files)["sha256"]
    with pytest.raises(PortableSourceError, match="SHA-256 mismatch"):
        compare_archives(archive, digest, archive, "0" * 64)
    same = compare_archives(archive, digest, archive, digest)
    assert same["source_identical"]
    assert same["counts"] == {"added": 0, "removed": 0, "modified": 0, "unchanged": 1}


def test_portable_zip_comparison_cli_is_read_only(tmp_path, capsys):
    import json
    from scripts.verify_gameforge_source_zip import main
    files = {"project.godot": "config_version=5"}
    archive = tmp_path / "project.zip"
    archive.write_bytes(_portable_zip(files.items()))
    digest = source_manifest(files)["sha256"]
    args = [str(archive), "--expected-sha256", digest, "--compare-zip", str(archive), "--compare-sha256", digest]
    assert main(args) == 0
    assert json.loads(capsys.readouterr().out)["source_identical"]
    output = tmp_path / "refused"
    with pytest.raises(SystemExit) as refused:
        main(args + ["--output", str(output)])
    assert refused.value.code == 2
    assert not output.exists()
