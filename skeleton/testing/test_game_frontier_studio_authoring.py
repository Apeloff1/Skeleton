"""Real functional acceptance for all 50 Forge Studio authoring operations.

The acceptance criterion is a changed StudioProject source state, not the
existence or passing status of another quality gate. The host test writes
actual game files through the original Godot export compiler.
"""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from skeleton.forge.game_frontier_studio import (
    StudioError, StudioEvent, StudioPrefab, StudioPlacement, StudioProject,
    StudioQuest, StudioQuestStage, MapLayer, compile_studio_project,
    compile_studio_native_quest_graph,
)
from skeleton.forge.game_frontier_studio_authoring import (
    AUTHORING_ACTIONS, apply_authoring_batch, authored_tile_region,
    execute_authoring, project_digest, authored_summary,
)
from skeleton.forge.game_frontier_studio_document import (
    authored_document, load_authored_document, create_authoring_project,
)
from skeleton.jeeves.game_frontier_worlds import ProjectionMode, WorldFamily
from skeleton.jeeves.game_frontier_expedition_generation import ArchipelagoProfile
from skeleton.jeeves.game_frontier_studio_authoring_tools import studio_authoring_handlers
from skeleton.jeeves.game_studio_tools import StudioCommand, studio_command_catalog

A = "a" * 64
B = "b" * 64


def project():
    layer = MapLayer(
        "base", 4, 4, ("grass", "stone", "water", "unused"),
        (0, 1, 2, 0,
         2, 1, 0, 0,
         0, 0, 2, 1,
         1, 0, 0, 0),
    )
    details = MapLayer("details", 4, 4, ("empty", "flower"),
                       (-1,) * 16, elevation_m=0.5)
    return StudioProject(
        "testgame", "tile", ProjectionMode.FULL_3D, WorldFamily.ORIGINAL,
        layers=(layer, details),
        prefabs=(
            StudioPrefab("tree", "foliage", "tile", A),
            StudioPrefab("merchant", "npc", "tile", A, "dialogue"),
            StudioPrefab("unused", "prop", "tile", A),
        ),
        placements=(
            StudioPlacement("tree", 1.0, 1.0, 0),
            StudioPlacement("merchant", 3, 2, 0),
        ),
        events=(
            StudioEvent("opening", "interact", "", True,
                        "show_dialogue", "tree", "Welcome"),
        ),
        native_quests=(
            StudioQuest("welcome", "Welcome", "first",
                        (StudioQuestStage("first", "Find a harbor"),)),
        ),
        soundtrack_ids=("theme", "ambient"),
    )


MAP = {
    "tile_set": {"layer": "base", "x": 0, "y": 0, "tile": 2},
    "rect_fill": {"layer": "base", "x": 0, "y": 0, "width": 2, "height": 2, "tile": 2},
    "line_draw": {"layer": "base", "x": 0, "y": 0, "x2": 3, "y2": 3, "tile": 1},
    "ellipse_fill": {"layer": "base", "x": 0, "y": 0, "width": 3, "height": 3, "tile": 1},
    "flood_fill": {"layer": "details", "x": 0, "y": 0, "tile": 1},
    "replace_tile": {"layer": "base", "before": 0, "after": 1},
    "checker_fill": {"layer": "base", "x": 0, "y": 0, "width": 4, "height": 4, "a": 1, "b": 2},
    "stamp": {"layer": "base", "x": 0, "y": 0, "width": 2, "height": 2,
              "tiles": [1, -1, 2, 1]},
    "region_paste": {"layer": "base", "x": 0, "y": 0, "width": 2, "height": 2,
                     "tiles": [-1, 1, 1, 2]},
    "shift_layer": {"layer": "base", "dx": 1, "dy": 0, "wrap": False},
    "flip_horizontal": {"layer": "base"},
    "flip_vertical": {"layer": "base"},
    "rotate_90": {"layer": "base", "clockwise": True},
    "layer_add": {"layer": "new", "width": 3, "height": 2,
                  "palette": ["dirt", "gravel"], "fill": 0},
    "layer_remove": {"layer": "details"},
    "layer_duplicate": {"layer": "base", "new_layer": "duplicate"},
    "layer_reorder": {"layer": "base", "position": 1},
    "layer_elevation": {"layer": "base", "elevation_m": 14.5},
    "palette_add": {"layer": "base", "value": "lava"},
    "palette_replace": {"layer": "base", "index": 1, "value": "shale"},
    "palette_swap": {"layer": "base", "a": 0, "b": 1},
    "palette_remove": {"layer": "base", "index": 3},
    "layer_resize": {"layer": "base", "width": 5, "height": 4, "fill": -1},
    "layer_crop": {"layer": "base", "x": 1, "y": 1, "width": 2, "height": 2},
    "layer_clear": {"layer": "base"},
}

OBJECTS = {
    "prefab_add": {"prefab_id": "pond", "kind": "liquid", "era": "tile", "asset_digest": B},
    "prefab_remove": {"prefab_id": "unused"},
    "prefab_clone": {"prefab_id": "tree", "new_prefab_id": "tree_alt"},
    "prefab_retarget": {"prefab_id": "tree", "asset_digest": B},
    "prefab_interaction": {"prefab_id": "tree", "interaction_type": "pickup"},
    "placement_add": {"prefab_id": "tree", "x": 4, "y": 4, "z": 0},
    "placement_remove": {"index": 0},
    "placement_move": {"index": 0, "x": 2, "y": 5, "z": 1},
    "placement_rotate": {"index": 0, "degrees": 90},
    "placement_duplicate": {"index": 0, "dx": 3, "dy": 3, "dz": 1},
    "placement_mirror": {"index": 0, "axis": "x", "pivot": 0},
    "placement_grid": {"prefab_id": "tree", "x": 0, "y": 0, "z": 0,
                       "columns": 2, "rows": 3, "dx": 1, "dy": 2},
    "event_add": {"event_id": "intro", "trigger": "enter", "action": "play_audio",
                  "target": "tree", "value": "theme"},
    "event_remove": {"event_id": "opening"},
    "event_condition": {"event_id": "opening", "condition_flag": "door_open",
                        "condition_value": False},
    "event_action": {"event_id": "opening", "action": "play_audio",
                     "target": "merchant", "value": "theme"},
    "event_trigger": {"event_id": "opening", "trigger": "weather"},
    "quest_add": {"quest_id": "newquest", "stage_id": "begin",
                  "title": "New Quest", "objective": "Find the sky island"},
    "quest_remove": {"quest_id": "welcome"},
    "quest_stage_append": {"quest_id": "welcome", "from_stage_id": "first",
                           "stage_id": "second", "objective": "Defeat the guardian"},
    "quest_objective": {"quest_id": "welcome", "stage_id": "first",
                        "objective": "Reach the floating citadel"},
    "quest_title": {"quest_id": "welcome", "title": "A Different Story"},
    "soundtrack_add": {"soundtrack_id": "combat"},
    "soundtrack_remove": {"soundtrack_id": "ambient"},
    "soundtrack_reorder": {"soundtrack_id": "theme", "position": 1},
}
PARAMETERS = {**MAP, **OBJECTS}
assert len(MAP) == 25 and len(OBJECTS) == 25


class RealForgeStudioAuthoringTests(unittest.TestCase):
    def test_first_fifty_distinct_supported_game_edits(self):
        self.assertEqual(100, len(AUTHORING_ACTIONS))
        self.assertEqual(50, len(PARAMETERS))
        self.assertTrue(set(PARAMETERS) <= set(AUTHORING_ACTIONS))

    def test_batch_edits_real_tile_geometry_quest_and_actor(self):
        original = project()
        old_digest = project_digest(original)
        changes = [
            {"action": "rect_fill", "parameters": MAP["rect_fill"]},
            {"action": "placement_add", "parameters": OBJECTS["placement_add"]},
            {"action": "quest_stage_append", "parameters": OBJECTS["quest_stage_append"]},
            {"action": "soundtrack_add", "parameters": OBJECTS["soundtrack_add"]},
        ]
        result = apply_authoring_batch(original, changes)
        new = result["project"]
        self.assertNotEqual(old_digest, project_digest(new))
        self.assertEqual(2, new.layers[0].data[0])
        self.assertEqual(3, len(new.placements))
        self.assertEqual(2, len(new.native_quests[0].stages))
        self.assertEqual("combat", new.soundtrack_ids[-1])
        self.assertEqual(1, len(compile_studio_native_quest_graph(new)["quests"]))
        self.assertEqual(4, result["receipt"]["action_count"])
        self.assertEqual(old_digest, project_digest(original))

    def test_rollback_on_bad_step_keeps_source_unchanged(self):
        original = project()
        digest = project_digest(original)
        with self.assertRaises(StudioError):
            apply_authoring_batch(original, [
                {"action": "tile_set", "parameters": MAP["tile_set"]},
                {"action": "prefab_remove", "parameters": {"prefab_id": "tree"}},
            ])
        self.assertEqual(digest, project_digest(original))

    def test_actual_copy_paste_and_tile_metadata(self):
        old = project()
        selection = authored_tile_region(old, "base", x=1, y=0, width=2, height=2)
        self.assertEqual([1, 2, 1, 0], selection["tiles"])
        new = execute_authoring(old, "region_paste", {
            "layer": "details", "x": 0, "y": 0, "width": 2, "height": 2,
            "tiles": [1, 1, 1, 0],
        })
        self.assertEqual((1, 1), new.layers[1].data[:2])
        self.assertNotEqual(project_digest(old), project_digest(new))

    def test_layer_rotation_dimensions_and_pixels(self):
        original = project()
        rotated = execute_authoring(original, "rotate_90", {"layer": "base"})
        self.assertEqual(original.layers[0].height, rotated.layers[0].width)
        self.assertEqual(original.layers[0].width, rotated.layers[0].height)
        self.assertEqual(original.layers[0].data[0], rotated.layers[0].data[3])
        restored = execute_authoring(rotated, "rotate_90", {
            "layer": "base", "clockwise": False})
        self.assertEqual(original.layers[0].data, restored.layers[0].data)

    def test_invalid_placement_grid_cannot_overallocate(self):
        with self.assertRaises(StudioError):
            execute_authoring(project(), "placement_grid", {
                **OBJECTS["placement_grid"], "columns": 128, "rows": 128})

    def test_typed_json_project_survives_real_save_reload(self):
        original = project()
        record = authored_document(original)
        loaded = load_authored_document(record, project_id="testgame")
        self.assertIsInstance(loaded, StudioProject)
        self.assertEqual(project_digest(original), project_digest(loaded))
        self.assertEqual(original.layers, loaded.layers)
        self.assertEqual(original.native_quests, loaded.native_quests)
        self.assertEqual(original.events, loaded.events)
        changed = execute_authoring(loaded, "quest_stage_append",
                                   OBJECTS["quest_stage_append"])
        reloaded = load_authored_document(
            authored_document(changed), project_id="testgame")
        self.assertEqual(2, len(reloaded.native_quests[0].stages))

    def test_json_rejects_foreign_or_modified_project_source(self):
        original = project()
        source = authored_document(original)
        with self.assertRaises(StudioError):
            load_authored_document(source, project_id="foreign")
        tampered = source.replace('"candidate_not_executed"', '"production_approved"')
        with self.assertRaises(StudioError):
            load_authored_document(tampered, project_id="testgame")

    def test_default_workspace_game_can_really_be_painted(self):
        blank = create_authoring_project("newgame", width=6, height=4)
        self.assertEqual((6, 4), (blank.layers[0].width, blank.layers[0].height))
        filled = execute_authoring(blank, "rect_fill", {
            "layer": "ground", "x": 1, "y": 1,
            "width": 3, "height": 2, "tile": 2})
        self.assertEqual(2, filled.layers[0].data[1 * 6 + 1])
        self.assertNotEqual(project_digest(blank), project_digest(filled))
        self.assertEqual(project_digest(filled), project_digest(
            load_authored_document(authored_document(filled), project_id="newgame")))

    def test_host_authorized_edit_persists_and_rechecks_generation(self):
        state = {"revision": 4, "value": project()}
        def load():
            return state["revision"], state["value"]
        def commit(project_id, revision, digest, new_project):
            if (project_id != "testgame" or revision != state["revision"]
                    or digest != project_digest(state["value"])):
                return False
            state["value"] = new_project
            state["revision"] += 1
            return True
        handlers = studio_authoring_handlers(
            {"testgame": load}, commit_project=commit,
        )
        catalog = studio_command_catalog()
        self.assertIn("game.studio.author.edit", catalog["write_operations"])
        self.assertIn("game.studio.author.preview", catalog["read_operations"])
        before = project_digest(state["value"])
        request = {"expected_revision": 4, "expected_sha256": before,
                   "steps": [{"action": "tile_set", "parameters": MAP["tile_set"]}]}
        preview = StudioCommand("game.studio.author.preview", "testgame", request)
        self.assertFalse(handlers[preview.operation](preview, None)["persisted"])
        self.assertEqual(4, state["revision"])
        command = StudioCommand("game.studio.author.edit", "testgame", request)
        stored = handlers[command.operation](command, None)
        self.assertTrue(stored["persisted"])
        self.assertEqual(5, state["revision"])
        self.assertEqual(2, state["value"].layers[0].data[0])
        with self.assertRaises(StudioError):
            handlers[command.operation](command, None)
        summary = StudioCommand("game.studio.author.inspect", "testgame", {})
        self.assertEqual(5, handlers[summary.operation](summary, None)["generation"])
        clip = StudioCommand("game.studio.author.copy", "testgame", {
            "layer": "base", "x": 0, "y": 0, "width": 1, "height": 1})
        self.assertEqual([2], handlers[clip.operation](clip, None)["tiles"])
        compiled = StudioCommand("game.studio.author.compile", "testgame", {})
        output = handlers[compiled.operation](compiled, None)
        self.assertEqual(project_digest(state["value"]), output["content_sha256"])
        self.assertTrue(output["compiled"])

    def test_host_export_real_playable_godot_project_without_overwrite(self):
        original = project()
        with TemporaryDirectory() as folder:
            handlers = studio_authoring_handlers(
                {"testgame": lambda: (0, original)},
                game_profiles={"testgame": ArchipelagoProfile(
                    seed=42, islands=4, caverns=0, include_underwater=False,
                    include_portals=False)},
                export_root=Path(folder),
            )
            game = StudioCommand("game.studio.author.game", "testgame", {})
            game_report = handlers[game.operation](game, None)
            self.assertGreater(game_report["waypoint_count"], 4)
            self.assertGreater(game_report["travel_edge_count"], 4)
            export = StudioCommand("game.studio.author.export", "testgame", {"folder": "authored"})
            exported = handlers[export.operation](export, None)
            self.assertTrue(exported["exported"])
            self.assertTrue((Path(folder) / "authored" / "project.godot").is_file())
            with self.assertRaises(Exception):
                handlers[export.operation](export, None)


def _functional_edit_test(operation):
    def test(self):
        source = project()
        result = execute_authoring(source, operation, PARAMETERS[operation])
        self.assertIsInstance(result, StudioProject)
        self.assertNotEqual(project_digest(source), project_digest(result),
                            f"{operation} must actually change game content")
        self.assertEqual("testgame", result.project_id)
        self.assertEqual("testgame", compile_studio_project(result)["project_id"])
    return test


for _name in AUTHORING_ACTIONS:
    setattr(RealForgeStudioAuthoringTests,
            "test_actual_" + _name, _functional_edit_test(_name))


if __name__ == "__main__":
    unittest.main()
