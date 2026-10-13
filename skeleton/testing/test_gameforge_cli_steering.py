"""Regression contracts for the durable creator CLI and Godot playtest path."""
from __future__ import annotations

import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from skeleton.__main__ import main
from skeleton.context.operator_state import read_steering


def _successful_run(**overrides):
    result = {
        "succeeded": True, "era": "cozy_wholesome", "mass": 1.0,
        "forge": {"file_count": 4}, "sim": {"passed": True},
        "project": None, "playtest": {"status": "passed"},
        "run": {"stages": []},
    }
    result.update(overrides)
    return result


class CreatorCliSteeringTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.state_file = Path(self.temp.name) / "operator" / "cockpit.json"
        env = patch.dict(os.environ, {"SKELETON_COCKPIT_STATE": str(self.state_file)})
        env.start()
        self.addCleanup(env.stop)

    def _cli(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main(list(args))
        return code, out.getvalue(), err.getvalue()

    def test_bind_era_and_archetype_survive_new_calls(self):
        self.assertEqual(self._cli("cockpit", "BIND", "ERA", "cozy_wholesome")[0], 0)
        self.assertEqual(self._cli("cockpit", "BIND", "ARCHETYPE", "auto")[0], 0)
        with patch("skeleton.context.pipeline.GameForgeRun.live") as live:
            live.return_value.execute.return_value = _successful_run()
            code, out, err = self._cli("run", "a", "peaceful", "village")
        self.assertEqual(code, 0, err)
        self.assertEqual(live.return_value.execute.call_args.kwargs["era"], "cozy_wholesome")
        self.assertEqual(live.call_args.kwargs["cockpit"].archetype, "auto")
        self.assertIn("playtest=passed", out)

    def test_answers_json_playtest_and_repair_options_are_threaded(self):
        answers = Path(self.temp.name) / "answers.json"
        answers.write_text(json.dumps({"genre": "rpg", "theme": "fantasy"}), encoding="utf-8")
        with patch("skeleton.context.pipeline.GameForgeRun.live") as live:
            live.return_value.execute.return_value = _successful_run()
            code, _, err = self._cli(
                "run", "epic", "--answers", str(answers),
                "--playtest", "require", "--repair-mode", "suggest", "--out",
                str(Path(self.temp.name) / "game"),
            )
        self.assertEqual(code, 0, err)
        call = live.return_value.execute.call_args.kwargs
        self.assertEqual(call["answers"], {"genre": "rpg", "theme": "fantasy"})
        self.assertEqual(call["playtest"], "require")
        self.assertEqual(call["repair_mode"], "suggest")
        self.assertTrue(call["project_root"].endswith("game"))

    def test_invalid_answers_fail_before_forge(self):
        answers = Path(self.temp.name) / "answers.json"
        answers.write_text('["not-an-object"]', encoding="utf-8")
        with patch("skeleton.context.pipeline.GameForgeRun.live") as live:
            code, _, err = self._cli("run", "adventure", "--answers", str(answers))
        self.assertEqual(code, 2)
        self.assertIn("object mapping strings to strings", err)
        live.assert_not_called()

    def test_snapshot_restore_roundtrip_pins(self):
        self.assertEqual(self._cli("cockpit", "BIND", "ERA", "cozy_wholesome")[0], 0)
        self.assertEqual(self._cli("cockpit", "BIND", "ARCHETYPE", "auto")[0], 0)
        snapshot = Path(self.temp.name) / "saved.json"
        code, _, err = self._cli("cockpit", "SNAPSHOT", "--out", str(snapshot))
        self.assertEqual(code, 0, err)
        self.assertEqual(self._cli("cockpit", "BIND", "ERA", "soulslike")[0], 0)
        self.assertEqual(self._cli("cockpit", "RESTORE", str(snapshot))[0], 0)
        state = read_steering()
        self.assertEqual(state["tensor"]["era"], "cozy_wholesome")
        self.assertEqual(state["archetype"], "auto")
        self.assertTrue(state["era_bound"])

    def test_explicit_era_overrides_saved_pin(self):
        self.assertEqual(self._cli("cockpit", "BIND", "ERA", "soulslike")[0], 0)
        with patch("skeleton.context.pipeline.GameForgeRun.live") as live:
            live.return_value.execute.return_value = _successful_run()
            code, _, _ = self._cli("run", "a", "village", "--era", "cozy_wholesome")
        self.assertEqual(code, 0)
        self.assertEqual(live.return_value.execute.call_args.kwargs["era"], "cozy_wholesome")

    def test_required_playtest_failure_names_emit_stage(self):
        failure = _successful_run(
            succeeded=False, playtest=None,
            run={"stages": [{"name": "emit", "status": "FAILED",
                             "error": "RuntimeError: playtest unavailable: missing Godot"}]},
        )
        with patch("skeleton.context.pipeline.GameForgeRun.live") as live:
            live.return_value.execute.return_value = failure
            code, out, err = self._cli("run", "village", "--playtest", "require")
        self.assertEqual(code, 1)
        self.assertIn("playtest=not-reached", out)
        self.assertIn("stage=emit", err)
        self.assertIn("missing Godot", err)

    def test_invalid_state_is_not_silently_discarded(self):
        self.state_file.parent.mkdir(parents=True)
        self.state_file.write_text('{"schema":"unknown"}', encoding="utf-8")
        with patch("skeleton.context.pipeline.GameForgeRun.live") as live:
            code, _, err = self._cli("run", "village")
        self.assertEqual(code, 2)
        self.assertIn("steering schema", err)
        live.assert_not_called()

    def test_blend_saved_only_when_not_overridden_by_era(self):
        self.assertEqual(
            self._cli("cockpit", "BLEND", "ERA", "soulslike", "cozy_wholesome", "0.25")[0], 0
        )
        with patch("skeleton.context.pipeline.GameForgeRun.live") as live:
            live.return_value.execute.return_value = _successful_run()
            code, _, _ = self._cli("run", "village", "--era", "cozy_wholesome")
        self.assertEqual(code, 0)
        call = live.return_value.execute.call_args.kwargs
        self.assertIsNone(call["blend"])
        self.assertEqual(call["era"], "cozy_wholesome")


if __name__ == "__main__":
    unittest.main()
