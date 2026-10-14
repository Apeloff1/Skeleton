"""Offline editor source contract, CSP, and gameplay-authoring handoff tests."""
from __future__ import annotations

from hashlib import sha256
import base64
from html import unescape
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
import unittest

from skeleton.ai.game_builder.authored_tiles import compile_authored_document
from skeleton.ai.game_builder.dual_runtime_export import render_dual_runtime_package
from skeleton.ai.game_builder.playable_compiler import (
    compile_authored_game, compile_original_game,
)
from skeleton.ai.game_builder.playable_world import GameBuildIntent
from skeleton.ai.game_builder.tile_editor_export import render_tile_editor


class VisualTileEditorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.intent = GameBuildIntent(
            project_id="editor-world-2026", title="Original <Cavern> & Sky",
            subtitle='The "new" planet </script><script>alert(1)</script>',
            seed=2040, width=11, height=11, levels=2,
            collectibles_per_level=2, hazards_per_level=3,
            theme="forest", starting_health=4,
        )
        cls.project = compile_original_game(cls.intent, authorized=True)
        cls.editor = render_tile_editor(cls.project.world, authorized=True)

    def test_editor_source_is_byte_stable_and_data_only(self) -> None:
        repeat = render_tile_editor(self.project.world, authorized=True)
        self.assertEqual(self.editor, repeat)
        self.assertEqual(self.editor.source_sha256, sha256(self.editor.content).hexdigest())
        text = self.editor.content.decode("utf-8")
        self.assertLess(len(self.editor.content), 500_000)
        self.assertTrue(text.startswith("<!doctype html>"))
        self.assertEqual(text.count("<script>"), 1)
        self.assertEqual(text.count("</script>"), 1)
        self.assertNotIn("<Cavern>", text)
        self.assertNotIn('<script>alert(1)</script>', text)
        self.assertIn('Offline', text)
        self.assertIn('connect-src &#x27;none&#x27;', text)
        self.assertIn('skeleton.game_builder.authored_tiles.v1', text)
        self.assertIn('Show safe route', text)
        self.assertIn('Export authored JSON', text)
        self.assertIn('Accessible text-grid editor', text)

    def test_editor_inline_js_and_style_are_exactly_csp_hashed(self) -> None:
        text = self.editor.content.decode("utf-8")
        style = re.search(r"<style>(.*?)</style>", text, flags=re.DOTALL)
        script = re.search(r"<script>(.*?)</script>", text, flags=re.DOTALL)
        assert style is not None and script is not None
        for policy, body in (("style-src", style.group(1)), ("script-src", script.group(1))):
            digest = base64.b64encode(sha256(body.encode("utf-8")).digest()).decode("ascii")
            self.assertIn(policy + " &#x27;sha256-" + digest + "&#x27;", text)
        self.assertNotIn("eval(", script.group(1))
        self.assertNotIn("fetch(", script.group(1))
        self.assertNotIn("XMLHttpRequest", script.group(1))
        self.assertNotIn("<script>", script.group(1))
        if shutil.which("node"):
            with tempfile.TemporaryDirectory() as tmp:
                source = Path(tmp) / "editor.mjs"
                source.write_text(script.group(1), encoding="utf-8")
                result = subprocess.run(
                    ["node", "--check", str(source)],
                    capture_output=True, text=True, timeout=15, check=False,
                )
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_bundled_editor_matches_native_world_and_does_not_publish(self) -> None:
        bundle = render_dual_runtime_package(self.project, authorized=True)
        self.assertEqual(bundle.files["tile-editor.html"], self.editor.content)
        self.assertEqual(
            bundle.manifest["files"]["tile-editor.html"], self.editor.source_sha256
        )
        self.assertFalse(bundle.manifest["automatic_publication"])
        self.assertEqual(len(bundle.files["tile-editor.html"]), len(self.editor.content))
        self.assertEqual(
            json.loads(bundle.files["godot/world.json"])["world_digest"],
            self.project.world.digest,
        )

    def test_editor_seed_document_is_valid_canonical_authored_game(self) -> None:
        # The saved initial geometry is a usable *authored* project. After
        # editing, the same strict Python admission and proof path applies.
        intent = self.project.world.intent
        doc = {
            "schema": "skeleton.game_builder.authored_tiles.v1",
            "intent": intent.to_payload(),
            "levels": [list(level.rows) for level in self.project.world.levels],
        }
        authored = compile_authored_document(
            doc, human_reviewed=True, authorized=True
        )
        compiled = compile_authored_game(
            intent, doc["levels"], human_reviewed=True, authorized=True
        )
        self.assertEqual(authored.digest, compiled.world.digest)
        self.assertNotEqual(authored.digest, self.project.world.digest)
        self.assertEqual(compiled.proof.final_state.status, "won")
        self.assertEqual(
            compiled.proof.final_state.health, intent.starting_health
        )
        release = render_dual_runtime_package(compiled, authorized=True)
        self.assertEqual(
            release.manifest["world_algorithm"], "skeleton.game_builder.authored-tiles.v1"
        )
        self.assertEqual(release.files["godot/world.json"][:1], b"{")

    def test_no_implicit_operator_authorization(self) -> None:
        with self.assertRaises(PermissionError):
            render_tile_editor(self.project.world, authorized=False)
        with self.assertRaises(TypeError):
            render_tile_editor({}, authorized=True)


if __name__ == "__main__":
    unittest.main()
