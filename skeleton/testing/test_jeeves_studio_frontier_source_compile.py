"""Real typed Frontier Studio compilation of authored Jeeves source records."""
from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from skeleton.forge.creator.command_surface import build_creator_command
from skeleton.jeeves.ai.studio_creator_source import (
    CreatorProjectSourceStore, CreatorSourceError,
)
from skeleton.jeeves.ai.studio_frontier_source_compile import (
    FrontierSourceError, compile_persisted_frontier_source,
)


class FrontierSourceCompileTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.export = self.root / "exports"
        self.export.mkdir()
        self.owner = CreatorProjectSourceStore(
            self.root / "game.sqlite",
            project_id="new-game", export_root=self.export,
        )
        self.addCleanup(self.owner.close)

    def create(self, rid, facet, doc, depends=()):
        cmd = build_creator_command(
            "create", project_id="new-game",
            payload={"intent": {
                "record_id": rid, "facet": facet,
                "document": doc, "depends_on": list(depends),
            }},
        )
        self.owner.create(cmd)

    def populate(self):
        self.create("config", "engine", {
            "kind": "studio_settings", "target_era": "sprite",
            "projection": "top_down", "world_family": "original",
        })
        self.create("islands", "map", {
            "kind": "map_layer", "layer_id": "base",
            "width": 2, "height": 2,
            "palette": ["grass", "sky"], "data": [0, 1, 1, 0],
        }, depends=("config",))
        self.create("original-npc", "asset_forge", {
            "kind": "prefab", "prefab_id": "captain-sera",
            "prefab_kind": "npc", "era": "sprite",
            "asset_digest": "a" * 64,
            "interaction_type": "dialogue",
        }, depends=("config",))
        self.create("sera-placement", "scene_forge", {
            "kind": "placement", "prefab_id": "captain-sera",
            "x": 1.0, "y": 0.0, "z": 0.0,
            "facing_deg": 90.0,
        }, depends=("original-npc", "islands"))
        self.create("sera-event", "dialogue", {
            "kind": "event", "event_id": "interact-sera",
            "trigger": "interact", "condition_flag": "",
            "condition_value": False, "action": "show_dialogue",
            "target": "captain-sera", "value": "new-quest",
        }, depends=("sera-placement",))

    def forge(self):
        return compile_persisted_frontier_source(
            "new-game", self.owner._records,
            source_head_sha256=self.owner.snapshot()["head_sha256"],
        )

    def test_real_typed_map_prefab_placement_event_compilation(self):
        self.populate()
        result = self.forge()
        manifest = result["typed_manifest"]
        self.assertEqual(manifest["schema"], "skeleton.forge.frontier_studio.v1")
        self.assertEqual(manifest["project_id"], "new-game")
        self.assertEqual(manifest["projection"], "top_down")
        self.assertEqual(len(manifest["layers"]), 1)
        self.assertEqual(manifest["layers"][0]["data"], (0, 1, 1, 0))
        self.assertEqual(len(manifest["prefabs"]), 1)
        self.assertEqual(len(manifest["placements"]), 1)
        self.assertEqual(len(manifest["events"]), 1)
        self.assertEqual(len(result["compiled_record_ids"]), 5)
        self.assertTrue(result["typed_forge_coverage_complete"])
        self.assertFalse(result["native_engine_runtime_executed"])
        self.assertEqual(len(result["receipt_sha256"]), 64)

    def test_real_content_addressed_typed_forge_export(self):
        self.populate()
        first = self.owner.export(build_creator_command(
            "export", project_id="new-game",
            payload={"format": "frontier-studio-json",
                     "artifact_name": "captain-sera-forge"},
        ))
        payload = json.loads((self.export / first["artifact_name"]).read_bytes())
        self.assertEqual(payload["typed_compiler"],
                         "skeleton.forge.game_frontier_studio.compile_studio_project")
        self.assertEqual(first["export_format"], "frontier-studio-json")
        self.assertEqual(payload["source_head_sha256"],
                         self.owner.snapshot()["head_sha256"])
        self.assertFalse(first["native_binary_compiled"])

    def test_missing_settings_fails_without_synthetic_defaults(self):
        self.create("terrain", "map", {
            "kind": "map_layer", "layer_id": "a", "width": 1,
            "height": 1, "palette": ["grass"], "data": [0],
        })
        with self.assertRaises(FrontierSourceError):
            self.forge()

    def test_missing_map_fails_without_inventing_a_world(self):
        self.create("config", "engine", {
            "kind": "studio_settings", "target_era": "sprite",
            "projection": "top_down", "world_family": "original",
        })
        with self.assertRaises(FrontierSourceError):
            self.forge()

    def test_invalid_map_palette_fails_native_type_validation(self):
        self.populate()
        self.create("invalid-map", "map", {
            "kind": "map_layer", "layer_id": "bad-map", "width": 2,
            "height": 2, "palette": ["grass"], "data": [2, 2, 2, 2],
        })
        with self.assertRaises(FrontierSourceError):
            self.forge()

    def test_other_studio_facet_is_retained_but_explicitly_uncompiled(self):
        self.populate()
        self.create("story-outline", "story", {
            "title": "The three ending routes",
            "endings": ["north", "west", "hidden"],
        }, depends=("islands",))
        result = self.forge()
        self.assertFalse(result["typed_forge_coverage_complete"])
        self.assertEqual(result["non_compilable_record_ids"], ["story-outline"])

    def test_unresolved_prefab_placement_fails_existing_forge_validation(self):
        self.create("config", "engine", {
            "kind": "studio_settings", "target_era": "sprite",
            "projection": "top_down", "world_family": "original",
        })
        self.create("terrain", "map", {
            "kind": "map_layer", "layer_id": "a", "width": 1,
            "height": 1, "palette": ["grass"], "data": [0],
        }, depends=("config",))
        self.create("placed", "scene_forge", {
            "kind": "placement", "prefab_id": "not-created",
            "x": 0.0, "y": 0.0, "z": 0.0,
        }, depends=("terrain",))
        with self.assertRaises(FrontierSourceError):
            self.forge()

    def test_export_refuses_invalid_forge_and_writes_no_file(self):
        self.create("config", "engine", {
            "kind": "studio_settings", "target_era": "sprite",
            "projection": "top_down", "world_family": "original",
        })
        with self.assertRaises(FrontierSourceError):
            self.owner.export(build_creator_command(
                "export", project_id="new-game",
                payload={"format": "frontier-studio-json",
                         "artifact_name": "bad-game"},
            ))
        self.assertEqual(list(self.export.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
