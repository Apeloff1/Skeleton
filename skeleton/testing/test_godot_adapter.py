"""Conformance tests for the Godot adapter boundary (#950)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from skeleton.frontier.world import WorldBounds, WorldRegion
from skeleton.game.mechanics import CombatStyle, CombatSystemSpec, MechanicType
from skeleton.organism.gamespec import SCHEMA as GAMESPEC_SCHEMA
from skeleton.platform.godot_adapter import (
    ADAPTER_INPUT_SCHEMA,
    ADAPTER_SCHEMA,
    ADAPTER_VERSION,
    FOOTPRINT_POLICY,
    REPO_GODOT_BINARY,
    REPO_GODOT_EMIT,
    REPO_GODOT_ENGINE_PACKAGE,
    GodotAdapter,
    GodotAdapterError,
    GodotAdapterView,
    GodotUnsupportedFeatureError,
    GodotVersionError,
    adapt_document,
    inventory_godot_footprint,
    map_combat_style,
    map_godot_region_to_world,
    map_node_type_to_occupant,
    map_occupant_kind,
    map_world_region,
    materialise_pack,
    project_document,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "godot_adapter"
REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_adapter_versions_are_explicit_and_stable():
    adapter = GodotAdapter()
    assert adapter.schema == ADAPTER_SCHEMA == "platform.godot_adapter.v1"
    assert adapter.schema_version == ADAPTER_VERSION == 1
    assert ADAPTER_INPUT_SCHEMA == "platform.godot_adapter.input.v1"


def test_adapter_instance_rejects_foreign_versions():
    with pytest.raises(GodotVersionError, match="not this boundary"):
        GodotAdapter(schema="platform.godot_adapter.v0")


def test_occupant_mapping_is_deterministic_and_round_trips():
    expected = {
        "player": "CharacterBody2D",
        "enemy": "CharacterBody2D",
        "extract": "Area2D",
        "heat": "Area2D",
        "loot": "Marker2D",
    }
    for kind, node_type in expected.items():
        assert map_occupant_kind(kind) == node_type
        assert map_node_type_to_occupant(node_type=node_type, primitive=kind) == kind


def test_unknown_occupant_and_mismatched_projection_fail_closed():
    with pytest.raises(GodotUnsupportedFeatureError) as unknown:
        map_occupant_kind("vehicle")
    assert unknown.value.code == "PLT.GODOT_UNSUPPORTED"
    assert unknown.value.context["feature"] == "occupant_kind"

    with pytest.raises(GodotUnsupportedFeatureError, match="occupant projection"):
        map_node_type_to_occupant(node_type="RigidBody3D", primitive="player")


def test_supported_combat_styles_map_to_continuous_2d():
    assert map_combat_style(CombatStyle.REAL_TIME) == "continuous_2d"
    assert map_combat_style("action") == "continuous_2d"


def test_unsupported_combat_and_mechanic_types_fail_with_typed_diagnostics():
    with pytest.raises(GodotUnsupportedFeatureError) as combat:
        map_combat_style(CombatStyle.TURN_BASED)
    assert combat.value.context["feature"] == "combat_style"
    assert "turn_based" in combat.value.context["style"]

    with pytest.raises(GodotUnsupportedFeatureError) as stealth:
        adapt_document(
            {
                "schema": ADAPTER_INPUT_SCHEMA,
                "schema_version": 1,
                "game": {
                    "combat_style": "real_time",
                    "mechanic_types": [MechanicType.STEALTH.value],
                },
            }
        )
    assert stealth.value.context["feature"] == "mechanic_type"


def test_bool_viewport_does_not_coerce_to_int():
    with pytest.raises(GodotAdapterError, match="must be an integer"):
        adapt_document(
            {
                "schema": ADAPTER_INPUT_SCHEMA,
                "schema_version": 1,
                "project": {
                    "title": "Nope",
                    "viewport_width": True,
                    "viewport_height": 720,
                },
            }
        )


def test_schema_version_true_does_not_equal_one():
    with pytest.raises(GodotVersionError):
        adapt_document(
            {
                "schema": ADAPTER_INPUT_SCHEMA,
                "schema_version": True,
                "project": {"title": "Nope", "viewport_width": 1280, "viewport_height": 720},
            }
        )


def test_engine_globals_in_core_contracts_fail_closed():
    with pytest.raises(GodotUnsupportedFeatureError) as err:
        adapt_document(
            {
                "schema": ADAPTER_INPUT_SCHEMA,
                "schema_version": 1,
                "game": {
                    "combat_style": "real_time",
                    "autoload": "HeatSystem",
                },
            }
        )
    assert err.value.context["feature"] == "engine_global"


def test_unknown_document_fields_fail_closed():
    with pytest.raises(GodotUnsupportedFeatureError) as err:
        adapt_document(
            {
                "schema": ADAPTER_INPUT_SCHEMA,
                "schema_version": 1,
                "networking": {"mode": "enet"},
                "game": {"combat_style": "real_time"},
            }
        )
    assert err.value.context["feature"] == "unknown_fields"


def test_world_region_round_trips_without_engine_state():
    region = WorldRegion(
        id="harbor",
        name="Harbor",
        difficulty=2,
        bounds=WorldBounds(x=8, y=16, width=100, height=80),
        dangers=("reef",),
    )
    node = map_world_region(region)
    assert node.node_type == "Node2D"
    assert node.position == (8.0, 16.0)
    assert node.size == (100.0, 80.0)
    restored = map_godot_region_to_world(node)
    assert restored.id == region.id
    assert restored.name == region.name
    assert restored.difficulty == region.difficulty
    assert restored.bounds == region.bounds
    assert restored.dangers == region.dangers


def test_region_points_of_interest_fail_closed_instead_of_dropping():
    region = WorldRegion(
        id="harbor",
        name="Harbor",
        difficulty=1,
        bounds=WorldBounds(0, 0, 10, 10),
        points_of_interest=({"name": "lighthouse"},),
    )
    with pytest.raises(GodotUnsupportedFeatureError, match="points_of_interest"):
        map_world_region(region)


def test_conformance_fixture_round_trips_supported_primitives():
    document = _load_fixture("conformance_v1.json")
    first = adapt_document(document)
    assert first.engine == "godot"
    assert first.project is not None
    assert first.project.config_version == 5
    assert first.project.features == ("4.3",)
    assert first.game is not None
    assert first.game.controller_family == "continuous_2d"
    occupant_types = {node.primitive: node.node_type for node in first.nodes if node.parent_id}
    assert occupant_types["player"] == "CharacterBody2D"
    assert occupant_types["enemy"] == "CharacterBody2D"
    assert occupant_types["extract"] == "Area2D"

    projected = project_document(first)
    second = adapt_document(projected)
    assert second.canonical_json() == first.canonical_json()
    assert projected["creator"]["schema"] == GAMESPEC_SCHEMA
    rooms = {room["id"]: room for room in projected["world"]["rooms"]}
    assert rooms["r00"]["kind"] == "spawn"
    assert rooms["r00"]["occupants"] == [{"kind": "player"}]
    assert rooms["r01"]["occupants"] == [{"kind": "enemy", "tier": "trash"}]


def test_canonical_json_is_byte_stable_across_calls():
    document = _load_fixture("conformance_v1.json")
    view = adapt_document(document)
    assert view.canonical_json() == GodotAdapter().adapt(document).canonical_json()
    assert '"schema":"platform.godot_adapter.v1"' in view.canonical_json()


def test_scene_state_payload_maps_2d_entities_without_importing_unmerged_world():
    payload = _load_fixture("scene_state_v1.json")
    view = adapt_document(
        {
            "schema": ADAPTER_INPUT_SCHEMA,
            "schema_version": 1,
            "world": payload,
        }
    )
    by_id = {node.node_id: node for node in view.nodes}
    assert by_id["room_spawn"].node_type == "Node2D"
    assert by_id["hero"].node_type == "CharacterBody2D"
    assert by_id["hero"].parent_id == "room_spawn"
    assert by_id["hero"].position == (16.0, 24.0)


def test_scene_state_3d_translation_fails_closed():
    payload = _load_fixture("scene_state_v1.json")
    payload["entities"]["hero"]["transform"]["translation"][2] = 4.0
    with pytest.raises(GodotUnsupportedFeatureError) as err:
        adapt_document(
            {
                "schema": ADAPTER_INPUT_SCHEMA,
                "schema_version": 1,
                "world": payload,
            }
        )
    assert err.value.context["feature"] == "translation_3d"


def test_unknown_scene_schema_version_fails_closed():
    with pytest.raises(GodotVersionError):
        adapt_document(
            {
                "schema": ADAPTER_INPUT_SCHEMA,
                "schema_version": 1,
                "world": {
                    "schema": "world.scene_state.v1",
                    "schema_version": 2,
                    "entities": {},
                },
            }
        )


def test_creator_intent_and_non_godot_platform_fail_closed():
    with pytest.raises(GodotUnsupportedFeatureError) as intent:
        adapt_document(
            {
                "schema": ADAPTER_INPUT_SCHEMA,
                "schema_version": 1,
                "creator": {"kind": "creator.intent.v1", "title": "Soon"},
            }
        )
    assert intent.value.context["feature"] == "creator_intent"

    with pytest.raises(GodotUnsupportedFeatureError) as platform:
        adapt_document(
            {
                "schema": ADAPTER_INPUT_SCHEMA,
                "schema_version": 1,
                "creator": {
                    "kind": "game-spec",
                    "schema": GAMESPEC_SCHEMA,
                    "vision": "unity port",
                    "platform": "unity",
                },
            }
        )
    assert platform.value.context["feature"] == "creator_platform"


def test_combat_system_spec_maps_without_rewriting_mechanics():
    spec = CombatSystemSpec(style=CombatStyle.ACTION, include_magic=False)
    view = adapt_document(
        {
            "schema": ADAPTER_INPUT_SCHEMA,
            "schema_version": 1,
            "game": spec,
        }
    )
    assert view.game is not None
    assert view.game.combat_style == "action"
    assert view.game.mechanic_types == ("combat",)
    assert spec.style is CombatStyle.ACTION


def test_adapter_module_has_no_hidden_engine_global_state():
    import skeleton.platform.godot_adapter as module

    assert "emit_godot" not in vars(module)
    mutable = [
        name
        for name, value in vars(module).items()
        if not name.startswith("__") and isinstance(value, (list, dict, set))
    ]
    assert mutable == []


def test_footprint_inventory_measures_and_does_not_propose_relocation():
    inventory = inventory_godot_footprint(REPO_ROOT)
    assert inventory.packaging_recommendation == FOOTPRINT_POLICY == "leave_in_place"
    assert inventory.relocate_binaries is False
    assert inventory.packaging_owner == "#1008 / GB-9"
    by_path = {entry.path: entry for entry in inventory.entries}
    assert by_path[REPO_GODOT_BINARY].kind == "binary"
    assert by_path[REPO_GODOT_BINARY].exists is True
    assert by_path[REPO_GODOT_BINARY].size_bytes > 50_000_000
    assert by_path[REPO_GODOT_ENGINE_PACKAGE].exists is True
    assert by_path[REPO_GODOT_EMIT].exists is True
    assert by_path[REPO_GODOT_EMIT].size_bytes > 1_000
    payload = inventory.to_payload()
    assert payload["relocate_binaries"] is False


def test_materialise_pack_wraps_emit_godot_without_becoming_the_contract():
    from skeleton.forge.eras import compile_era
    from skeleton.forge.godot_emit import emit_godot

    pack = compile_era("extraction_now")
    result = materialise_pack(pack, title="Adapter Wrap")
    direct = emit_godot(pack, title="Adapter Wrap")
    assert result.emitter == "skeleton.forge.godot_emit.emit_godot"
    assert "project.godot" in result.files
    assert sorted(result.files) == sorted(direct)
    assert result.files["project.godot"] == direct["project.godot"]
    assert result.view.schema == ADAPTER_SCHEMA
    assert result.view.project is not None
    assert result.view.project.title == "Adapter Wrap"
    assert "forge.godot_emit" in result.view.provenance
    assert "autoload" not in result.view.to_payload()
    assert "HeatSystem" not in result.view.canonical_json()


def test_materialise_pack_rejects_engine_globals_and_bool_viewport():
    with pytest.raises(GodotUnsupportedFeatureError, match="engine-global"):
        materialise_pack({"era": "extraction_now", "autoload": "GameState"})

    with pytest.raises(GodotAdapterError, match="must be an integer"):
        materialise_pack({"hardware": {"viewport": [True, 720]}})


def test_adapt_document_helpers_match_adapter_protocol():
    document = {
        "schema": ADAPTER_INPUT_SCHEMA,
        "schema_version": 1,
        "project": {"title": "Helper", "viewport_width": 640, "viewport_height": 480},
    }
    view = adapt_document(document)
    assert isinstance(view, GodotAdapterView)
    assert project_document(view)["project"]["title"] == "Helper"
