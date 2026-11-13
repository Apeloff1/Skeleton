"""Operator headless Godot qualification wrapper; mocked binary tests only.

Tests verify fail-closed tool execution and source hash lineage. They do not
claim Godot 4 was installed or native graphics/physics was actually run.
"""
from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from scripts.qualify_game_frontier_godot import (
    qualify_project,GodotQualificationError,
)


class NativeHeadlessScriptTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.project=self.root/"game"
        (self.project/"frontier/data").mkdir(parents=True)
        (self.project/"project.godot").write_text('[application]\n')
        (self.project/"frontier/frontier_scene.tscn").write_text(
            '[gd_scene format=3]\n')
        (self.project/"frontier/frontier_scene.gd").write_text(
            'extends Node3D\n')
        (self.project/"frontier/data/scene.json").write_text(json.dumps({
            "schema":"skeleton.game.frontier_godot_overlay.v1",
            "native_capture":{"enabled":False},
        }))
        self.binary=self.root/"godot_mock"
        self.write_binary("import sys\nprint('Mock stage: '+str(sys.argv[1:]))\n")

    def write_binary(self,script):
        self.binary.write_text("#!/usr/bin/env python3\n"+script)
        self.binary.chmod(0o700)
        self.pin=sha256(self.binary.read_bytes()).hexdigest()

    def qualify(self,**args):
        return qualify_project(
            binary=self.binary,expected_sha256=self.pin,
            project=self.project,frames=5,**args)

    def test_explicit_local_binary_two_stage_receipts(self):
        proof=self.qualify()
        self.assertEqual(len(proof["native_stages"]),2)
        self.assertEqual([s["stage"] for s in proof["native_stages"]],
                         ["import","play"])
        self.assertEqual(proof["native_playback_frames_requested"],5)
        self.assertEqual(len(proof["receipt_digest"]),64)
        self.assertEqual(proof["authority"],
            "operator_run_local_headless_import_play_not_GPU_or_gameplay_attestation")

    def test_operator_cli_invokes_documented_scene_and_import_flags(self):
        self.write_binary(
            "from pathlib import Path\n"
            "import sys\n"
            "with Path('argv.log').open('a') as output:\n"
            "    output.write(' '.join(sys.argv[1:]) + '\\n')\n"
        )
        self.qualify()
        phases=(self.project/"argv.log").read_text().splitlines()
        self.assertEqual(len(phases),2)
        self.assertIn("--import",phases[0])
        self.assertIn("--scene",phases[1])
        self.assertIn("--quit-after 5",phases[1])
        self.assertIn("res://frontier/frontier_scene.tscn",phases[1])

    def test_refuse_unsigned_binary_changes(self):
        with self.assertRaises(GodotQualificationError):
            qualify_project(binary=self.binary,expected_sha256="a"*64,
                            project=self.project)
        self.binary.write_text(self.binary.read_text()+"#unexpected\n")
        with self.assertRaises(GodotQualificationError):
            self.qualify()

    def test_nonzero_or_explicit_native_script_error_fails(self):
        self.write_binary("import sys\nsys.exit(3)\n")
        with self.assertRaises(GodotQualificationError):
            self.qualify()
        self.write_binary("print('SCRIPT ERROR: parse line 4')\n")
        with self.assertRaises(GodotQualificationError):
            self.qualify()

    def test_missing_scene_or_corrupt_scene_schema_rejected(self):
        (self.project/"frontier/frontier_scene.tscn").unlink()
        with self.assertRaises(GodotQualificationError):
            self.qualify()
        (self.project/"frontier/frontier_scene.tscn").write_text(
            '[gd_scene format=3]\n')
        (self.project/"frontier/data/scene.json").write_text("{}")
        with self.assertRaises(GodotQualificationError):
            self.qualify()

    def test_native_limits_are_explicit(self):
        with self.assertRaises(GodotQualificationError):
            qualify_project(binary=self.binary,expected_sha256=self.pin,
                            project=self.project,frames=0)
        with self.assertRaises(GodotQualificationError):
            qualify_project(binary=self.binary,expected_sha256=self.pin,
                            project=self.project,timeout_seconds=0)


if __name__=="__main__":
    unittest.main()
