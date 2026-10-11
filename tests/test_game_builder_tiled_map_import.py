"""Tiled editor numeric geometry converts to truly playable native/browser games."""
from __future__ import annotations

from contextlib import redirect_stdout
from dataclasses import replace
import io
import json
from pathlib import Path
import tempfile
import unittest

from skeleton.ai.game_builder.authored_tiles import (
    AUTHORED_SCHEMA, compile_authored_document,
)
from skeleton.ai.game_builder.dual_runtime_export import render_dual_runtime_package
from skeleton.ai.game_builder.original_game_studio_cli import main as studio_main
from skeleton.ai.game_builder.playable_compiler import compile_original_game
from skeleton.ai.game_builder.playable_world import GameBuildIntent
from skeleton.ai.game_builder.tiled_map_import import (
    TiledImportError, import_tiled_levels, write_tiled_authored_json,
)
from skeleton.ai.game_builder.tiled_map_cli import main as tiled_main


_TO_GID = {"#": 1, ".": 2, "S": 3, "G": 4, "C": 5, "H": 6}


class TiledDataOnlyHomebrewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.intent = GameBuildIntent(
            project_id="tiled-original-homebrew-2026",
            title="Original Tiled Homebrew",
            subtitle="Original geometry using an open source authoring tool.",
            seed=891, width=11, height=11, levels=2,
            collectibles_per_level=2, hazards_per_level=1,
            theme="desert", starting_health=4,
        )
        cls.project = compile_original_game(cls.intent, authorized=True)

    @staticmethod
    def map_json(level):
        return {
            "type": "map",
            "orientation": "orthogonal", "infinite": False,
            "width": level.width, "height": level.height,
            "tilewidth": 16, "tileheight": 16,
            "layers": [{
                "type": "tilelayer",
                "name": "original_game_tiles", "width": level.width,
                "height": level.height, "visible": True,
                "x": 0, "y": 0,
                "data": [_TO_GID[ch] for row in level.rows for ch in row],
            }],
            "tilesets": [
                {"firstgid": 1, "source": "../../external-original-or-unlicensed.tsx",
                 "image": "https://example.org/not-imported-characters.png"},
            ],
        }

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.inputs = []
        for level in self.project.world.levels:
            path = self.root / f"level-{level.index}.json"
            path.write_text(json.dumps(self.map_json(level)), encoding="utf-8")
            self.inputs.append(path)

    def test_tiled_to_authorable_original_playable_games(self):
        conversion = import_tiled_levels(
            self.intent, self.inputs, human_reviewed=True, authorized=True)
        self.assertEqual(conversion.ignored_external_tileset_metadata, 2)
        self.assertEqual(conversion.proof_steps, self.project.proof.final_state.steps)
        self.assertEqual(len(conversion.source_digests), 2)
        self.assertNotEqual(conversion.world_digest, self.project.world.digest)
        authored = conversion.authored_document()
        self.assertEqual(set(authored), {"schema", "intent", "levels"})
        self.assertEqual(authored["schema"], AUTHORED_SCHEMA)
        world = compile_authored_document(
            authored, authorized=True, human_reviewed=True)
        self.assertEqual(world.digest, conversion.world_digest)
        self.assertEqual(world.algorithm, "skeleton.game_builder.authored-tiles.v1")
        self.assertEqual([level.rows for level in world.levels],
                         [level.rows for level in self.project.world.levels])
        self.assertFalse(conversion.receipt()["external_images_copied"])
        self.assertFalse(conversion.receipt()["copyright_clearance"])
        self.assertFalse(conversion.receipt()["native_consumer_cleared"])
        destination = self.root / "authored.json"
        self.assertEqual(
            write_tiled_authored_json(conversion, destination, authorized=True),
            destination)
        self.assertEqual(json.loads(destination.read_text(encoding="utf-8")), authored)
        self.assertNotIn("example.org", destination.read_text(encoding="utf-8"))
        self.assertNotIn("external-original", destination.read_text(encoding="utf-8"))
        with self.assertRaisesRegex(TiledImportError, "never overwrite"):
            write_tiled_authored_json(conversion, destination, authorized=True)

    def test_tiled_cli_to_full_native_game_studio(self):
        intent_file = self.root / "intent.json"
        intent_file.write_text(json.dumps(self.intent.to_payload()), encoding="utf-8")
        authored_file = self.root / "authored.json"
        args = [
            "--intent", str(intent_file), "--tiled-level", str(self.inputs[0]),
            "--tiled-level", str(self.inputs[1]),
            "--output", str(authored_file),
            "--human-reviewed", "--trusted-local-operator",
        ]
        with redirect_stdout(io.StringIO()) as output:
            self.assertEqual(tiled_main(args), 0)
        tiled_result = json.loads(output.getvalue())
        self.assertEqual(tiled_result["world_digest"],
                         json.loads(authored_file.read_text(encoding="utf-8"))
                         and import_tiled_levels(
                            self.intent, self.inputs,
                            human_reviewed=True, authorized=True).world_digest)
        studio_out = self.root / "consumer-game"
        with redirect_stdout(io.StringIO()) as printed:
            self.assertEqual(studio_main([
                "--intent", str(intent_file),
                "--authored-world", str(authored_file),
                "--output", str(studio_out), "--human-reviewed",
                "--mirror-attempts", "64", "--companion-practice", "1",
                "--trusted-local-operator",
            ]), 0)
        result = json.loads(printed.getvalue())
        self.assertEqual(result["mirror_failures"], 0)
        self.assertEqual(result["consumer_status"], "release-blocked")
        self.assertTrue((studio_out / "index.html").is_file())
        self.assertTrue((studio_out / "godot/project.godot").is_file())
        self.assertTrue((studio_out / "practice/slot-01/godot/project.godot").is_file())
        self.assertTrue((studio_out / "studio/companion_mirror_room.json").is_file())
        self.assertNotIn("https://example.org",
                         (studio_out / "index.html").read_text(encoding="utf-8"))
        self.assertTrue((studio_out / "proof/verified_solution.json").is_file())

    def test_import_rejects_tiled_flip_compression_or_unrecognized_layer(self):
        doc = self.map_json(self.project.world.levels[0])
        for change in ("flip", "object", "infinite", "compression", "size", "gid"):
            with self.subTest(change=change):
                altered = json.loads(json.dumps(doc))
                if change == "flip":
                    altered["layers"][0]["data"][0] |= 0x80000000
                elif change == "object":
                    altered["layers"][0]["type"] = "objectgroup"
                elif change == "infinite":
                    altered["infinite"] = True
                elif change == "compression":
                    altered["layers"][0]["encoding"] = "base64"
                elif change == "size":
                    altered["width"] = 9
                else:
                    altered["layers"][0]["data"][0] = 999
                path = self.root / "corrupt.json"
                path.write_text(json.dumps(altered), encoding="utf-8")
                with self.assertRaises(TiledImportError):
                    import_tiled_levels(
                        self.intent, [path, self.inputs[1]],
                        human_reviewed=True, authorized=True)

    def test_legal_safety_budgets_and_deny_by_default(self):
        with self.assertRaises(PermissionError):
            import_tiled_levels(
                self.intent, self.inputs, human_reviewed=True, authorized=False)
        with self.assertRaises(TiledImportError):
            import_tiled_levels(
                self.intent, self.inputs, human_reviewed=False, authorized=True)
        with self.assertRaises(TiledImportError):
            import_tiled_levels(
                self.intent, self.inputs[:1], human_reviewed=True, authorized=True)
        with self.assertRaises(TiledImportError):
            import_tiled_levels(
                self.intent, self.inputs, human_reviewed=True, authorized=True,
                gid_palette={1: "S"})
        with self.assertRaises(TiledImportError):
            import_tiled_levels(
                self.intent, [self.inputs[0], self.inputs[0]],
                human_reviewed=True, authorized=True)
        rogue = self.root / "symlink.json"
        rogue.symlink_to(self.inputs[0])
        with self.assertRaises(TiledImportError):
            import_tiled_levels(
                self.intent, [rogue, self.inputs[1]],
                human_reviewed=True, authorized=True)
        duplicate = self.root / "duplicate.json"
        duplicate.write_text('{"width":11,"width":11}', encoding="utf-8")
        with self.assertRaises(TiledImportError):
            import_tiled_levels(
                self.intent, [duplicate, self.inputs[1]],
                human_reviewed=True, authorized=True)
        oversized = self.root / "oversized.json"
        oversized.write_bytes(b"x" * 700001)
        with self.assertRaises(TiledImportError):
            import_tiled_levels(
                self.intent, [oversized, self.inputs[1]],
                human_reviewed=True, authorized=True)

    def test_cli_requires_operator_and_review_before_writing(self):
        intent_file = self.root / "intent.json"
        intent_file.write_text(json.dumps(self.intent.to_payload()), encoding="utf-8")
        destination = self.root / "authored.json"
        args = [
            "--intent", str(intent_file),
            "--tiled-level", str(self.inputs[0]),
            "--tiled-level", str(self.inputs[1]),
            "--output", str(destination),
        ]
        self.assertEqual(tiled_main(args), 2)
        self.assertFalse(destination.exists())
        self.assertEqual(tiled_main(args + ["--trusted-local-operator"]), 2)
        self.assertFalse(destination.exists())
        self.assertEqual(tiled_main(args + ["--trusted-local-operator",
                                            "--human-reviewed"]), 0)
        self.assertTrue(destination.exists())


if __name__ == "__main__":
    unittest.main()
