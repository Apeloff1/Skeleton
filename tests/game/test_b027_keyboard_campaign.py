"""CLI keyboard movement regression for the canonical original campaign."""
from __future__ import annotations

import contextlib
import io
import unittest
from unittest.mock import patch

from scripts.game.offline_grid_campaign import main


class KeyboardCampaignTests(unittest.TestCase):
    def _play(self, commands):
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch("builtins.input", side_effect=commands), contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            status = main(["play", "--accessible"])
        return status, stdout.getvalue(), stderr.getvalue()

    def test_wasd_moves_through_canonical_session(self):
        status, output, errors = self._play(["d", "quit"])
        self.assertEqual(status, 0, errors)
        self.assertIn('"save":', output)
        self.assertNotIn("Movement shortcuts do not accept targets", errors)

    def test_shortcut_target_rejected_without_step(self):
        status, output, errors = self._play(["w unintended", "quit"])
        self.assertEqual(status, 0, errors)
        self.assertIn("Movement shortcuts do not accept targets", errors)
        self.assertIn('"save":', output)

    def test_uppercase_shortcut(self):
        status, output, errors = self._play(["W", "quit"])
        self.assertEqual(status, 0, errors)
        self.assertIn('"save":', output)


if __name__ == "__main__":
    unittest.main()
