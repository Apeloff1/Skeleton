"""Contract, reproducibility and real-world export tests for two game runtimes."""
from __future__ import annotations

from contextlib import redirect_stdout
from dataclasses import replace
from hashlib import sha256
import io
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from skeleton.ai.game_builder.dual_runtime_cli import main
from skeleton.ai.game_builder.playable_compiler import compile_authored_game
from skeleton.ai.game_builder.dual_runtime_export import (
    DualRuntimeExportError,
    export_dual_runtime_package,
    render_dual_runtime_package,
)
from skeleton.ai.game_builder.playable_compiler import compile_original_game
from skeleton.ai.game_builder.playable_world import GameBuildIntent


class DualRuntimeGameTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.intent = GameBuildIntent(
            project_id="original-expedition-2026",
            title='The <Original> Adventure',
            subtitle="Original tiles; no borrowed character art.",
            seed=20361217, width=15, height=13, levels=2,
            collectibles_per_level=2, hazards_per_level=3,
            theme="ocean", starting_health=4,
        )
        cls.compiled = compile_original_game(cls.intent, authorized=True)
        cls.bundle = render_dual_runtime_package(cls.compiled, authorized=True)

    def test_shared_world_and_winning_python_proof(self) -> None:
        manifest = self.bundle.manifest
        world = json.loads(self.bundle.files["godot/world.json"])
        trace = json.loads(self.bundle.files["proof/verified_solution.json"])
        self.assertEqual(world["world_digest"], self.compiled.world.digest)
        self.assertEqual(trace["world_digest"], self.compiled.world.digest)
        self.assertEqual(manifest["proof_digest"], self.compiled.proof.digest)
        self.assertEqual(
            json.loads(self.bundle.files["godot/proof.json"]), trace
        )
        self.assertEqual(trace["final_state"]["status"], "won")
        self.assertEqual(trace["final_state"]["health"], self.intent.starting_health)
        self.assertEqual(len(world["levels"]), self.intent.levels)
        self.assertEqual(world["intent"]["title"], self.intent.title)
        self.assertIn("Content-Security-Policy", self.bundle.files["index.html"].decode())
        self.assertEqual(
            sha256(self.bundle.files["index.html"]).hexdigest(),
            self.compiled.playable.html_sha256,
        )
        self.assertFalse(manifest["godot_hardware_tested"])
        self.assertEqual(manifest["targets"]["godot-4.2"], "source-rendered-unexecuted")

    def test_byte_identical_render_and_manifest_file_digests(self) -> None:
        replay = render_dual_runtime_package(self.compiled, authorized=True)
        self.assertEqual(replay.files, self.bundle.files)
        self.assertEqual(replay.manifest, self.bundle.manifest)
        self.assertEqual(
            set(self.bundle.files), set(self.bundle.manifest["files"]) | {"release.json"}
        )
        for path, digest in self.bundle.manifest["files"].items():
            self.assertEqual(sha256(self.bundle.files[path]).hexdigest(), digest)

    def test_native_source_provides_real_gameplay_rules(self) -> None:
        script = self.bundle.files["godot/scripts/main.gd"].decode()
        for mechanic in (
            "extends Control", "func _step(", "func _enter_level(",
            'tile == "C"', 'tile == "H" and entered',
            'tile == "G" and collected.size()', "score += 100",
            "health -= 1", "MAX_ACTIONS = 20000",
            "func _undo()", "func _save_actions()", "func _load_actions()",
            "func _draw()", "func _unhandled_key_input(",
            "func _unhandled_input(", "JOY_BUTTON_DPAD_UP",
            "JOY_BUTTON_DPAD_DOWN", "JOY_BUTTON_B",
            "InputEventScreenTouch", "touch_origin",
            "func _verify_native_proof()", "NATIVE_REPLAY_OK",
        ):
            with self.subTest(mechanic=mechanic):
                self.assertIn(mechanic, script)
        self.assertNotIn(self.intent.title, script)
        self.assertNotIn(self.intent.subtitle, script)
        presets = self.bundle.files["godot/export_presets.cfg"].decode()
        self.assertIn('platform="Linux"', presets)
        self.assertIn('platform="Windows Desktop"', presets)
        self.assertIn('include_filter="*.json"', presets)
        self.assertIn('binary_format/embed_pck=true', presets)
        self.assertNotIn('codesign/enable=true', presets)
        self.assertIn("run/main_scene", self.bundle.files["godot/project.godot"].decode())
        self.assertIn("ExtResource", self.bundle.files["godot/scenes/main.tscn"].decode())

    def test_export_is_atomic_and_existing_projects_are_never_overwritten(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "game"
            self.assertEqual(
                export_dual_runtime_package(self.bundle, output, authorized=True), output
            )
            for relative, payload in self.bundle.files.items():
                self.assertEqual((output / relative).read_bytes(), payload)
            with self.assertRaisesRegex(DualRuntimeExportError, "already exists"):
                export_dual_runtime_package(self.bundle, output, authorized=True)
            self.assertEqual((output / "release.json").read_bytes(), self.bundle.files["release.json"])
            self.assertFalse(list(Path(temp).glob(".game-export-*")))

    def test_refuses_unauthorized_tampered_or_symlink_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "export"
            with self.assertRaises(PermissionError):
                render_dual_runtime_package(self.compiled, authorized=False)
            with self.assertRaises(PermissionError):
                export_dual_runtime_package(self.bundle, output, authorized=False)
            self.assertFalse(output.exists())
            old = self.bundle.files["index.html"]
            try:
                self.bundle.files["index.html"] = b"tampered"
                with self.assertRaisesRegex(DualRuntimeExportError, "changed"):
                    export_dual_runtime_package(self.bundle, output, authorized=True)
                self.assertFalse(output.exists())
            finally:
                self.bundle.files["index.html"] = old
            external = Path(temp) / "external"
            external.mkdir()
            link = Path(temp) / "link"
            link.symlink_to(external, target_is_directory=True)
            with self.assertRaises(DualRuntimeExportError):
                export_dual_runtime_package(self.bundle, link, authorized=True)
            with self.assertRaises(DualRuntimeExportError):
                export_dual_runtime_package(
                    self.bundle, Path(temp) / "link" / "nested", authorized=True
                )

    def test_cli_build_and_operator_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            intent_path = Path(temp) / "intent.json"
            intent_path.write_text(json.dumps(self.intent.to_payload()), encoding="utf-8")
            output = Path(temp) / "my-game"
            params = ["--intent", str(intent_path), "--output", str(output)]
            with self.assertRaises(SystemExit):
                main(["--bad-flag"])
            self.assertEqual(main(params), 2)
            self.assertFalse(output.exists())
            captured = io.StringIO()
            with redirect_stdout(captured):
                self.assertEqual(main(params + ["--trusted-local-operator"]), 0)
            result = json.loads(captured.getvalue())
            self.assertEqual(result["world_digest"], self.compiled.world.digest)
            self.assertEqual(result["output"], str(output))
            self.assertFalse(result["godot_hardware_tested"])
            self.assertTrue((output / "godot/project.godot").exists())

    def test_optional_real_godot_scene_load(self) -> None:
        engine = shutil.which("godot") or shutil.which("godot4")
        if engine is None:
            self.skipTest("Godot 4 engine not installed: no native runtime validation")
        with tempfile.TemporaryDirectory() as temp:
            output = export_dual_runtime_package(
                self.bundle, Path(temp) / "game", authorized=True
            )
            result = subprocess.run(
                [engine, "--headless", "--path", str(output / "godot"),
                 "--quit-after", "200", "--", "--verify-proof"],
                capture_output=True, text=True, timeout=45, check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("NATIVE_REPLAY_OK", result.stdout + result.stderr)
            self.assertNotIn("SCRIPT ERROR", result.stdout + result.stderr)
            self.assertNotIn("Parse Error", result.stdout + result.stderr)


    def test_optional_godot_authored_world_replays_native(self) -> None:
        engine = shutil.which("godot") or shutil.which("godot4")
        if engine is None:
            self.skipTest("Godot 4 not installed")
        authored = compile_authored_game(
            self.intent, [list(level.rows) for level in self.compiled.world.levels],
            human_reviewed=True, authorized=True,
        )
        bundle = render_dual_runtime_package(authored, authorized=True)
        with tempfile.TemporaryDirectory() as temp:
            output = export_dual_runtime_package(
                bundle, Path(temp) / "authored", authorized=True
            )
            proc = subprocess.run(
                [engine, "--headless", "--path", str(output / "godot"),
                 "--quit-after", "200", "--", "--verify-proof"],
                capture_output=True, text=True, timeout=45, check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertIn("NATIVE_REPLAY_OK", proc.stdout + proc.stderr)

    def test_optional_godot_tampered_proof_fails_closed(self) -> None:
        engine = shutil.which("godot") or shutil.which("godot4")
        if engine is None:
            self.skipTest("Godot 4 not installed")
        with tempfile.TemporaryDirectory() as temp:
            output = export_dual_runtime_package(
                self.bundle, Path(temp) / "game", authorized=True
            )
            trace = output / "godot" / "proof.json"
            raw = json.loads(trace.read_text(encoding="utf-8"))
            raw["final_state"]["score"] += 10000
            trace.write_text(json.dumps(raw), encoding="utf-8")
            proc = subprocess.run(
                [engine, "--headless", "--path", str(output / "godot"),
                 "--quit-after", "200", "--", "--verify-proof"],
                capture_output=True, text=True, timeout=45, check=False,
            )
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn("NATIVE_REPLAY_ERROR", proc.stdout + proc.stderr)
            self.assertIn("score", proc.stdout + proc.stderr)


if __name__ == "__main__":
    unittest.main()
