"""Source-level regression for numbered controls in the standalone Jeeves player.

This does not substitute for an actual Chromium/Windows playtest.
"""
import unittest
from skeleton.jeeves.worlds.world_canon import compile_html, propose


class StandaloneKeyboardControls(unittest.TestCase):
    def test_numbered_choices_are_in_compiled_player(self):
        world = propose(world_id="keyboard-choices", premise="Explore a new place",
                        protagonist="Ada", region="Valley", goal="Reach the end")
        html = compile_html(world)
        self.assertIn('data-choice-index', html)
        self.assertIn('event.repeat', html)
        self.assertIn('button.click()', html)
        self.assertIn('event.preventDefault()', html)
        self.assertIn('event.target?.isContentEditable', html)
        self.assertIn('["INPUT", "TEXTAREA", "SELECT"]', html)
        self.assertIn('event.altKey || event.ctrlKey || event.metaKey', html)
        self.assertIn('document.addEventListener("keydown"', html)


if __name__ == "__main__":
    unittest.main()
