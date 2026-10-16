"""Specialized tests for generated original game media and real HTTP E2E.

Run: python -m unittest tests.test_jeeves_director_media_e2e
This verifies executable Python/Godot SOURCE integrity and real local Python
HTTP playthrough; it does not claim Godot rendering or physical controllers.
"""
from __future__ import annotations

import json
from pathlib import Path
import struct
import tempfile
import unittest
import wave

from skeleton.ai.game_builder.quest_scene_forge import forge_director
from skeleton.developer.game_cli import SCHEMA as WORKSPACE_SCHEMA, run_game_cli
from skeleton.developer.jeeves_game_director_media import generate
from skeleton.developer.jeeves_game_director_atlas import export, verify
from skeleton.developer.jeeves_game_director_e2e import run


class DirectorMediaE2ETests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "original_game"
        self.root.mkdir()
        (self.root / "design").mkdir()
        (self.root / "skeleton.game.json").write_text(json.dumps({
            "schema": WORKSPACE_SCHEMA,
            "name": "original_game",
            "vision": "An original city with different quest endings",
            "era": "extraction_now", "archetype": "auto",
        }))
        self.world = forge_director(
            "original_game", seed=43,
            regions=("harbor", "market", "tower", "garden"),
            quest_types=("main_story", "investigation"), stages=2,
        )
        self.source = "design/director_campaign_source.json"
        (self.root / self.source).write_text(json.dumps({
            "schema": "skeleton.jeeves.director_campaign_source.v1",
            "author_review_acknowledged": True,
            "director_world": self.world.payload(),
        }))

    def test_original_media_bytes_are_reproducible_and_valid(self):
        first, catalog = generate(self.world)
        again, same_catalog = generate(self.world)
        self.assertEqual(first, again)
        self.assertEqual(catalog, same_catalog)
        self.assertEqual(catalog["original_exported_scene_image_count"], 4)
        self.assertGreaterEqual(catalog["original_exported_audio_music_count"], 1)
        self.assertFalse(catalog["professional_asset_quality_verified"])
        scene = self.world.scenes[0]
        png = first["media/scene_" + scene.key + ".png"]
        self.assertTrue(png.startswith(b"\x89PNG\r\n\x1a\n"))
        self.assertEqual(struct.unpack(">II", png[16:24]), (256, 144))
        for filename, raw in first.items():
            if filename.endswith(".wav"):
                with tempfile.TemporaryFile() as buf:
                    buf.write(raw)
                    buf.seek(0)
                    with wave.open(buf, "rb") as sample:
                        self.assertEqual(sample.getnchannels(), 1)
                        self.assertEqual(sample.getframerate(), 16000)
                        self.assertEqual(sample.getnframes(), 16000)

    def test_export_integrity_and_godot_import_sidecars(self):
        result = export(self.root, source=self.source)
        location = Path(result["path"])
        self.assertTrue(location.name.endswith("-live-v4"))
        self.assertTrue((location / "media_catalog.json").is_file())
        self.assertTrue((location / "media").is_dir())
        self.assertTrue(result["manifest"]["native_original_audio_playback_in_source"])
        self.assertTrue(result["manifest"]["generated_original_png_backdrops"] == 4)
        self.assertTrue(verify(self.root, source=self.source)["source_manifest_verified"])
        script = (location / "director_stage.gd").read_text()
        self.assertIn("AudioStreamPlayer.new()", script)
        self.assertIn("draw_texture_rect(backdrop", script)
        self.assertIn("toggle_music()", script)
        (location / ".godot" / "imported").mkdir(parents=True)
        (location / ".godot" / "imported" / "ignored.ctex").write_bytes(b"cache")
        scene = self.world.scenes[0]
        img = location / "media" / ("scene_" + scene.key + ".png")
        (location / "media" / (img.name + ".import")).write_text("generated import sidecar")
        self.assertTrue(verify(self.root, source=self.source)["source_manifest_verified"])
        img.write_bytes(img.read_bytes() + b"tamper")
        with self.assertRaises(ValueError):
            verify(self.root, source=self.source)

    def test_http_e2e_replays_complete_story_and_restart(self):
        report = run(self.root, source=self.source, routes=2)
        self.assertTrue(report["all_routes_completed_over_real_http"])
        self.assertTrue(report["isolated_source_and_sessions_cleaned_up"])
        self.assertTrue(report["actual_service_restart_and_journal_recovery_tested"])
        self.assertEqual(report["route_count"], 2)
        self.assertTrue(all(r["stale_post_rejected"] and r["complete_campaign"]
                            for r in report["results"]))
        self.assertTrue(all(r["all_stage_results"] == 4 for r in report["results"]))
        self.assertFalse(report["godot_binary_executed"])
        self.assertFalse(report["human_player_tested"])
        self.assertFalse((self.root / ".jeeves" / "director_sessions").exists())

    def test_cli_rejects_unrelated_e2e_options(self):
        report = run_game_cli([
            "jeeves", "director-loopback-e2e", "--project", str(self.root),
            "--source", self.source, "--kind", "quest",
        ])
        self.assertFalse(report["ok"])
        with self.assertRaises(ValueError):
            run(self.root, source=self.source, routes=0)


if __name__ == "__main__":
    unittest.main()
