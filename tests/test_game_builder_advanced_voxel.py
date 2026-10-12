"""Authoring, gameplay and adversarial evidence for original voxel milestone."""
from __future__ import annotations

from copy import deepcopy
import unittest

from skeleton.ai.game_builder.advanced_voxel_runtime import (
    VoxelActionError, default_layout, normalize_layout, start, step,
)
from skeleton.ai.game_builder.advanced_gameplay_runtime import (
    ENGINES, AdvancedRuntimeError, run_advanced_session, verify_advanced_session,
)
from skeleton.ai.game_builder.advanced_level_scenes import (
    SceneError, make_advanced_scene, validate_advanced_scene,
)
from skeleton.ai.game_builder.advanced_gameplay_save import (
    export_advanced_savegame, import_advanced_savegame, continue_advanced_savegame,
)
from skeleton.ai.game_builder.system_editors import (
    make_editor_document, catalog, SystemEditorError,
)
from skeleton.ai.game_builder.system_editor_assembly import compile_system_assembly


class OriginalVoxelEngineTests(unittest.TestCase):
    def config(self):
        return make_editor_document("voxel")["settings"]

    def test_advanced_editor_and_true_reference_runtime(self):
        self.assertIn("voxel", ENGINES)
        spec = next(s for s in catalog() if s["id"] == "voxel")
        self.assertEqual(spec["progression_floor"], "advanced")
        self.assertEqual(spec["runtime_maturity"], "advanced_reference_runtime")
        self.assertGreaterEqual(len(spec["fields"]), 18)

    def test_physical_mine_construct_and_replay(self):
        actions = ["mine", "place:soil", "light", "inspect", "rest"]
        receipt = run_advanced_session("voxel", actions=actions, seed=0)
        self.assertTrue(verify_advanced_session(receipt))
        state = receipt["state"]
        self.assertEqual(state["ore_mined"], 1)
        self.assertEqual(state["placed"], 1)
        self.assertEqual(state["inventory"]["ore"], 1)
        self.assertEqual(len(state["torches"]), 1)
        self.assertFalse(state["finished"])
        self.assertFalse(receipt["native_hardware_verified"])

    def test_material_conservation_and_disabled_mining(self):
        for command in ("mine:above", "place:stone", "checkpoint", "retire"):
            with self.assertRaises(AdvancedRuntimeError):
                run_advanced_session("voxel", actions=[command])
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("voxel", {"destruction": False}, actions=["mine"])
        with self.assertRaises(SystemEditorError):
            make_editor_document("voxel", {"ore_goal": 0})
        with self.assertRaises(SystemEditorError):
            make_editor_document("voxel", {"materials": 1.0})

    def test_sand_gravity_conserves_number_of_blocks(self):
        config = self.config()
        state = start(config, 0)
        initial = len(state["cells"])
        for _ in range(3):
            step(state, config, "wait")
        self.assertEqual(len(state["cells"]), initial)
        self.assertGreaterEqual(state["fallen_blocks"], 0)
        self.assertEqual(len({tuple(c[:3]) for c in state["cells"]}), initial)

    def test_author_scene_and_reject_injected_geometry(self):
        cfg = self.config()
        scene = make_advanced_scene("voxel", seed=2)
        self.assertEqual(validate_advanced_scene(scene), scene)
        report = run_advanced_session("voxel", seed=2, scene=scene,
                                      actions=["inspect", "mine"])
        self.assertTrue(verify_advanced_session(report))
        for mutation in ("overlap", "bedrock", "variant", "order", "spawn"):
            invalid = deepcopy(scene["layout"])
            if mutation == "overlap":
                invalid["cells"].append(list(invalid["cells"][-1]))
            elif mutation == "bedrock":
                invalid["cells"][0][3] = "ore"
            elif mutation == "variant":
                invalid["cells"][0][4] = cfg["materials"]
            elif mutation == "order":
                invalid["cells"].reverse()
            else:
                invalid["spawn"] = [1, 0, 2]
            with self.subTest(mutation=mutation), self.assertRaises(SceneError):
                make_advanced_scene("voxel", layout=invalid)
        forged = deepcopy(scene)
        forged["layout"]["title"] = "Forged Frontier"
        with self.assertRaises(SceneError):
            validate_advanced_scene(forged)

    def test_receipt_save_continuation_and_tamper_detection(self):
        first = run_advanced_session("voxel", actions=["mine", "light"])
        save = export_advanced_savegame(first)
        self.assertTrue(import_advanced_savegame(save)["verified"])
        continued = continue_advanced_savegame(save, ["place:soil", "wait"])
        self.assertTrue(import_advanced_savegame(continued)["verified"])
        forged = deepcopy(first)
        forged["state"]["inventory"]["ore"] += 100
        with self.assertRaises(AdvancedRuntimeError):
            verify_advanced_session(forged)

    def test_editor_axes_have_real_gameplay_consequences(self):
        narrow = run_advanced_session("voxel",
                     {"visible_chunks": 1}, actions=["east", "east"])
        self.assertEqual(narrow["state"]["player"][:2], [2, 0])
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("voxel",
                {"visible_chunks": 1}, actions=["north"] * 6)
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("voxel",
                {"max_stamina": 2}, actions=["east", "east", "east"])
        dark = run_advanced_session("voxel", {"day_length": 2},
                                    actions=["wait"])
        self.assertFalse(dark["state"]["daylight"])
        self.assertLess(dark["state"]["health"], self.config()["max_health"])

    def test_assembly_contains_real_gameplay_receipts(self):
        manifest = compile_system_assembly("voxel_alpha",
                       [make_editor_document("voxel")])
        evidence = manifest["advanced_runtime_evidence"]
        self.assertEqual(len(evidence), 1)
        self.assertEqual(evidence[0]["editor"], "voxel")
        self.assertFalse(evidence[0]["native_game_engine_certified"])


if __name__ == "__main__":
    unittest.main()
