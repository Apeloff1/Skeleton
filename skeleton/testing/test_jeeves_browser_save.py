"""Source-bound browser-save regression for independently runnable Jeeves HTML."""
from __future__ import annotations

import hashlib
import re
import unittest

from skeleton.jeeves.worlds.world_canon import compile_html, propose


class BrowserSaveContractTests(unittest.TestCase):
    def setUp(self):
        self.world = propose(
            world_id="browser-save",
            premise="A courier seeks the last lighthouse.",
            protagonist="Ira",
            region="Salt Coast",
            goal="Light the beacon",
        )
        self.html = compile_html(self.world)

    def test_save_controls_are_in_exported_offline_player(self):
        for text in ("Save progress", "Restore saved progress",
                     "Delete saved progress", "localStorage.setItem",
                     "localStorage.getItem", "localStorage.removeItem"):
            self.assertIn(text, self.html)
        self.assertIn("connect-src 'none'", self.html)
        self.assertIn("default-src 'none'", self.html)

    def test_replay_validates_source_and_each_choice(self):
        for text in ("source_digest !== sourceDigest",
                     "invalid_save_transition", "save_after_ending",
                     "choice.from !== scene", "choice.requires.every",
                     "MAX_SAVE_BYTES", "steps.length > 4096"):
            self.assertIn(text, self.html)

    def test_script_csp_matches_embedded_player(self):
        import base64
        match = re.search(r"<script>(.*?)</script>", self.html, re.S)
        self.assertIsNotNone(match)
        digest = base64.b64encode(hashlib.sha256(
            match.group(1).encode("utf-8")).digest()).decode("ascii")
        self.assertIn("script-src 'sha256-" + digest + "'", self.html)

    def test_different_world_revision_changes_save_namespace(self):
        other = propose(
            world_id="browser-save",
            premise="A courier seeks the last lighthouse.",
            protagonist="Ira",
            region="Salt Coast",
            goal="A different resolution",
        )
        from skeleton.jeeves.worlds.world_canon import digest
        self.assertNotEqual(digest(self.world), digest(other))
        self.assertIn(digest(self.world), self.html)
        self.assertIn(digest(other), compile_html(other))


if __name__ == "__main__":
    unittest.main()
