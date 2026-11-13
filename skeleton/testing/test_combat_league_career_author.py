"""Career source editing, optimistic lease, replay and preview acceptance."""
import copy
import io
import json
import unittest
from contextlib import redirect_stdout, redirect_stderr

from skeleton.__main__ import main
from skeleton.game.gameplay.turn_combat import CombatSessionError
from skeleton.game.gameplay.combat_league_career import original_career, verify_career
from skeleton.game.gameplay.combat_league_career_author import (
    edit_author, export_author, import_author, new_author,
    preview_author, verify_author,
)


class CareerAuthorTests(unittest.TestCase):
    def setUp(self):
        self.author = new_author(original_career())

    def edit(self, record, **fields):
        return edit_author(record, {**fields, "expected_source_digest": record["source_digest"]})

    def test_career_stat_edit_replays_and_previews(self):
        revised = self.edit(self.author, kind="set_entrant_stat",
                            entrant_id="amber_guard", field="attack", value=6)
        self.assertEqual(revised["source"]["league"]["entrants"][0]["attack"], 6)
        self.assertEqual(verify_author(revised), revised)
        preview = preview_author(revised, [{"kind": "rest"}])
        self.assertEqual(verify_career(preview["session"]), preview["session"])
        self.assertEqual(preview["board"]["seasons_played"], 1)
        self.assertEqual(self.author["source"]["league"]["entrants"][0]["attack"], 5)

    def test_training_budget_and_seasons_are_coupled(self):
        with self.assertRaises(CombatSessionError):
            self.edit(self.author, kind="set_seasons", value=1)
        revised = self.edit(self.author, kind="set_training_tokens", value=1)
        final = self.edit(revised, kind="set_seasons", value=1)
        self.assertEqual(final["source"]["seasons"], 1)
        self.assertEqual(final["source"]["training_tokens"], 1)

    def test_stale_edit_and_invalid_stat_fail_closed(self):
        edit = {"kind": "rename_career", "career_id": "new_career",
                "expected_source_digest": self.author["source_digest"]}
        revised = edit_author(self.author, edit)
        with self.assertRaisesRegex(CombatSessionError, "stale"):
            edit_author(revised, edit)
        with self.assertRaises(CombatSessionError):
            self.edit(self.author, kind="set_entrant_stat",
                      entrant_id="missing", field="attack", value=6)
        with self.assertRaises(CombatSessionError):
            self.edit(self.author, kind="set_entrant_stat",
                      entrant_id="amber_guard", field="magic", value=6)

    def test_journal_and_bundle_cannot_be_forged(self):
        revised = self.edit(self.author, kind="set_league_rounds", value=2)
        forged = copy.deepcopy(revised)
        forged["journal"][0]["after"] = "0" * 64
        with self.assertRaises(CombatSessionError):
            verify_author(forged)
        self.assertEqual(import_author(export_author(revised)), revised)
        bundle = export_author(revised)
        bundle["checksum"] = "0" * 64
        with self.assertRaises(CombatSessionError):
            import_author(bundle)

    def test_preview_illegal_training_rejected(self):
        with self.assertRaises(CombatSessionError):
            preview_author(self.author, [
                {"kind": "train", "entrant_id": "missing", "stat": "attack"},
            ])
        self.assertEqual(verify_author(self.author), self.author)

    def test_cli_demo_and_rejected_edit(self):
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(main(["combat-career-author", "demo"]), 0)
        author = json.loads(output.getvalue())
        self.assertEqual(verify_author(author), author)
        error = io.StringIO()
        with redirect_stderr(error):
            self.assertEqual(main(["combat-career-author", "edit", "--author-json",
                                   json.dumps(author), "--edit-json", '{"kind":"bad"}']), 2)
        self.assertIn('"ok": false', error.getvalue())


if __name__ == "__main__":
    unittest.main()
