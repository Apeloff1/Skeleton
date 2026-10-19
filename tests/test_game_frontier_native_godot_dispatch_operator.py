"""Operator-approved dispatch preflight and tamper rejection before real Godot."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from scripts.run_game_frontier_godot_dispatch import _write_new,GodotDispatchError
from skeleton.jeeves.game_frontier_native_engine_dispatch import canonical_dispatch_json
from tests.test_game_frontier_native_engine_dispatch import NativeEngineDispatchTests


class NativeGodotDispatchOperatorTests(NativeEngineDispatchTests):
    def test_canonical_file_digest_matches_exact_written_bytes(self):
        from skeleton.jeeves.game_frontier_native_engine_dispatch import dispatch_file_sha256
        import hashlib
        manifest=self.dispatch()
        with TemporaryDirectory() as temp:
            path=Path(temp)/"native_gameplay_dispatch.json"
            _write_new(path,canonical_dispatch_json(manifest))
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),
                             dispatch_file_sha256(manifest))
            self.assertEqual(json.loads(path.read_text()),manifest)
            with self.assertRaises(GodotDispatchError):
                _write_new(path,"{}")
            self.assertEqual(json.loads(path.read_text()),manifest)

    def test_no_symlink_dispatch_write(self):
        with TemporaryDirectory() as temp:
            folder=Path(temp)
            existing=folder/"exists.json"
            existing.write_text("{}")
            redirected=folder/"link.json"
            redirected.symlink_to(existing)
            with self.assertRaises(GodotDispatchError):
                _write_new(redirected,"{}")
            self.assertEqual(existing.read_text(),"{}")
