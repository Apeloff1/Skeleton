"""Game director browser compilation and original cinematic test coverage."""
from __future__ import annotations
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
import unittest

from skeleton.ai.game_builder.quest_scene_forge import forge_director
from skeleton.ai.game_builder.quest_scene_export import render_director_browser
from skeleton.ai.game_builder.quest_scene_engine import DirectorError


class DirectorBrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.world = forge_director(
            "cinematic_director", seed=733,
            regions=tuple(f"scene_region_{i:02d}" for i in range(10)),
            quest_types=("main_story", "escort_leash", "combat", "rival_story"),
            stages=3,
        )

    def test_original_nonlinear_quest_game_is_independently_playable(self):
        out = render_director_browser(self.world, authorized=True)
        self.assertEqual(out.world_digest, self.world.digest)
        self.assertEqual(out.source_sha256,
                         render_director_browser(self.world, authorized=True).source_sha256)
        html = out.html.decode()
        self.assertIn("Content-Security-Policy", html)
        self.assertIn("connect-src &#x27;none&#x27;", html)
        self.assertIn("script-src", html)
        self.assertIn("function action(ev)", html)
        self.assertIn("function cinema(trigger)", html)
        self.assertIn('id="stage-screen"', html)
        self.assertIn('id="stage-cast"', html)
        self.assertIn("function applyCinematicCue(cue)", html)
        self.assertIn('cue.kind==="camera_zoom"', html)
        self.assertIn('cue.kind==="actor_move"', html)
        self.assertIn('cue.kind==="lighting"', html)
        self.assertIn('cue.kind==="subtitle"', html)
        self.assertIn("function allowed()", html)
        self.assertIn("function render()", html)
        self.assertIn("time_target", html)
        self.assertIn("quest_00", html)
        self.assertIn("escort_leash", html)
        self.assertIn('"optional"', html)
        self.assertIn('"cues"', html)
        self.assertIn('"invariant_goal"', html)

    def test_embedded_javascript_syntax_and_no_unreviewed_external_assets(self):
        html = render_director_browser(self.world, authorized=True).html.decode()
        scripts = re.findall(r"<script>(.*?)</script>", html, re.DOTALL)
        self.assertEqual(len(scripts), 1)
        if shutil.which("node"):
            with tempfile.TemporaryDirectory() as folder:
                path = Path(folder) / "director-preview.js"
                path.write_text(scripts[0], encoding="utf-8")
                result = subprocess.run(
                    ["node", "--check", str(path)], capture_output=True, text=True,
                    timeout=10)
                self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("https://", html)
        self.assertNotIn("http://", html)
        self.assertNotIn("<iframe", html)

    def test_authorization_and_world_type(self):
        with self.assertRaises(PermissionError):
            render_director_browser(self.world, authorized=False)
        with self.assertRaises(DirectorError):
            render_director_browser(None, authorized=True)


if __name__ == "__main__":
    unittest.main()
