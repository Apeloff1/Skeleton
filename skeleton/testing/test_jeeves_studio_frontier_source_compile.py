"""Real typed Frontier Studio compilation of authored Jeeves source records."""
from __future__ import annotations

import json
import zipfile
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from skeleton.forge.creator.command_surface import build_creator_command
from skeleton.jeeves.ai.studio_creator_source import (
    CreatorProjectSourceStore, CreatorSourceError,
)
from skeleton.jeeves.ai.studio_godot_zip_verify import (
    NativeSourceVerificationError, verify_published_godot_zip,
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



class RealGodotSourceBuildTests(unittest.TestCase):
    """Generate actual Godot source bytes from authored, revisioned local data."""

    setUp = FrontierSourceCompileTests.setUp
    create = FrontierSourceCompileTests.create

    def populate_3d(self, *, traveler_modes=None):
        self.create("config-3d", "engine", {
            "kind": "studio_settings", "target_era": "sprite",
            "projection": "3d", "world_family": "original",
        })
        self.create("islands-3d", "map", {
            "kind": "map_layer", "layer_id": "islands",
            "width": 2, "height": 2,
            "palette": ["soil", "cloud"], "data": [0, 1, 0, 1],
        }, depends=("config-3d",))
        self.create("generated-islands", "world", {
            "kind": "expedition_profile",
            "seed": 42, "islands": 5, "spacing_m": 40.0,
            "rise_m": 8.0, "branch_factor": 2,
            "caverns": 1, "include_underwater": True,
            "include_portals": True,
        }, depends=("islands-3d",))
        self.create("original-traveler", "movement", {
            "kind": "traveler_profile",
            "permitted_modes": traveler_modes if traveler_modes is not None else [
                "walk", "rope_bridge", "updraft", "glide",
                "airship", "portal", "climb", "dive", "swim",
            ],
            "flags": ["glider", "airship_license", "diving_gear", "portal_key"],
            "equipment": ["instrument_navigation"],
            "max_stamina": 1000, "carried_kg": 0.0,
            "capacity_kg": 30.0, "skill": 0.8, "shelter": 0.0,
        }, depends=("generated-islands",))

    def export_godot(self):
        return self.owner.export(build_creator_command(
            "export", project_id="new-game",
            payload={"format": "frontier-godot4-zip",
                     "artifact_name": "original-archipelago"},
        ))

    def test_actual_godot_project_files_and_hash_receipts(self):
        self.populate_3d()
        report = self.export_godot()
        path = self.export / report["artifact_name"]
        self.assertEqual(path.suffix, ".zip")
        self.assertTrue(path.is_file())
        self.assertEqual(sha256(path.read_bytes()).hexdigest(),
                         report["artifact_sha256"])
        with zipfile.ZipFile(path) as artifact:
            names = set(artifact.namelist())
            self.assertIn("project.godot", names)
            self.assertIn("game/frontier/expedition.gd", names)
            self.assertIn("game/frontier/expedition.tscn", names)
            self.assertIn("game/frontier/expedition.json", names)
            self.assertIn("jeeves_source_receipt.json", names)
            receipt = json.loads(artifact.read("jeeves_source_receipt.json"))
            self.assertTrue(receipt["real_python_route_playtest_passed"])
            self.assertFalse(receipt["godot_engine_launched"])
            self.assertTrue(receipt["all_studio_facets_compiled"])
            self.assertEqual(
                receipt["source_head_sha256"], self.owner.head_identity(),
            )
            for name, expected in receipt["godot_file_hashes"].items():
                self.assertEqual(sha256(artifact.read(name)).hexdigest(), expected)

    def test_independent_reader_attests_real_file_bytes(self):
        self.populate_3d()
        result = self.export_godot()
        self.assertIsNotNone(result["disk_verification"])
        report = verify_published_godot_zip(
            self.export / result["artifact_name"], project_id="new-game",
            source_head_sha256=self.owner.head_identity(),
            expected_archive_sha256=result["artifact_sha256"],
        )
        self.assertEqual(report["archive_sha256"], result["artifact_sha256"])
        self.assertGreaterEqual(report["verified_file_count"], 5)
        self.assertFalse(report["actual_godot_execution_verified"])

    def test_tampered_export_is_rejected_against_original_receipt(self):
        self.populate_3d()
        result = self.export_godot()
        target = self.export / result["artifact_name"]
        with target.open("ab") as writer:
            writer.write(b"altered-after-fsync")
        with self.assertRaises(NativeSourceVerificationError):
            verify_published_godot_zip(
                target, project_id="new-game",
                source_head_sha256=self.owner.head_identity(),
                expected_archive_sha256=result["artifact_sha256"],
            )
        with self.assertRaises(CreatorSourceError):
            self.export_godot()

    def test_reject_foreign_project_pretending_to_own_valid_zip(self):
        self.populate_3d()
        result = self.export_godot()
        with self.assertRaises(NativeSourceVerificationError):
            verify_published_godot_zip(
                self.export / result["artifact_name"], project_id="foreign-game",
                source_head_sha256=self.owner.head_identity(),
                expected_archive_sha256=result["artifact_sha256"],
            )

    def test_native_zip_reexport_is_identical_and_non_destructive(self):
        self.populate_3d()
        first = self.export_godot()
        second = self.export_godot()
        self.assertEqual(first["artifact_sha256"], second["artifact_sha256"])
        self.assertTrue(second["already_exported"])
        self.assertEqual(len(list(self.export.iterdir())), 1)

    def test_missing_native_traveler_refuses_export(self):
        self.create("config-3d", "engine", {
            "kind": "studio_settings", "target_era": "sprite",
            "projection": "3d", "world_family": "original",
        })
        self.create("islands-3d", "map", {
            "kind": "map_layer", "layer_id": "islands",
            "width": 1, "height": 1,
            "palette": ["cloud"], "data": [0],
        })
        with self.assertRaises(FrontierSourceError):
            self.export_godot()
        self.assertFalse(any(self.export.iterdir()))

    def test_runtime_capability_constraints_are_not_silently_bypassed(self):
        self.populate_3d(traveler_modes=["walk"])
        with self.assertRaises(FrontierSourceError):
            self.export_godot()
        self.assertFalse(any(self.export.iterdir()))

    def test_existing_uncompiled_story_is_never_claimed_as_engine_content(self):
        self.populate_3d()
        self.create("uncompiled-acts", "story", {
            "title": "Three alternate finale chapters",
            "endings": ["airship", "hidden", "portals"],
        }, depends=("islands-3d",))
        report = self.export_godot()
        with zipfile.ZipFile(self.export / report["artifact_name"]) as archive:
            receipt = json.loads(archive.read("jeeves_source_receipt.json"))
        self.assertIn("uncompiled-acts", receipt["uncompiled_record_ids"])
        self.assertFalse(receipt["all_studio_facets_compiled"])
        self.assertFalse(receipt["native_godot_playthrough_verified"])


if __name__ == "__main__":
    unittest.main()
