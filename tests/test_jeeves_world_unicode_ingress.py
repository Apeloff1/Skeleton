"""Unicode scalar boundary regression for the canonical Jeeves world compiler."""
import unittest

from skeleton.jeeves.worlds.world_canon import CanonError, compile_html, edit, propose, prove


class WorldUnicodeIngressTests(unittest.TestCase):
    def setUp(self):
        self.world = propose(world_id="unicode-world", premise="A new beginning",
                             protagonist="Mira", region="The Vale", goal="Find the beacon")

    def test_normal_world_remains_playable(self):
        self.assertIn("Ending:", compile_html(self.world))
        self.assertEqual(len(prove(self.world).ending_witnesses), 1)

    def test_surrogate_in_prompt_rejected_before_publication(self):
        self.world["prompt"] = "broken" + chr(0xD800)
        with self.assertRaises(CanonError) as caught:
            prove(self.world)
        self.assertEqual(caught.exception.code, "invalid_unicode_scalar")

    def test_surrogate_in_atomic_scene_edit_rejected(self):
        operation = {"action": "replace_scene", "value": {
            "id": "opening", "title": "Broken" + chr(0xDFFF), "narrative": "A new beginning"}}
        with self.assertRaises(CanonError) as caught:
            edit(self.world, operation)
        self.assertEqual(caught.exception.code, "invalid_unicode_scalar")
        self.assertEqual(self.world["scenes"][0]["title"], "Mira in The Vale")

    def test_valid_supplementary_plane_unicode_is_accepted(self):
        # Reject invalid scalar code points without banning valid non-BMP text.
        self.world["prompt"] = "Explore " + chr(0x1F680)
        self.assertEqual(len(prove(self.world).ending_witnesses), 1)

    def test_lone_low_surrogate_in_choice_label_is_rejected(self):
        self.world["choices"][0]["label"] = "Choose " + chr(0xDC00)
        with self.assertRaises(CanonError) as caught:
            compile_html(self.world)
        self.assertEqual(caught.exception.code, "invalid_unicode_scalar")

    def test_surrogate_pair_codepoints_are_not_valid_utf8_scalars(self):
        self.world["region"] = "region" + chr(0xD83D) + chr(0xDE80)
        with self.assertRaises(CanonError) as caught:
            prove(self.world)
        self.assertEqual(caught.exception.code, "invalid_unicode_scalar")


if __name__ == "__main__":
    unittest.main()
