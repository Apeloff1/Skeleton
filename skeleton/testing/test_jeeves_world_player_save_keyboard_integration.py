"""Both standalone world-player features must share one immutable source-bound build.

This is source-level regression only; browser/device qualification remains separate.
"""
import unittest
from skeleton.jeeves.worlds.world_canon import compile_html, propose


class WorldPlayerSaveKeyboardIntegration(unittest.TestCase):
    def test_standalone_player_has_both_features_without_choice_aliasing(self):
        world = propose(
            world_id="save-keyboard-integration",
            premise="Explore the new original world",
            protagonist="Ada",
            region="North",
            goal="Return safely",
        )
        html = compile_html(world)
        for marker in (
            "Save progress",
            "Load saved progress",
            "save_schema_or_source_mismatch",
            "save_invalid_transition",
            "Verified saved progress restored.",
            'data-choice-index',
            'button.click()',
            'document.addEventListener("keydown"',
            'button[data-choice-index=',
            'connect-src \'none\'',
        ):
            self.assertIn(marker, html)
        # The indexed selector is assigned exclusively to current scene choices.
        self.assertIn("choices.forEach((choice, index)", html)
        self.assertNotIn('save.dataset.choiceIndex', html)
        self.assertNotIn('load.dataset.choiceIndex', html)
        self.assertIn('if (button && !button.disabled)', html)


if __name__ == "__main__":
    unittest.main()
