"""Standalone original-world browser save contract regression.

This is source-level acceptance, not a browser/device playtest.
"""
import unittest
from skeleton.jeeves.worlds.world_canon import compile_html, propose, digest


class BrowserSaveContractTests(unittest.TestCase):
    def setUp(self):
        self.world = propose(world_id="original", premise="An original journey",
                             protagonist="Ada", region="North", goal="Find the beacon")

    def test_standalone_player_has_save_and_restore_controls(self):
        html = compile_html(self.world)
        self.assertIn("Save progress", html)
        self.assertIn("Load saved progress", html)
        self.assertIn("save_invalid_transition", html)
        self.assertIn("save_schema_or_source_mismatch", html)
        self.assertIn(digest(self.world), html)
        self.assertIn("script-src 'sha256-", html)
        self.assertIn("connect-src 'none'", html)

    def test_save_replay_binds_to_exact_world_source(self):
        first = compile_html(self.world)
        changed = dict(self.world)
        changed["prompt"] = "A revised original journey"
        second = compile_html(changed)
        self.assertNotEqual(digest(self.world), digest(changed))
        self.assertNotEqual(first, second)
        self.assertIn(digest(changed), second)


if __name__ == "__main__":
    unittest.main()
