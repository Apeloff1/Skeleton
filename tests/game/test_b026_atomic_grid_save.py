"""Regression coverage for durable, no-clobber original grid save slots."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.game.offline_grid_campaign import _write_new_save as _write_save


class AtomicGridSaveTests(unittest.TestCase):
    def test_round_trip_and_no_clobber(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "slot.json"
            snapshot = {"schema_version": 1, "events": [], "source_digest": "abc"}
            _write_save(path, snapshot)
            self.assertEqual(json.loads(path.read_text("utf-8")), snapshot)
            with self.assertRaises(FileExistsError):
                _write_save(path, {"events": ["overwrite"]})
            self.assertEqual(json.loads(path.read_text("utf-8")), snapshot)
            self.assertEqual(sorted(p.name for p in Path(root).iterdir()), ["slot.json"])

    def test_invalid_payload_does_not_publish(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "slot.json"
            with self.assertRaises(ValueError):
                _write_save(path, {"value": float("nan")})
            self.assertFalse(path.exists())

    def test_publication_failure_cleans_temp(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "slot.json"
            with patch("scripts.game.offline_grid_campaign.os.link", side_effect=OSError("disk full")):
                with self.assertRaises(OSError):
                    _write_save(path, {"events": []})
            self.assertEqual(list(Path(root).iterdir()), [])


if __name__ == "__main__":
    unittest.main()
