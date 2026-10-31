"""Real canonical offline campaign acceptance and adversarial replay tests."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from skeleton.game.gameplay.flgb_gameplay_runtime import GameplayContractError
from skeleton.game.gameplay.offline_grid_campaign import Campaign, Command, Session

SOURCE = Path(__file__).resolve().parents[1] / "game/gameplay/content/lantern_harbor.json"
COMMANDS = [
    ("east", "move", "east"), ("take", "collect", "lantern"),
    ("east2", "move", "east"), ("greet", "talk", "keeper"),
    ("south", "move", "south"), ("south2", "move", "south"),
    ("east3", "move", "east"), ("east4", "move", "east"),
    ("south3", "move", "south"), ("finish", "finish", "homecoming"),
]


class OfflineGridCampaignTests(unittest.TestCase):
    def setUp(self) -> None:
        self.source = json.loads(SOURCE.read_text(encoding="utf-8"))
        self.campaign = Campaign.load(self.source)

    def play(self, commands=COMMANDS):
        state = Session.new(self.campaign)
        for identity, kind, target in commands:
            state = state.step(Command(identity, kind, target))
        return state

    def test_real_input_quest_ending_save_and_reopen(self):
        state = self.play()
        self.assertEqual(state.ending, "homecoming")
        self.assertEqual(state.quests, ("lightkeeper",))
        self.assertEqual(state.inventory, ("lantern",))
        self.assertEqual(state.tick, 10)
        self.assertEqual(Session.restore(self.campaign, state.snapshot()), state)
        self.assertEqual(state.render().count("@"), 1)
        self.assertEqual(self.play().state_digest, state.state_digest)

    def test_alternate_ending_requires_goal_but_not_quest(self):
        movements = [("east", "move", "east"), ("east2", "move", "east"),
                     ("south", "move", "south"), ("south2", "move", "south"),
                     ("east3", "move", "east"), ("east4", "move", "east"),
                     ("south3", "move", "south"), ("alt", "finish", "wanderer")]
        self.assertEqual(self.play(movements).ending, "wanderer")
        with self.assertRaises(GameplayContractError):
            self.play(movements[:-1] + [("bad", "finish", "homecoming")])

    def test_replay_and_collision_do_not_mutate_state(self):
        state = Session.new(self.campaign)
        with self.assertRaises(GameplayContractError):
            state.step(Command("wall", "move", "north"))
        self.assertEqual(state.tick, 0)
        advanced = state.step(Command("one", "move", "east"))
        with self.assertRaises(GameplayContractError):
            advanced.step(Command("one", "wait"))
        self.assertEqual(advanced.tick, 1)
        with self.assertRaises(GameplayContractError):
            advanced.step(Command("missing", "collect", "keeper"))
        self.assertEqual(Session.restore(self.campaign, advanced.snapshot()), advanced)

    def test_tamper_source_event_state_and_version(self):
        state = self.play()
        original = state.snapshot()
        changes = [
            ("source_digest", "0" * 64),
            ("state_digest", "0" * 64),
            ("schema_version", 2),
        ]
        for field, value in changes:
            payload = copy.deepcopy(original)
            payload[field] = value
            with self.subTest(field=field), self.assertRaises(GameplayContractError):
                Session.restore(self.campaign, payload)
        for field, value in (("kind", "wait"), ("tick", 999), ("digest", "0" * 64)):
            payload = copy.deepcopy(original)
            payload["events"][0][field] = value
            with self.subTest(event=field), self.assertRaises(GameplayContractError):
                Session.restore(self.campaign, payload)
        payload = copy.deepcopy(original)
        payload["events"][0]["tick"] = True
        with self.assertRaises(GameplayContractError):
            Session.restore(self.campaign, payload)
        payload = copy.deepcopy(original)
        payload["state"]["x"] = True
        with self.assertRaises(GameplayContractError):
            Session.restore(self.campaign, payload)
        payload = copy.deepcopy(original)
        payload["state"]["x"] += 1
        with self.assertRaises(GameplayContractError):
            Session.restore(self.campaign, payload)

    def test_invalid_authored_graphs_and_bounds(self):
        bad_cases = [
            lambda v: v["rows"].__setitem__(0, "##X######"),
            lambda v: v["objects"].append(dict(v["objects"][0])),
            lambda v: v["objects"][0].update(x=0, y=0),
            lambda v: v["quests"][0].update(requires_items=["unknown"]),
            lambda v: v["quests"][0].update(requires_quests=["lightkeeper"]),
            lambda v: v["endings"][0].update(requires_quests=["missing"]),
            lambda v: v.update(version=True),
            lambda v: v.update(license="unlicensed"),
            lambda v: v.update(extra="unreviewed"),
        ]
        for mutate in bad_cases:
            source = copy.deepcopy(self.source)
            mutate(source)
            with self.subTest(source=source), self.assertRaises(GameplayContractError):
                Campaign.load(source)
        with self.assertRaises(GameplayContractError):
            Campaign.load({"rows": []})

    def test_terminal_and_event_limits(self):
        state = self.play()
        with self.assertRaises(GameplayContractError):
            state.step(Command("after", "wait"))
        self.assertEqual(len(state.events), 10)
        with self.assertRaises(GameplayContractError):
            Command("bad", "move", "teleport")
        with self.assertRaises(GameplayContractError):
            Command("bad", "wait", "payload")

    def test_interactive_terminal_playthrough(self):
        inputs = "\n".join(
            (f"{kind} {target}".strip() for _, kind, target in COMMANDS)
        ) + "\n"
        process = subprocess.run(
            [sys.executable, "-m", "scripts.game.offline_grid_campaign", "play"],
            input=inputs, capture_output=True, text=True, check=False,
        )
        self.assertEqual(process.returncode, 0, process.stderr)
        result = json.loads(process.stdout.splitlines()[-1])
        self.assertEqual(result["save"]["state"]["ending"], "homecoming")
        self.assertEqual(Session.restore(self.campaign, result["save"]).tick, 10)

    def test_canonical_application_entrypoint(self):
        process = subprocess.run(
            [sys.executable, "-m", "skeleton", "campaign", "inspect"],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(process.returncode, 0, process.stderr)
        output = json.loads(process.stdout)
        self.assertEqual(output["source_digest"], self.campaign.source_digest)
        self.assertIn("@", output["map"])

    def test_cli_offline_end_to_end(self):
        with tempfile.TemporaryDirectory() as tmp:
            commands = Path(tmp) / "commands.json"
            commands.write_text(json.dumps([
                {"command_id": identity, "kind": kind, "target": target}
                for identity, kind, target in COMMANDS
            ]), encoding="utf-8")
            process = subprocess.run(
                [sys.executable, "-m", "scripts.game.offline_grid_campaign",
                 "run", "--commands", str(commands)],
                capture_output=True, text=True, check=False,
            )
            self.assertEqual(process.returncode, 0, process.stderr)
            result = json.loads(process.stdout)
            self.assertEqual(result["save"]["state"]["ending"], "homecoming")
            self.assertEqual(Session.restore(self.campaign, result["save"]).ending, "homecoming")
            save = Path(tmp) / "save.json"
            save.write_text(json.dumps(result["save"]), encoding="utf-8")
            empty = Path(tmp) / "empty.json"
            empty.write_text("[]", encoding="utf-8")
            resumed = subprocess.run(
                [sys.executable, "-m", "scripts.game.offline_grid_campaign",
                 "run", "--commands", str(empty), "--resume", str(save)],
                capture_output=True, text=True, check=False,
            )
            self.assertEqual(resumed.returncode, 0, resumed.stderr)
            self.assertEqual(json.loads(resumed.stdout)["save"], result["save"])


if __name__ == "__main__":
    unittest.main()
