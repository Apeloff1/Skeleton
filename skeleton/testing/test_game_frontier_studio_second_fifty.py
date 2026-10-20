"""Functional 50-step second Forge Studio build acceptance.

These tests assert actual mutation of authored environmental RPG, active 3D
zones/forces, executable native quest graphs and procedural terrain pixels,
not existence of gate declarations. Older fifty remain separately covered.
"""
from __future__ import annotations

from dataclasses import replace
import unittest

from skeleton.forge.game_frontier_studio import (
    StudioError, StudioEvent, StudioForceField, StudioPlacement,
    StudioQuest, StudioQuestStage, StudioTriggerVolume,
    StudioProject, compile_studio_gameplay_force_fields,
    compile_studio_gameplay_zones, compile_studio_native_quest_graph,
)
from skeleton.forge.game_frontier_rpg_events import (
    EnvironmentalTrigger, RPGEventAction, RPGEventPage,
    evaluate_environment_events,
)
from skeleton.forge.game_frontier_studio_authoring import (
    AUTHORING_ACTIONS, apply_authoring_batch, execute_authoring, project_digest,
)
from skeleton.forge.game_frontier_studio_environment_edit import ENV_ACTIONS
from skeleton.forge.game_frontier_studio_physics_edit import PHYSICAL_ACTIONS
from skeleton.forge.game_frontier_studio_quest_terrain_edit import QUEST_ACTIONS, TERRAIN_ACTIONS
from skeleton.forge.game_frontier_studio_document import authored_document, load_authored_document
from skeleton.testing.test_game_frontier_studio_authoring import project as original_project

NEW_ACTIONS = ENV_ACTIONS + PHYSICAL_ACTIONS + QUEST_ACTIONS + TERRAIN_ACTIONS


def project(*, cyclic_start: bool = False) -> StudioProject:
    base = original_project()
    quest = StudioQuest(
        "journey", "Archipelago Journey", "first",
        (
            StudioQuestStage("first", "Leave harbor", ("second", "third")),
            StudioQuestStage("second", "Collect wind gem",
                             ("fourth", "first") if cyclic_start else ("fourth",)),
            StudioQuestStage("third", "Consult captain", ("fourth",)),
            StudioQuestStage("fourth", "Return home"),
        ),
    )
    event = RPGEventPage(
        "weather_event", 1,
        (EnvironmentalTrigger("temperature_c", "above", 10),
         EnvironmentalTrigger("humidity", "below", .5)),
        (RPGEventAction("set_flag", "world", "wind_warning", "true"),
         RPGEventAction("play_music", "audio", "weather", "ambient")),
        required_flags=(("ready", True),),
        cooldown_ms=10,
    )
    return replace(
        base,
        placements=base.placements + (StudioPlacement("tree", 6, 2, 0),),
        events=base.events + (
            StudioEvent("zone_entry", "enter", "", True, "show_dialogue", "tree", "Hello"),
            StudioEvent("zone_alt", "enter", "", True, "play_audio", "tree", "ambient"),
        ),
        environmental_pages=(event,),
        native_trigger_volumes=(
            StudioTriggerVolume("zone0", "tree:0", "zone_entry", 2., (0., 0., 0.)),
        ),
        native_gameplay_force_fields=(
            StudioForceField("wind0", "tree:0", "updraft", 5., 4., (0., 0., 0.)),
        ),
        native_quests=(quest,),
    )


ENV = {
    "environment_page_add": {"page_id": "new_weather", "signal": "wind_mps",
                             "comparison": "above", "threshold": 10.,
                             "kind": "set_flag", "channel": "world",
                             "target": "wind_alert", "value": "true"},
    "environment_page_remove": {"page_id": "weather_event"},
    "environment_page_clone": {"page_id": "weather_event", "new_page_id": "weather_alt"},
    "environment_page_priority": {"page_id": "weather_event", "priority": 22},
    "environment_page_enable": {"page_id": "weather_event", "enabled": False},
    "environment_page_repeat": {"page_id": "weather_event", "repeat": False},
    "environment_page_cooldown": {"page_id": "weather_event", "cooldown_ms": 15000},
    "environment_condition_add": {"page_id": "weather_event", "signal": "wind_mps",
                                  "comparison": "above", "threshold": 8.},
    "environment_condition_edit": {"page_id": "weather_event", "index": 0,
                                   "signal": "temperature_c", "comparison": "above",
                                   "threshold": 25.},
    "environment_condition_remove": {"page_id": "weather_event", "index": 1},
    "environment_action_add": {"page_id": "weather_event", "kind": "change_light",
                               "channel": "environment", "target": "sun", "value": "dim"},
    "environment_action_edit": {"page_id": "weather_event", "index": 0,
                                "kind": "play_music", "channel": "audio",
                                "target": "world", "value": "wind"},
    "environment_action_remove": {"page_id": "weather_event", "index": 1},
    "environment_flag_require": {"page_id": "weather_event", "flag": "storm_ready",
                                 "required": True},
    "environment_flag_clear": {"page_id": "weather_event", "flag": "ready"},
}
ZONE = {
    "zone_add": {"zone_id": "zone1", "actor_id": "tree:2", "event_id": "zone_entry",
                 "radius_m": 3, "x": 0, "y": 0, "z": 2},
    "zone_remove": {"zone_id": "zone0"},
    "zone_clone": {"zone_id": "zone0", "new_zone_id": "zone2"},
    "zone_bind_actor": {"zone_id": "zone0", "actor_id": "tree:2"},
    "zone_bind_event": {"zone_id": "zone0", "event_id": "zone_alt"},
    "zone_radius": {"zone_id": "zone0", "radius_m": 7},
    "zone_offset": {"zone_id": "zone0", "x": 1, "y": 1, "z": 2},
    "zone_translate": {"zone_id": "zone0", "dx": 1, "dy": 0, "dz": 3},
    "zone_scale": {"zone_id": "zone0", "factor": 2},
    "zone_duplicate_to_actor": {
        "zone_id": "zone0", "new_zone_id": "zone3", "new_actor_id": "tree:2",
    },
}
FIELD = {
    "field_add": {"field_id": "wind1", "actor_id": "tree:2", "kind": "vortex",
                  "radius_m": 10, "acceleration_mps2": 5, "x": 0, "y": 1, "z": 0},
    "field_remove": {"field_id": "wind0"},
    "field_clone": {"field_id": "wind0", "new_field_id": "wind2"},
    "field_bind_actor": {"field_id": "wind0", "actor_id": "tree:2"},
    "field_kind": {"field_id": "wind0", "kind": "vortex"},
    "field_radius": {"field_id": "wind0", "radius_m": 8},
    "field_strength": {"field_id": "wind0", "acceleration_mps2": 9},
    "field_offset": {"field_id": "wind0", "x": 1, "y": 3, "z": 0},
    "field_invert": {"field_id": "wind0"},
    "field_duplicate_to_actor": {
        "field_id": "wind0", "new_field_id": "wind3", "new_actor_id": "tree:2",
    },
}
QUEST = {
    "quest_stage_remove": {"quest_id": "journey", "stage_id": "third"},
    "quest_stage_link": {"quest_id": "journey", "from_stage_id": "second",
                         "to_stage_id": "third"},
    "quest_stage_unlink": {"quest_id": "journey", "from_stage_id": "second",
                           "to_stage_id": "fourth"},
    "quest_stage_split": {"quest_id": "journey", "from_stage_id": "second",
                          "to_stage_id": "fourth", "new_stage_id": "bridge",
                          "objective": "Cross the bridge"},
    "quest_stage_rename": {"quest_id": "journey", "stage_id": "third",
                           "new_stage_id": "captain"},
    "quest_start_change": {"quest_id": "journey", "stage_id": "second"},
    "quest_stage_swap_objectives": {"quest_id": "journey",
                                   "stage_a": "second", "stage_b": "third"},
    "quest_duplicate": {"quest_id": "journey", "new_quest_id": "journey2",
                        "title": "Alternate Sky Journey"},
    "quest_stage_reorder": {"quest_id": "journey", "stage_id": "second", "position": 0},
    "quest_rewrite_objectives": {"quest_id": "journey",
                                 "objectives": {"first": "Reach the sky tower",
                                                "third": "Learn wind navigation"}},
}
TERRAIN = {
    "terrain_noise": {"layer": "base", "x": 0, "y": 0, "width": 4, "height": 4,
                      "seed": 224, "a": 0, "b": 3, "percent_b": 85},
    "terrain_smooth": {"layer": "base", "x": 0, "y": 0, "width": 4, "height": 4,
                       "passes": 2},
    "terrain_terrace": {"layer": "base", "x": 0, "y": 0, "width": 4, "height": 4,
                        "bands": 2},
    "terrain_outline": {"layer": "base", "x": 0, "y": 0, "width": 4, "height": 4,
                        "target": 2, "replacement": 3},
    "terrain_erode": {"layer": "base", "x": 0, "y": 0, "width": 4, "height": 4,
                      "target": 0, "replacement": -1},
}
CASES = {**ENV, **ZONE, **FIELD, **QUEST, **TERRAIN}
assert len(CASES) == 50


class SecondFiftyFunctionalAcceptance(unittest.TestCase):
    def test_100_real_tools_exposed_after_second_pass(self):
        self.assertEqual(100, len(AUTHORING_ACTIONS))
        self.assertEqual(50, len(NEW_ACTIONS))
        self.assertEqual(set(NEW_ACTIONS), set(CASES))
        self.assertEqual(100, len(set(AUTHORING_ACTIONS)))

    def test_native_zone_exports_real_3d_positions(self):
        edited = execute_authoring(project(), "zone_translate", ZONE["zone_translate"])
        output = compile_studio_gameplay_zones(edited)
        self.assertEqual(1, output["zone_count"])
        self.assertEqual([2., 1., 3.], output["zones"][0]["center_xyz_m"])

    def test_force_fields_compile_real_bounded_native_physics(self):
        altered = execute_authoring(project(), "field_strength", FIELD["field_strength"])
        compiled = compile_studio_gameplay_force_fields(altered)
        self.assertEqual(1, compiled["field_count"])
        self.assertEqual(9., compiled["fields"][0]["acceleration_mps2"])

    def test_branch_split_compiles_through_native_quest_parser(self):
        edited = execute_authoring(project(), "quest_stage_split", QUEST["quest_stage_split"])
        compiled = compile_studio_native_quest_graph(edited)
        stages = compiled["quests"][0]["stages"]
        self.assertEqual(5, len(stages))
        self.assertIn("bridge", next(x for x in stages if x["id"] == "second")["next"])
        self.assertEqual(["fourth"], next(x for x in stages if x["id"] == "bridge")["next"])

    def test_environment_actions_change_actual_event_evaluation(self):
        before = project()
        after = execute_authoring(before, "environment_page_enable", ENV["environment_page_enable"])
        observation = {"temperature_c": 30, "humidity": .1}
        fired = evaluate_environment_events(
            before.environmental_pages, current=observation,
            flags={"ready": True}, now_ms=50000)
        blocked = evaluate_environment_events(
            after.environmental_pages, current=observation,
            flags={"ready": True}, now_ms=50000)
        self.assertTrue(fired.accepted)
        self.assertFalse(blocked.accepted)

    def test_deterministic_terrain_noise_same_seed_and_source(self):
        original = project()
        a = execute_authoring(original, "terrain_noise", TERRAIN["terrain_noise"])
        b = execute_authoring(original, "terrain_noise", TERRAIN["terrain_noise"])
        self.assertEqual(a.layers[0].data, b.layers[0].data)
        self.assertNotEqual(project_digest(original), project_digest(a))

    def test_full_source_document_survives_all_new_families(self):
        edited = project()
        for name in ("environment_page_priority", "zone_radius",
                     "field_strength", "quest_stage_rename", "terrain_terrace"):
            edited = execute_authoring(edited, name, CASES[name])
        reloaded = load_authored_document(authored_document(edited),
                                          project_id=edited.project_id)
        self.assertEqual(project_digest(edited), project_digest(reloaded))
        self.assertEqual(edited.environmental_pages, reloaded.environmental_pages)
        self.assertEqual(edited.native_trigger_volumes, reloaded.native_trigger_volumes)
        self.assertEqual(edited.native_gameplay_force_fields,
                         reloaded.native_gameplay_force_fields)

    def test_invalid_native_operation_rolls_back_entire_batch(self):
        original = project()
        with self.assertRaises(StudioError):
            apply_authoring_batch(original, [
                {"action": "terrain_noise", "parameters": TERRAIN["terrain_noise"]},
                {"action": "zone_bind_actor",
                 "parameters": {"zone_id": "zone0", "actor_id": "unowned:99"}},
            ])
        self.assertEqual(project_digest(original), project_digest(project()))

    def test_quest_reparent_rejects_unreachable_native_nodes(self):
        before = project()
        with self.assertRaises(StudioError):
            execute_authoring(before, "quest_stage_unlink", {
                "quest_id": "journey", "from_stage_id": "first", "to_stage_id": "third"})
        self.assertEqual(4, len(before.native_quests[0].stages))

    def test_invalid_zone_binding_cannot_change_actor_or_original(self):
        before = project()
        with self.assertRaises(StudioError):
            execute_authoring(before, "zone_bind_event", {
                "zone_id": "zone0", "event_id": "opening"})
        self.assertEqual("zone_entry", before.native_trigger_volumes[0].event_page_id)


def _functional_case(action):
    def check(self):
        base = project(cyclic_start=(action == "quest_start_change"))
        before = project_digest(base)
        changed = execute_authoring(base, action, CASES[action])
        self.assertIsInstance(changed, StudioProject)
        self.assertNotEqual(before, project_digest(changed),
                            action + " must modify real game source")
        self.assertEqual(before, project_digest(base))
        self.assertEqual(changed.project_id, "testgame")
        reloaded = load_authored_document(authored_document(changed),
                                          project_id="testgame")
        self.assertEqual(project_digest(changed), project_digest(reloaded))
    return check


for _action in NEW_ACTIONS:
    setattr(SecondFiftyFunctionalAcceptance, "test_real_" + _action,
            _functional_case(_action))


if __name__ == "__main__":
    unittest.main()
