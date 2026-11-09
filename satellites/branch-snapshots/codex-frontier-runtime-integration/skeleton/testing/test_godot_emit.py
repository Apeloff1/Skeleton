"""End-to-end Godot emit tests: blueprint → emit → verify → repair loop."""

from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path


class TestGodotEmitToVerify(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _emitted(self):
        from skeleton.forge.eras import compile_era
        from skeleton.forge.godot_emit import emit_godot
        pack = compile_era("extraction_now")
        return emit_godot(pack, title="Emit E2E")

    def test_emit_produces_godot_project(self):
        files = self._emitted()
        self.assertIn("project.godot", files)
        self.assertTrue(any(p.endswith(".gd") for p in files))
        self.assertTrue(any(p.endswith(".tscn") for p in files))

    def test_emitted_project_passes_static_check(self):
        from skeleton.forge.gdscript_check import check_files
        problems = check_files(self._emitted())
        self.assertEqual(problems, [])

    def test_emitted_project_accepted_by_verifier(self):
        from skeleton.intelligence.forge_verifier import ForgeVerifier
        report = ForgeVerifier(root=self.tmp).verify(self._emitted(), request="emit e2e")
        self.assertTrue(report.accepted, f"rejected: {report.reason} {list(report.blocking_issues)[:5]}")

    def test_verify_loop_accepts_emitted_project(self):
        from skeleton.forge.verify_loop import forge_verify_until_green
        result = forge_verify_until_green(self._emitted(), request="emit e2e", root=self.tmp)
        self.assertTrue(result["accepted"])
        self.assertEqual(result["trace"]["stopped_reason"], "accepted")

    def test_materialise_godot_no_repair(self):
        from skeleton.forge.universal import Forge
        forge = Forge()
        bp = forge.new_blueprint("godot-plain")
        forge.instantiate(bp, "player", "hero")
        forge.instantiate(bp, "sink", "output")
        bp.connect(("hero", "intent"), ("output", "in"))
        result = forge.materialise(bp, era="extraction_now", target="godot", repair=False)
        self.assertIn("files", result)
        self.assertIn("project.godot", result["files"])
        self.assertTrue(result["verification"]["accepted"])

    def test_materialise_godot_with_repair(self):
        from skeleton.forge.universal import Forge
        forge = Forge()
        bp = forge.new_blueprint("godot-repair")
        forge.instantiate(bp, "player", "hero")
        forge.instantiate(bp, "sink", "output")
        bp.connect(("hero", "intent"), ("output", "in"))
        result = forge.materialise(bp, era="extraction_now", target="godot", repair=True, max_rounds=2)
        self.assertTrue(result["verification"]["accepted"])
        self.assertEqual(result["verify_loop"]["stopped_reason"], "accepted")
        self.assertIn("project.godot", result["files"])

    def test_quality_ledger_records_materialise(self):
        from skeleton.forge.universal import Forge
        from skeleton.organism.quality_state import load_quality

        forge = Forge(root=self.tmp)
        bp = forge.new_blueprint("godot-ledger")
        forge.instantiate(bp, "player", "hero")
        forge.instantiate(bp, "sink", "output")
        bp.connect(("hero", "intent"), ("output", "in"))
        forge.materialise(bp, era="extraction_now", target="godot", repair=False)

        rows = load_quality(root=self.tmp, surface="forge")
        self.assertGreater(len(rows), 0)
        self.assertTrue(rows[-1]["accepted"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
