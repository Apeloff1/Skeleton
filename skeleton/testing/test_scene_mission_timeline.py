"""Source-to-runtime-to-save-to-export tests for mission timeline branches."""
import copy
import io
import json
import unittest
from contextlib import redirect_stderr, redirect_stdout

from skeleton.__main__ import main
from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.scene_travel import SceneTravelError
from skeleton.game.gameplay.scene_mission import demo_actions, original_mission
from skeleton.game.gameplay.scene_mission_timeline import (
    MAX_BRANCHES, _json, _seal, append_actions, branch_session,
    checkout_branch, compare_branches, demo_timeline, export_timeline,
    fork_branch, import_timeline, inspect_timeline, new_timeline, verify_timeline,
)


def advance(record, branch, actions):
    return append_actions(record, branch, actions,
        expected_revision=record["revision"], expected_digest=record["digest"])


def fork(record, parent, name, tick):
    return fork_branch(record, parent, name, tick,
        expected_revision=record["revision"], expected_digest=record["digest"])


class MissionTimelineTests(unittest.TestCase):
    def setUp(self):
        self.timeline = new_timeline(original_mission())

    def test_demo_canonical_play_and_checkpoint(self):
        record = demo_timeline()
        self.assertEqual(verify_timeline(record), record)
        self.assertEqual(branch_session(record, "main")["state"]["ending"],
                         "lantern_restored")
        self.assertEqual(branch_session(record, "alternate")["state"]["phase"],
                         "active")
        result = compare_branches(record, "main", "alternate")
        self.assertEqual(result["common_turns"], 1)
        self.assertFalse(result["same_head"])
        self.assertEqual(result["right_ending"], None)

    def test_branch_independence_and_portable_replay(self):
        full = advance(self.timeline, "main", demo_actions())
        record = fork(full, "main", "short", 1)
        record = advance(record, "short", [
            {"kind": "scene", "action": {"kind": "collect", "pickup_id": "find_key"}},
        ])
        self.assertEqual(branch_session(record, "main")["state_digest"],
                         branch_session(full, "main")["state_digest"])
        self.assertEqual(len(branch_session(record, "short")["journal"]), 2)
        self.assertEqual(import_timeline(export_timeline(record)), record)
        self.assertEqual(inspect_timeline(record)["active_branch"], "short")

    def test_stale_revision_and_digest_rejected(self):
        with self.assertRaisesRegex(SceneTravelError, "stale timeline revision"):
            append_actions(self.timeline, "main", demo_actions(),
                expected_revision=1, expected_digest=self.timeline["digest"])
        with self.assertRaisesRegex(SceneTravelError, "stale timeline digest"):
            append_actions(self.timeline, "main", demo_actions(),
                expected_revision=0, expected_digest="0" * 64)
        with self.assertRaisesRegex(SceneTravelError, "stale timeline revision"):
            fork_branch(self.timeline, "main", "other", 0,
                expected_revision=True, expected_digest=self.timeline["digest"])

    def test_failed_batch_never_mutates_original(self):
        before = copy.deepcopy(self.timeline)
        with self.assertRaises(SceneTravelError):
            advance(self.timeline, "main", [
                {"kind": "choose", "choice_id": "restore_lantern", "option_id": "help"},
                {"kind": "scene", "action": {"kind": "travel", "exit_id": "inside"}},
            ])
        self.assertEqual(self.timeline, before)

    def test_recomputed_hash_cannot_bypass_replay_proof(self):
        record = demo_timeline()
        mutations = []
        bad = copy.deepcopy(record)
        bad["branches"][0]["actions"][0]["option_id"] = "decline"
        mutations.append(bad)
        bad = copy.deepcopy(record)
        bad["branches"][1]["fork_state_digest"] = "0" * 64
        mutations.append(bad)
        bad = copy.deepcopy(record)
        bad["branches"][1]["parent"] = "unknown"
        mutations.append(bad)
        bad = copy.deepcopy(record)
        bad["branches"][1]["actions"][0]["option_id"] = "decline"
        mutations.append(bad)
        for item in mutations:
            with self.subTest(item=item["branches"][-1]):
                with self.assertRaises(SceneTravelError):
                    verify_timeline(_seal(item))

    def test_limits_and_unknown_references(self):
        with self.assertRaises(SceneTravelError):
            fork(self.timeline, "unknown", "other", 0)
        with self.assertRaises(SceneTravelError):
            fork(self.timeline, "main", "main", 0)
        with self.assertRaises(SceneTravelError):
            fork(self.timeline, "main", "other", 1)
        with self.assertRaises(SceneTravelError):
            branch_session(self.timeline, "unknown")
        record = self.timeline
        for index in range(MAX_BRANCHES - 1):
            record = fork(record, "main", f"fork_{index}", 0)
        with self.assertRaisesRegex(SceneTravelError, "branch budget"):
            fork(record, "main", "extra", 0)
        record = checkout_branch(record, "main",
            expected_revision=record["revision"], expected_digest=record["digest"])
        self.assertEqual(record["active_branch"], "main")

    def test_bundle_tampering_and_hostile_json(self):
        bundle = export_timeline(demo_timeline())
        bundle["timeline"]["branches"][0]["head_state_digest"] = "0" * 64
        bundle["timeline"] = _seal(bundle["timeline"])
        bundle["timeline_digest"] = bundle["timeline"]["digest"]
        bundle["checksum"] = dig({k: v for k, v in bundle.items()
                                   if k != "checksum"})
        with self.assertRaises(SceneTravelError):
            import_timeline(bundle)
        for raw in ('{"a":1,"a":2}', '{"x":NaN}', '{"x":Infinity}'):
            with self.assertRaises(SceneTravelError):
                _json(raw, "hostile")
        with self.assertRaises(SceneTravelError):
            _json("a" * (2 * 1024 * 1024 + 1), "hostile")

    def test_canonical_cli_is_reachable_and_fails_closed(self):
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(main(["scene-mission-timeline", "demo"]), 0)
        self.assertEqual(verify_timeline(json.loads(out.getvalue())),
                         json.loads(out.getvalue()))
        err = io.StringIO()
        with redirect_stderr(err):
            code = main(["scene-mission-timeline", "verify",
                         "--timeline-json", '{"a":1,"a":2}'])
        self.assertEqual(code, 2)
        self.assertIn("invalid timeline JSON", err.getvalue())


if __name__ == "__main__":
    unittest.main()
