"""Designer-authored tile imports must run through the real playable game engine."""
from __future__ import annotations

from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest

from skeleton.ai.game_builder.authored_tiles import (
    AUTHORED_ALGORITHM, AUTHORED_SCHEMA, AuthoredGameError,
    compile_authored_document, compile_authored_world,
    read_authored_document,
)
from skeleton.ai.game_builder.dual_runtime_cli import main
from skeleton.ai.game_builder.dual_runtime_export import render_dual_runtime_package
from skeleton.ai.game_builder.playable_compiler import compile_authored_game
from skeleton.ai.game_builder.playable_world import GameBuildIntent, PlayableWorldError
from skeleton.ai.game_builder.playable_simulation import demonstrate_solvable


ROWS = [
    "#########",
    "#S..C...#",
    "#.#####.#",
    "#.......#",
    "#...H...#",
    "#.......#",
    "#..C..G.#",
    "#.......#",
    "#########",
]


class AuthoredWorldTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.intent = GameBuildIntent(
            project_id="original-editor-test",
            title="Cave </script> & Beyond",
            subtitle="Fully original designer-authored 2D tile geometry.",
            seed=42, width=9, height=9, levels=1,
            collectibles_per_level=2, hazards_per_level=1,
            theme="arcade", starting_health=3,
        )
        cls.document = {
            "schema": AUTHORED_SCHEMA, "intent": cls.intent.to_payload(),
            "levels": [ROWS],
        }

    def test_authored_world_is_playable_with_proved_safe_path(self) -> None:
        world = compile_authored_document(
            self.document, human_reviewed=True, authorized=True,
        )
        self.assertEqual(world.algorithm, AUTHORED_ALGORITHM)
        self.assertEqual(world.levels[0].rows, tuple(ROWS))
        replay = demonstrate_solvable(world, authorized=True)
        self.assertEqual(replay.final_state.status, "won")
        self.assertEqual(replay.final_state.health, self.intent.starting_health)
        self.assertTrue(world.levels[0].safe_solution)

    def test_design_export_uses_same_binary_free_gameplay_contract(self) -> None:
        compiled = compile_authored_game(
            self.intent, [ROWS], human_reviewed=True, authorized=True,
        )
        package = render_dual_runtime_package(compiled, authorized=True)
        native = json.loads(package.files["godot/world.json"])
        proof = json.loads(package.files["proof/verified_solution.json"])
        self.assertEqual(package.manifest["world_algorithm"], AUTHORED_ALGORITHM)
        self.assertEqual(native["world_digest"], compiled.world.digest)
        self.assertEqual(proof["final_state"]["status"], "won")
        self.assertEqual(native["levels"][0]["rows"], ROWS)
        self.assertNotIn(b"</script>", package.files["godot/scripts/main.gd"])
        self.assertNotIn(b"Cave </script>", package.files["index.html"])
        self.assertFalse(package.manifest["automatic_publication"])

    def test_rejects_unreviewed_and_unauthorized_imports(self) -> None:
        with self.assertRaises(PermissionError):
            compile_authored_world(
                self.intent, [ROWS], human_reviewed=True, authorized=False,
            )
        with self.assertRaisesRegex(AuthoredGameError, "human-reviewed"):
            compile_authored_world(
                self.intent, [ROWS], human_reviewed=False, authorized=True,
            )
        with self.assertRaisesRegex(AuthoredGameError, "human-reviewed"):
            compile_authored_document(
                self.document, human_reviewed=False, authorized=True,
            )

    def test_rejects_unreachable_unbalanced_and_unrecognized_tiles(self) -> None:
        unreachable = list(ROWS)
        unreachable[1] = "#S#.C...#"
        unreachable[2] = "#######.#"
        with self.assertRaisesRegex(AuthoredGameError, "safe winning route"):
            compile_authored_world(
                self.intent, [unreachable], human_reviewed=True, authorized=True,
            )
        invalid = list(ROWS)
        invalid[3] = "#...X...#"
        with self.assertRaisesRegex(AuthoredGameError, "unknown or uneven"):
            compile_authored_world(
                self.intent, [invalid], human_reviewed=True, authorized=True,
            )
        with self.assertRaisesRegex(AuthoredGameError, "collectible count"):
            compile_authored_world(
                self.intent, [[r.replace("C", ".", 1) if i == 1 else r
                               for i, r in enumerate(ROWS)]],
                human_reviewed=True, authorized=True,
            )
        with self.assertRaisesRegex(AuthoredGameError, "level count"):
            compile_authored_world(
                self.intent, [], human_reviewed=True, authorized=True,
            )
        with self.assertRaisesRegex(AuthoredGameError, "structure"):
            compile_authored_document(
                {**self.document, "unsafe_script": "print('hello')"},
                human_reviewed=True, authorized=True,
            )

    def test_json_duplicate_keys_and_oversize_are_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "level.json"
            source.write_text('{"schema":"a","schema":"b"}', encoding="utf-8")
            with self.assertRaisesRegex(AuthoredGameError, "duplicate"):
                read_authored_document(source, authorized=True)
            source.write_bytes(b"x" * 100_001)
            with self.assertRaisesRegex(AuthoredGameError, "exceeds"):
                read_authored_document(source, authorized=True)
            source.unlink()
            source.symlink_to(Path(temp) / "missing.json")
            with self.assertRaisesRegex(AuthoredGameError, "regular"):
                read_authored_document(source, authorized=True)

    def test_cli_compiles_reviewed_authored_project_not_a_generated_substitute(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            intent_path = Path(temp) / "intent.json"
            intent_path.write_text(json.dumps(self.intent.to_payload()), encoding="utf-8")
            edited_path = Path(temp) / "editor-world.json"
            edited_path.write_text(json.dumps(self.document), encoding="utf-8")
            output = Path(temp) / "native-project"
            args = [
                "--intent", str(intent_path), "--authored-world", str(edited_path),
                "--output", str(output), "--trusted-local-operator",
            ]
            self.assertEqual(main(args), 2)  # Explicit geometry review required.
            self.assertFalse(output.exists())
            with redirect_stdout(io.StringIO()) as stdout:
                self.assertEqual(main(args + ["--human-reviewed"]), 0)
            result = json.loads(stdout.getvalue())
            manifest = json.loads((output / "release.json").read_text())
            self.assertEqual(manifest["world_algorithm"], AUTHORED_ALGORITHM)
            self.assertEqual(result["world_digest"], manifest["world_digest"])
            self.assertEqual(
                json.loads((output / "godot/world.json").read_text())
                ["levels"][0]["rows"], ROWS,
            )
            self.assertNotIn("Cave </script>", (output / "index.html").read_text())
            with self.assertRaises(AuthoredGameError):
                compile_authored_document(
                    {**self.document, "schema": "wrong"},
                    human_reviewed=True, authorized=True,
                )


if __name__ == "__main__":
    unittest.main()
