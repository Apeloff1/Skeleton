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
from skeleton.jeeves.ai.studio_sprite_forge import StudioSpriteError
from skeleton.jeeves.ai.studio_sprite_actor_binding import SpriteBindingError
from skeleton.jeeves.ai.studio_sprite_actor_native import NativeAvatarError
from skeleton.jeeves.ai.studio_host_bootstrap import NativeStudioHost
from skeleton.jeeves.ai.studio_interaction_contract import (
    StudioEvidenceJournal, StudioInteractionError,
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

    def test_missing_real_godot_binary_refuses_native_playthrough(self):
        self.populate_3d()
        with self.assertRaises(FrontierSourceError):
            self.owner.run_native_playthrough(
                godot_executable=str(self.root / "absent-godot4"),
                timeout_seconds=1,
            )
        self.assertFalse(any(self.export.iterdir()))

    def test_model_cannot_self_claim_native_gameplay_receipt(self):
        with StudioEvidenceJournal(
            self.root / "native-journal.sqlite",
            project_id="new-game", session_id="human-session",
        ) as journal:
            with self.assertRaises(StudioInteractionError):
                journal.append("native_gameplay_verified", {
                    "native_process_executed": True, "completed": True,
                })
            self.assertEqual(len(journal.read()), 0)

    def test_host_permission_denied_before_engine_launch(self):
        self.populate_3d()
        with StudioEvidenceJournal(
            self.root / "native-journal.sqlite",
            project_id="new-game", session_id="human-session",
        ) as journal:
            host = NativeStudioHost.__new__(NativeStudioHost)
            host.journal = journal
            host.source_store = self.owner
            calls = []
            with self.assertRaises(StudioInteractionError):
                host.verify_real_native_gameplay(
                    godot_executable=str(self.root / "absent-godot4"),
                    actor_id="human-producer",
                    authorize_native_execution=lambda project, binary, actor: (
                        calls.append((project, binary, actor)) or False
                    ),
                )
            self.assertEqual(len(calls), 1)
            self.assertEqual(len(journal.read()), 0)

    def test_original_normal_map_is_verified_in_real_godot_source_zip(self):
        self.populate_3d()
        self.create("authored-lit-art", "sprite_forge", {
            "kind": "pixel_sprite", "asset_id": "lit-hero",
            "width": 2, "height": 2, "pixel_scale": 2,
            "palette": ["#00000000", "#cc6644ff"],
            "frames": [
                {"frame_id": "idle-0", "duration_ms": 100,
                 "pixels": [0, 1, 1, 0]},
            ],
            "animations": [{
                "name": "idle", "frame_ids": ["idle-0"], "loop": True,
            }],
            "lighting": {
                "kind": "heightfield_normals", "strength": 8,
                "height_frames": [{
                    "frame_id": "idle-0", "heights": [0, 120, 220, 255],
                }],
            },
        }, depends=("config-3d",))
        report = self.export_godot()
        with zipfile.ZipFile(self.export / report["artifact_name"]) as bundle:
            texture = bundle.read("game/frontier/sprites/lit-hero.normal.png")
            color = bundle.read("game/frontier/sprites/lit-hero.png")
            metadata = json.loads(
                bundle.read("game/frontier/sprites/lit-hero.json")
            )
            original_heights = json.loads(
                bundle.read("game/frontier/sprites/lit-hero.normal.source.json")
            )
            manifest = json.loads(bundle.read("jeeves_source_receipt.json"))
        from skeleton.jeeves.ai.studio_sprite_surface import (
            verify_authored_normals, verify_normal_texture_bytes,
        )
        self.assertTrue(verify_authored_normals(
            original_heights, metadata=metadata,
            color_png=color, normal_png=texture,
            normal_receipt=metadata["normal_map"],
        )["height_map_replayed"])
        self.assertTrue(verify_normal_texture_bytes(
            color, texture, metadata["normal_map"],
            width=metadata["sheet_width_px"],
            height=metadata["sheet_height_px"],
        )["normalized_visible_vectors_verified"])
        self.assertEqual(
            manifest["packaged_original_sprites"][0]["normal_png_sha256"],
            sha256(texture).hexdigest(),
        )
        self.assertTrue(report["disk_verification"]["all_emitted_file_hashes_verified"])
        self.assertFalse(metadata["normal_map"]["normal_map_loaded_in_native_engine"])

    def test_original_sprite_png_is_packaged_inside_real_godot_project(self):
        self.populate_3d()
        self.create("hero-art", "sprite_forge", {
            "kind": "pixel_sprite", "asset_id": "hero-idle",
            "width": 2, "height": 2, "pixel_scale": 2,
            "palette": ["#00000000", "#3366ffff"],
            "frames": [
                {"frame_id": "first", "duration_ms": 100,
                 "pixels": [0, 1, 1, 0]},
                {"frame_id": "second", "duration_ms": 200,
                 "pixels": [1, 0, 0, 1]},
            ],
            "animations": [
                {"name": "idle", "frame_ids": ["first", "second"],
                 "loop": True},
            ],
        }, depends=("config-3d",))
        result = self.export_godot()
        with zipfile.ZipFile(self.export / result["artifact_name"]) as z:
            png = z.read("game/frontier/sprites/hero-idle.png")
            info = json.loads(z.read("game/frontier/sprites/hero-idle.json"))
            hitboxes = json.loads(
                z.read("game/frontier/sprites/hero-idle.hitboxes.json")
            )
            receipt = json.loads(z.read("jeeves_source_receipt.json"))
        self.assertTrue(png.startswith(b"\x89PNG\r\n\x1a\n"))
        self.assertEqual(info["sheet_width_px"], 8)
        self.assertEqual(info["frames"][1]["duration_ms"], 200)
        self.assertEqual(info["png_sha256"], sha256(png).hexdigest())
        from skeleton.jeeves.ai.studio_sprite_hitboxes import verify_exact_sprite_hitboxes
        self.assertEqual(verify_exact_sprite_hitboxes(info, hitboxes), hitboxes)
        self.assertEqual(
            receipt["packaged_original_sprites"][0]["original_hitbox_receipt_sha256"],
            hitboxes["receipt_sha256"],
        )
        self.assertEqual(receipt["packaged_original_sprites"][0]["asset_id"],
                         "hero-idle")
        self.assertIn("hero-art", receipt["source_sprite_record_ids"])
        self.assertFalse(receipt["native_sprite_scene_binding_verified"])
        self.assertIn("hero-art", receipt["uncompiled_record_ids"])
        self.assertFalse(receipt["all_studio_facets_compiled"])
        self.assertTrue(result["disk_verification"]["all_emitted_file_hashes_verified"])

    def test_invalid_sprite_source_blocks_game_export_without_partial_file(self):
        self.populate_3d()
        with self.assertRaises(StudioSpriteError):
            self.create("invalid-art", "sprite_forge", {
            "kind": "pixel_sprite", "asset_id": "invalid-art",
            "width": 1, "height": 1, "pixel_scale": 1,
            "palette": ["#3366ffff"],
            "frames": [{"frame_id": "empty", "duration_ms": 100,
                        "pixels": [9]}],
            "animations": [{"name": "idle", "frame_ids": ["empty"],
                            "loop": True}],
            }, depends=("config-3d",))
        self.assertEqual(self.owner.snapshot()["source_count"], 4)
        self.assertFalse(any(self.export.iterdir()))

    def author_player_visual(self, *, animation="idle", source_dependency=True,
                             movement_map=None, directional_map=None, cues=None,
                             audio_bindings=None):
        hero_document = {
            "kind": "pixel_sprite", "asset_id": "hero-idle",
            "width": 2, "height": 2, "pixel_scale": 2,
            "palette": ["#00000000", "#3366ffff"],
            "frames": [
                {"frame_id": "first", "duration_ms": 120,
                 "pixels": [0, 1, 1, 0]},
                {"frame_id": "second", "duration_ms": 160,
                 "pixels": [1, 0, 0, 1]},
            ],
            "animations": [
                {"name": "idle", "frame_ids": ["first", "second"],
                 "loop": True},
                {"name": "walk", "frame_ids": ["second", "first"],
                 "loop": True},
                {"name": "glide", "frame_ids": ["second"],
                 "loop": True},
            ],
        }
        if cues is not None:
            hero_document["cues"] = cues
        self.create("hero-art", "sprite_forge",
                    hero_document, depends=("config-3d",))
        binding_document = {
            "kind": "sprite_actor_binding",
            "target": "player_actor", "asset_id": "hero-idle",
            "animation": animation, "pixel_size": 0.025,
            "vertical_offset_m": 1.5,
            "billboard": True, "hide_capsule": True,
        }
        if movement_map is not None:
            binding_document["movement_animations"] = movement_map
        if directional_map is not None:
            binding_document["directional_animations"] = directional_map
        dependencies = ("hero-art",) if source_dependency else ("config-3d",)
        if audio_bindings is not None:
            binding_document["audio_cue_bindings"] = dict(audio_bindings)
            if audio_bindings:
                dependencies = dependencies + ("footstep-source",)
        self.create("hero-visual-binding", "scene_forge",
                    binding_document, depends=dependencies)

    def author_original_world_npc(self):
        self.create("captain-spawn", "npc", {
            "kind": "npc_spawn", "npc_id": "captain-sera",
            "home_waypoint_id": "harbor",
            "patrol_waypoint_ids": ["island_001", "harbor"],
        }, depends=("generated-islands",))
        self.create("captain-art-binding", "scene_forge", {
            "kind": "sprite_npc_binding",
            "npc_id": "captain-sera",
            "asset_id": "hero-idle",
            "animation": "idle",
            "pixel_size": 0.025,
            "vertical_offset_m": 1.5,
            "billboard": True, "hide_capsule": True,
        }, depends=("hero-art", "captain-spawn"))

    def test_original_npc_animation_emits_authored_frame_cues_in_real_godot(self):
        self.populate_3d()
        self.author_player_visual(cues=[
            {"animation": "idle", "frame_index": 0,
             "event_id": "captain-footstep", "category": "footstep"},
            {"animation": "glide", "frame_index": 0,
             "event_id": "captain-cloak", "category": "sound"},
        ])
        self.author_original_world_npc()
        result = self.export_godot()
        with zipfile.ZipFile(self.export / result["artifact_name"]) as archive:
            code = archive.read("game/frontier/expedition.gd").decode("utf-8")
            cues = archive.read(
                "game/frontier/sprites/hero-idle.cues.gd",
            ).decode("utf-8")
            proof = json.loads(archive.read("jeeves_source_receipt.json"))
        self.assertIn(
            "jeeves_npc_sprite.set_script(jeeves_npc_cue_script)", code,
        )
        self.assertIn("captain-footstep", cues)
        self.assertIn("captain-cloak", cues)
        self.assertEqual(
            proof["authored_npc_sprite_bindings"][0]["frame_cues_sha256"],
            proof["authored_player_avatar_binding"]["frame_cues_sha256"],
        )
        self.assertTrue(
            result["disk_verification"]["all_emitted_file_hashes_verified"],
        )
        self.assertFalse(proof["native_godot_playthrough_verified"])

    def test_real_godot_player_and_original_npc_both_receive_animated_sprites(self):
        self.populate_3d()
        self.author_player_visual()
        self.author_original_world_npc()
        result = self.export_godot()
        with zipfile.ZipFile(self.export / result["artifact_name"]) as archive:
            engine = archive.read("game/frontier/expedition.gd").decode("utf-8")
            cast = json.loads(archive.read("game/frontier/npcs.json"))
            receipt = json.loads(archive.read("jeeves_source_receipt.json"))
        self.assertEqual(cast["schema"], "skeleton.game.original_npc_cast.v1")
        self.assertEqual(cast["cast"][0]["design"]["npc_id"], "captain-sera")
        self.assertEqual(cast["cast"][0]["design"]["home"], "harbor")
        self.assertEqual(cast["cast"][0]["proof"]["steps"],
                         [{"new": "island_001"}, {"new": "harbor"}])
        self.assertIn("npc.add_child(jeeves_npc_sprite)", engine)
        self.assertIn("actor.add_child(jeeves_avatar)", engine)
        self.assertIn('jeeves_npc_sprite.name = "OriginalAuthoredNPCSprite"', engine)
        self.assertTrue(receipt["animated_npc_sprite3d_source_compiled"])
        self.assertTrue(receipt["animated_sprite3d_player_script_compiled"])
        self.assertEqual(receipt["original_npc_cast_receipt"]["npc_count"], 1)
        self.assertEqual(receipt["npc_sprite_game_script_receipt"]["npc_bound_count"], 1)
        self.assertFalse(receipt["npc_sprite_game_script_receipt"][
            "native_npc_visual_render_verified"
        ])
        self.assertTrue(result["disk_verification"][
            "all_emitted_file_hashes_verified"
        ])

    def test_original_npc_world_patrol_must_reference_a_real_waypoint(self):
        self.populate_3d()
        self.create("captain-spawn", "npc", {
            "kind": "npc_spawn", "npc_id": "captain-sera",
            "home_waypoint_id": "nonexistent-island",
            "patrol_waypoint_ids": ["harbor"],
        }, depends=("generated-islands",))
        from skeleton.jeeves.ai.studio_npc_cast_source import OriginalNpcCastError
        with self.assertRaisesRegex(OriginalNpcCastError, "real authored world waypoint"):
            self.export_godot()
        self.assertFalse(any(self.export.iterdir()))

    def test_original_palette_skin_is_real_verified_godot_sprite_resource(self):
        self.populate_3d()
        self.author_player_visual()
        self.create("hero-night-palette", "sprite_forge", {
            "kind": "sprite_palette_variant",
            "asset_id": "hero-night",
            "parent_record_id": "hero-art",
            "color_map": {"#3366ffff": "#ff3366ff"},
        }, depends=("hero-art",))
        exported = self.export_godot()
        with zipfile.ZipFile(self.export / exported["artifact_name"]) as archive:
            base = archive.read("game/frontier/sprites/hero-idle.png")
            night = archive.read("game/frontier/sprites/hero-night.png")
            frames = archive.read("game/frontier/sprites/hero-night.tres")
            source = json.loads(archive.read("jeeves_source_receipt.json"))
            original = json.loads(archive.read("game/frontier/sprites/hero-idle.json"))
            derived = json.loads(archive.read("game/frontier/sprites/hero-night.json"))
        self.assertNotEqual(base, night)
        self.assertIn(b"SpriteFrames", frames)
        self.assertEqual(
            [frame["collision_mask_bits_hex"] for frame in original["frames"]],
            [frame["collision_mask_bits_hex"] for frame in derived["frames"]],
        )
        self.assertEqual(
            [frame["duration_ms"] for frame in original["frames"]],
            [frame["duration_ms"] for frame in derived["frames"]],
        )
        self.assertEqual(len(source["original_palette_variant_receipts"]), 1)
        receipt = source["original_palette_variant_receipts"][0]
        self.assertEqual(receipt["variant_source_record_id"], "hero-night-palette")
        self.assertEqual(receipt["source_png_sha256"], sha256(base).hexdigest())
        self.assertEqual(receipt["derived_png_sha256"], sha256(night).hexdigest())
        self.assertTrue(exported["disk_verification"][
            "all_emitted_file_hashes_verified"
        ])
        self.assertFalse(source["native_sprite_scene_binding_verified"])

    def test_authored_frame_cues_execute_on_the_real_avatar_script_source(self):
        self.populate_3d()
        self.author_player_visual(cues=[
            {"animation": "idle", "frame_index": 0,
             "event_id": "footstep-1", "category": "footstep"},
            {"animation": "walk", "frame_index": 1,
             "event_id": "cloth-impact", "category": "impact"},
        ])
        exported = self.export_godot()
        with zipfile.ZipFile(self.export / exported["artifact_name"]) as bundle:
            godot = bundle.read("game/frontier/expedition.gd").decode("utf-8")
            cuescript = bundle.read(
                "game/frontier/sprites/hero-idle.cues.gd",
            ).decode("utf-8")
            source = json.loads(bundle.read("jeeves_source_receipt.json"))
            authored = json.loads(bundle.read(
                "game/frontier/sprites/hero-idle.json",
            ))
        self.assertIn("jeeves_avatar.set_script(jeeves_cue_logic)", godot)
        self.assertIn("frame_changed.connect(_publish_frame_cues)", cuescript)
        self.assertIn("footstep-1", cuescript)
        self.assertIn("cloth-impact", cuescript)
        self.assertTrue(exported["disk_verification"]["all_emitted_file_hashes_verified"])
        self.assertEqual(
            source["authored_player_avatar_binding"]["frame_cues_sha256"],
            authored["frame_cues"]["receipt_sha256"],
        )
        self.assertFalse(
            source["native_godot_playthrough_verified"],
        )

    def test_original_pcm_footstep_plays_from_godot_player_frame_cue_source(self):
        from skeleton.testing.test_jeeves_original_audio import original_sound
        from skeleton.jeeves.ai.studio_original_audio import verify_original_sound
        self.populate_3d()
        self.create("footstep-source", "audio_forge", original_sound(),
                    depends=("config-3d",))
        self.author_player_visual(
            cues=[{"animation": "walk", "frame_index": 0,
                   "event_id": "step-left", "category": "footstep"}],
            audio_bindings={"step-left": "original-footstep"},
        )
        exported = self.export_godot()
        with zipfile.ZipFile(self.export / exported["artifact_name"]) as archive:
            audio = archive.read("game/frontier/audio/original-footstep.wav")
            source = json.loads(archive.read(
                "game/frontier/audio/original-footstep.source.json",
            ))
            engine = archive.read("game/frontier/expedition.gd").decode("utf-8")
            receipt = json.loads(archive.read("jeeves_source_receipt.json"))
        self.assertTrue(
            verify_original_sound(
                source["record"], audio, source["metadata"],
            )["reconstructed_all_pcm_samples"]
        )
        self.assertIn("AudioStreamPlayer3D.new()", engine)
        self.assertIn('jeeves_avatar.connect("cue_fired"', engine)
        self.assertIn("original-footstep", engine)
        self.assertEqual(receipt["original_player_audio_cue_routes_compiled"], 1)
        self.assertEqual(len(receipt["packaged_original_audio"]), 1)
        self.assertFalse(receipt["audio_engine_playback_verified"])
        self.assertTrue(exported["disk_verification"][
            "all_emitted_file_hashes_verified"
        ])

    def test_audio_cue_cannot_reference_uncreated_sound(self):
        from skeleton.jeeves.ai.studio_creator_source import CreatorSourceError
        self.populate_3d()
        with self.assertRaises(CreatorSourceError):
            self.author_player_visual(
                cues=[{"animation": "idle", "frame_index": 0,
                       "event_id": "step-left", "category": "footstep"}],
                audio_bindings={"step-left": "missing-original-sound"},
            )
        # A missing source dependency never becomes a silent default tone.
        self.assertFalse(any(self.export.iterdir()))

    def test_authored_sprite_is_bound_to_actual_moving_godot_player(self):
        self.populate_3d()
        self.author_player_visual()
        exported = self.export_godot()
        with zipfile.ZipFile(self.export / exported["artifact_name"]) as archive:
            script = archive.read("game/frontier/expedition.gd").decode("utf-8")
            receipt = json.loads(archive.read("jeeves_source_receipt.json"))
            resource = archive.read("game/frontier/sprites/hero-idle.tres")
        self.assertIn("var jeeves_avatar := AnimatedSprite3D.new()", script)
        self.assertIn("actor.add_child(jeeves_avatar)", script)
        self.assertIn('jeeves_avatar.animation = &"idle"', script)
        self.assertIn("actor.mesh = null", script)
        self.assertIn(b"SpriteFrames", resource)
        self.assertTrue(receipt["animated_sprite3d_player_script_compiled"])
        self.assertEqual(
            receipt["authored_player_avatar_binding"]["record_id"],
            "hero-visual-binding",
        )
        self.assertTrue(receipt["player_avatar_game_script_receipt"][
            "source_reproduction_verified"
        ])
        self.assertFalse(receipt["native_sprite_scene_binding_verified"])
        self.assertTrue(exported["disk_verification"][
            "all_emitted_file_hashes_verified"
        ])

    def test_real_game_moves_animated_player_between_authored_modes(self):
        self.populate_3d()
        self.author_player_visual(
            movement_map={"walk": "walk", "glide": "glide"},
        )
        exported = self.export_godot()
        with zipfile.ZipFile(self.export / exported["artifact_name"]) as z:
            script = z.read("game/frontier/expedition.gd").decode("utf-8")
            proof = json.loads(z.read("jeeves_source_receipt.json"))
        self.assertIn('"walk": "walk"', script)
        self.assertIn('"glide": "glide"', script)
        self.assertIn("jeeves_avatar_node.play(jeeves_animation)", script)
        self.assertLess(
            script.index('if stamina < int(costs["stamina"]):'),
            script.index("var jeeves_travel_animations"),
        )
        self.assertEqual(
            proof["authored_player_avatar_binding"]["movement_animations"],
            {"walk": "walk", "glide": "glide"},
        )
        self.assertTrue(exported["disk_verification"][
            "all_emitted_file_hashes_verified"
        ])

    def test_player_movement_rejects_nonexistent_original_animation(self):
        self.populate_3d()
        with self.assertRaisesRegex(SpriteBindingError, "movement state map"):
            self.author_player_visual(movement_map={"walk": "nonexistent"})
        self.assertEqual(self.owner.snapshot()["source_count"], 5)
        self.assertEqual(list(self.export.iterdir()), [])

    def test_avatar_movement_mode_must_have_safe_identifier(self):
        self.populate_3d()
        with self.assertRaisesRegex(SpriteBindingError, "movement state map"):
            self.author_player_visual(movement_map={"walk;queue_free": "walk"})
        self.assertEqual(list(self.export.iterdir()), [])

    def test_binding_requires_real_sprite_source_dependency(self):
        self.populate_3d()
        with self.assertRaisesRegex(SpriteBindingError, "depend"):
            self.author_player_visual(source_dependency=False)
        self.assertEqual(list(self.export.iterdir()), [])

    def test_binding_rejects_nonexistent_animation(self):
        self.populate_3d()
        with self.assertRaisesRegex(SpriteBindingError, "animation"):
            self.author_player_visual(animation="fictitious")
        self.assertEqual(list(self.export.iterdir()), [])

    def test_sprite_edit_cannot_break_already_bound_player_animation(self):
        self.populate_3d()
        self.author_player_visual()
        before = self.owner.snapshot()["head_sha256"]
        changed = [{
            "name": "new-animation",
            "frame_ids": ["first", "second"], "loop": True,
        }]
        with self.assertRaisesRegex(SpriteBindingError, "animation"):
            self.owner.edit(build_creator_command(
                "edit", project_id="new-game",
                payload={
                    "target_id": "hero-art", "expected_revision": 1,
                    "patch": {"set": {"animations": changed}, "remove": []},
                },
            ))
        self.assertEqual(self.owner.snapshot()["head_sha256"], before)
        self.assertFalse(any(self.export.iterdir()))

    def test_avatar_source_edit_preserves_binding_and_renews_attestation(self):
        self.populate_3d()
        self.author_player_visual()
        before = self.owner.snapshot()["head_sha256"]
        self.owner.edit(build_creator_command(
            "edit", project_id="new-game",
            payload={
                "target_id": "hero-art", "expected_revision": 1,
                "patch": {"set": {"pixel_scale": 3}, "remove": []},
            },
        ))
        self.assertNotEqual(self.owner.snapshot()["head_sha256"], before)
        exported = self.export_godot()
        with zipfile.ZipFile(self.export / exported["artifact_name"]) as z:
            sprite = json.loads(z.read("game/frontier/sprites/hero-idle.json"))
            binding = json.loads(z.read("jeeves_source_receipt.json"))[
                "authored_player_avatar_binding"
            ]
        self.assertEqual(sprite["pixel_scale"], 3)
        self.assertEqual(binding["sprite_png_sha256"], sprite["png_sha256"])
        self.assertFalse(binding["engine_actor_visual_execution_verified"])

    def test_real_avatar_inspector_is_bound_to_native_route_observations(self):
        from skeleton.jeeves.ai.studio_sprite_actor_native import _INSPECT
        self.assertIn('for step in expected["route"]:', _INSPECT)
        self.assertIn("game._can_travel(edge)", _INSPECT)
        self.assertIn("game._travel(edge)", _INSPECT)
        self.assertIn('if str(game.current_id) != str(step["target"]):', _INSPECT)
        self.assertIn('if avatar.get_parent() != actor:', _INSPECT)
        self.assertIn("avatar.animation != selected", _INSPECT)
        self.assertIn('"mapped_movement_transitions_observed"', _INSPECT)
        self.assertIn('"observed_movement_modes"', _INSPECT)

    def test_native_sprite_state_compiler_preserves_real_travel_gates(self):
        from skeleton.jeeves.ai.studio_sprite_actor_binding import (
            bind_sprite_to_expedition_script, binding_from_source,
        )
        from skeleton.jeeves.game_frontier_expedition_godot import _GODOT_SCRIPT
        self.populate_3d()
        self.author_player_visual(
            movement_map={"walk": "walk", "glide": "glide"},
        )
        authored = self.owner._records["hero-art"]
        from skeleton.jeeves.ai.studio_sprite_forge import compile_authored_sprite
        from skeleton.jeeves.ai.studio_sprite_godot_resources import (
            compile_godot_sprite_resources, verify_godot_sprite_resources,
        )
        asset = compile_authored_sprite(authored)["metadata"]
        proof = verify_godot_sprite_resources(
            asset, compile_godot_sprite_resources(asset),
        )
        binding = binding_from_source(self.owner._records, [{
            "asset_id": asset["asset_id"],
            "source_record_id": authored["record_id"],
            "png_sha256": asset["png_sha256"],
            "godot_spriteframes_resource_sha256": proof["receipt_sha256"],
            "animation_names": [entry["name"] for entry in asset["animations"]],
        }])
        native = bind_sprite_to_expedition_script(_GODOT_SCRIPT, binding)
        self.assertIn('if won or failed or not _can_travel(edge):', native)
        self.assertIn('if stamina < int(costs["stamina"]):', native)
        self.assertLess(
            native.index('if stamina < int(costs["stamina"]):'),
            native.index('var jeeves_travel_animations: Dictionary'),
        )
        self.assertEqual(native.count('stamina -= int(costs["stamina"])'), 1)
        self.assertEqual(native.count('actor.add_child(jeeves_avatar)'), 1)

    def test_native_engine_actor_review_requires_installed_godot4(self):
        self.populate_3d()
        self.author_player_visual()
        with self.assertRaises(NativeAvatarError):
            self.owner.verify_native_player_avatar(
                godot_executable=str(self.root / "not-installed-godot4"),
                expected_binding_record_id="hero-visual-binding",
                timeout_seconds=2,
            )

    def test_host_permission_denies_game_avatar_before_native_launch(self):
        self.populate_3d()
        self.author_player_visual()
        with StudioEvidenceJournal(
            self.root / "avatar-journal.sqlite",
            project_id="new-game", session_id="reviewer-session",
        ) as journal:
            host = NativeStudioHost.__new__(NativeStudioHost)
            host.journal = journal
            host.source_store = self.owner
            authority_calls = []
            with self.assertRaises(StudioInteractionError):
                host.verify_real_player_avatar(
                    binding_record_id="hero-visual-binding",
                    godot_executable=str(self.root / "not-installed-godot4"),
                    actor_id="human-producer",
                    authorize_avatar_execution=lambda *args: (
                        authority_calls.append(args) or False
                    ),
                )
            self.assertEqual(authority_calls, [
                ("new-game", "hero-visual-binding",
                 str(self.root / "not-installed-godot4"), "human-producer"),
            ])
            self.assertEqual(journal.read(), ())

    def test_model_cannot_self_certify_game_avatar_visual_observation(self):
        with StudioEvidenceJournal(
            self.root / "avatar-journal.sqlite",
            project_id="new-game", session_id="reviewer-session",
        ) as journal:
            with self.assertRaises(StudioInteractionError):
                journal.append("native_player_avatar_verified", {
                    "real_godot_process_executed": True,
                    "animated_sprite_child_bound": True,
                })
            self.assertEqual(journal.read(), ())

    def test_native_avatar_does_not_resolve_foreign_scene_binding(self):
        self.populate_3d()
        with self.assertRaises(CreatorSourceError):
            self.owner.verify_native_player_avatar(
                godot_executable=str(self.root / "not-installed-godot4"),
                expected_binding_record_id="other-game-avatar",
            )

    def test_native_player_visual_does_not_self_certify_engine_render(self):
        self.populate_3d()
        self.author_player_visual()
        exported = self.export_godot()
        with zipfile.ZipFile(self.export / exported["artifact_name"]) as archive:
            proof = json.loads(archive.read("jeeves_source_receipt.json"))
        self.assertFalse(proof["authored_player_avatar_binding"][
            "engine_actor_visual_execution_verified"
        ])
        self.assertFalse(proof["player_avatar_game_script_receipt"][
            "real_godot_sprite_render_observed"
        ])
        self.assertFalse(proof["native_godot_playthrough_verified"])

    def test_optional_alpha_sensor_creates_real_frame_following_godot_shapes(self):
        self.populate_3d()
        self.author_player_visual()
        self.owner.edit(build_creator_command(
            "edit", project_id="new-game",
            payload={"target_id": "hero-visual-binding", "expected_revision": 1,
                     "patch": {"set": {"collision_sensor": True}, "remove": []}},
        ))
        result = self.export_godot()
        with zipfile.ZipFile(self.export / result["artifact_name"]) as archive:
            script = archive.read("game/frontier/expedition.gd").decode("utf-8")
            sensor = archive.read("game/frontier/sprites/hero-idle.sensor.gd").decode("utf-8")
            proof = json.loads(archive.read("jeeves_source_receipt.json"))
        self.assertIn("OriginalAlphaCollisionSensor", script)
        self.assertIn("actor.add_child(jeeves_sensor)", script)
        self.assertIn("avatar.frame_changed.connect(_update_exact_alpha_sensor)", sensor)
        self.assertIn("var shape := BoxShape3D.new()", sensor)
        self.assertTrue(proof["native_player_alpha_sensor_script_compiled"])
        self.assertEqual(proof["player_collision_sensor_receipt"]["runtime_collision_type"],
                         "Area3D_overlap_sensor")
        self.assertFalse(proof["player_collision_sensor_receipt"][
            "blocking_rigidbody_collision_claimed"
        ])
        self.assertFalse(proof["player_collision_sensor_receipt"][
            "native_godot_collision_test_executed"
        ])
        self.assertTrue(result["disk_verification"]["all_emitted_file_hashes_verified"])

    def test_missing_optional_sensor_cannot_invent_physics(self):
        self.populate_3d()
        self.author_player_visual()
        result = self.export_godot()
        with zipfile.ZipFile(self.export / result["artifact_name"]) as archive:
            proof = json.loads(archive.read("jeeves_source_receipt.json"))
            self.assertFalse(any(name.endswith(".sensor.gd")
                                 for name in archive.namelist()))
        self.assertIsNone(proof["player_collision_sensor_receipt"])
        self.assertFalse(proof["native_player_alpha_sensor_script_compiled"])

    def test_nonboolean_collision_policy_is_rejected_before_source_commit(self):
        self.populate_3d()
        self.author_player_visual()
        with self.assertRaises(Exception):
            self.owner.edit(build_creator_command(
                "edit", project_id="new-game",
                payload={"target_id": "hero-visual-binding",
                         "expected_revision": 1,
                         "patch": {"set": {"collision_sensor": "yes"},
                                   "remove": []}},
            ))
        self.assertEqual(self.owner._records["hero-visual-binding"]["revision"], 1)

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
