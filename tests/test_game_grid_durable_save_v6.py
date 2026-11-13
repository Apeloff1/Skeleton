"""Durable CLI save/restart and no-clobber regression for original grid campaign."""
from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from scripts.game.offline_grid_campaign import main, DEFAULT_SOURCE


class DurableGridSaveTests(unittest.TestCase):
    def invoke(self, *args: str) -> tuple[int, str]:
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            code = main(list(args))
        return code, out.getvalue()

    def test_save_resume_and_no_clobber(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            commands = root / "commands.json"
            save = root / "slot.json"
            commands.write_text(json.dumps([{"command_id": "first", "kind": "wait", "target": ""}]))
            code, output = self.invoke("run", "--source", str(DEFAULT_SOURCE),
                                       "--commands", str(commands), "--out-save", str(save))
            self.assertEqual(code, 0)
            snapshot = json.loads(save.read_text())
            self.assertEqual(snapshot, json.loads(output)["save"])
            self.assertEqual(snapshot["state"]["tick"], 1)
            code, _ = self.invoke("run", "--source", str(DEFAULT_SOURCE),
                                  "--commands", str(commands), "--out-save", str(save))
            self.assertEqual(code, 2)
            self.assertEqual(json.loads(save.read_text()), snapshot)
            commands.write_text(json.dumps([{"command_id": "second", "kind": "wait", "target": ""}]))
            next_save = root / "slot-2.json"
            code, output = self.invoke("run", "--source", str(DEFAULT_SOURCE),
                                       "--commands", str(commands), "--resume", str(save),
                                       "--out-save", str(next_save))
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(output)["save"]["state"]["tick"], 2)
            self.assertEqual(json.loads(next_save.read_text())["state"]["tick"], 2)

    def test_corruption_and_invalid_destination_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            commands = root / "commands.json"
            commands.write_text("[]")
            corrupted = root / "corrupted.json"
            corrupted.write_text('{"schema_version":1}')
            code, _ = self.invoke("run", "--source", str(DEFAULT_SOURCE),
                                  "--commands", str(commands), "--resume", str(corrupted))
            self.assertEqual(code, 2)
            directory_target = root / "folder"
            directory_target.mkdir()
            code, _ = self.invoke("run", "--source", str(DEFAULT_SOURCE),
                                  "--commands", str(commands), "--out-save", str(directory_target))
            self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
