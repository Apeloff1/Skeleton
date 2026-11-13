"""Authoring transaction, replay and portable preview acceptance."""
import copy
import io
import json
import unittest
from contextlib import redirect_stderr, redirect_stdout

from skeleton.__main__ import main
from skeleton.game.gameplay.turn_combat import CombatSessionError
from skeleton.game.gameplay.combat_league import original_league
from skeleton.game.gameplay.combat_league_author import (
    edit_author, export_author, import_author, new_author, preview_author,
    verify_author,
)


def edit(saved, kind, **kwargs):
    return edit_author(saved, {
        "kind": kind, **kwargs, "expected_source_digest": saved["source_digest"],
    })


class CombatLeagueAuthorTests(unittest.TestCase):
    def setUp(self):
        self.author = new_author(original_league())

    def test_author_stats_rounds_and_playable_preview(self):
        saved = edit(self.author, "set_stat", entrant_id="amber_guard",
                     field="attack", value=8)
        saved = edit(saved, "set_rounds", value=2)
        saved = edit(saved, "set_turn_limit", value=24)
        saved = edit(saved, "rename_entrant", entrant_id="fog_warden",
                     new_id="fog_navigator")
        self.assertEqual(verify_author(saved), saved)
        self.assertEqual(saved["source"]["rounds"], 2)
        self.assertEqual(len(saved["journal"]), 4)
        preview = preview_author(saved)
        self.assertEqual(preview["league"]["state"]["next_round"], 2)
        self.assertEqual(preview["standings"]["rounds_played"], 2)
        self.assertEqual(preview["source_digest"], saved["source_digest"])
        self.assertEqual(import_author(export_author(saved)), saved)

    def test_stale_edit_and_unknown_entrant_do_not_mutate(self):
        before = copy.deepcopy(self.author)
        with self.assertRaisesRegex(CombatSessionError, "stale"):
            edit_author(self.author, {
                "kind": "set_rounds", "value": 2,
                "expected_source_digest": "0" * 64,
            })
        with self.assertRaisesRegex(CombatSessionError, "unknown"):
            edit(self.author, "set_stat", entrant_id="absent",
                 field="speed", value=3)
        self.assertEqual(self.author, before)

    def test_replay_rejects_forged_journal_and_receipt(self):
        saved = edit(self.author, "set_stat", entrant_id="amber_guard",
                     field="attack", value=8)
        changed = copy.deepcopy(saved)
        changed["journal"][0]["edit"]["value"] = 100
        with self.assertRaises(CombatSessionError):
            verify_author(changed)
        changed = copy.deepcopy(saved)
        changed["source"]["entrants"][0]["attack"] = 100
        with self.assertRaises(CombatSessionError):
            verify_author(changed)
        changed = copy.deepcopy(saved)
        changed["receipt"] = "0" * 64
        with self.assertRaises(CombatSessionError):
            verify_author(changed)

    def test_duplicate_rename_invalid_stat_and_budget(self):
        with self.assertRaises(CombatSessionError):
            edit(self.author, "rename_entrant", entrant_id="amber_guard",
                 new_id="beacon_mender")
        with self.assertRaises(CombatSessionError):
            edit(self.author, "set_stat", entrant_id="amber_guard",
                 field="attack", value=True)
        with self.assertRaises(CombatSessionError):
            edit(self.author, "set_stat", entrant_id="amber_guard",
                 field="team", value=2)
        with self.assertRaises(CombatSessionError):
            edit(self.author, "set_rounds", value=5)

    def test_portable_checksum_rejects_corruption(self):
        bundle = export_author(self.author)
        bundle["checksum"] = "0" * 64
        with self.assertRaises(CombatSessionError):
            import_author(bundle)

    def test_canonical_cli_demo_and_bad_edit(self):
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(main(["combat-league-author", "demo"]), 0)
        self.assertEqual(verify_author(json.loads(output.getvalue())),
                         json.loads(output.getvalue()))
        error = io.StringIO()
        with redirect_stderr(error):
            code = main(["combat-league-author", "new",
                         "--source-json", '{"invalid":true}'])
        self.assertEqual(code, 2)
        self.assertIn('"ok": false', error.getvalue())


if __name__ == "__main__":
    unittest.main()
