"""Canonical input binding, remapping, replay and CLI acceptance."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from skeleton.game.presentation.flgb_presentation_runtime import PresentationContractError
from skeleton.game.presentation.input_router import InputEvent, InputProfile, InputSession

PROFILE = Path(__file__).resolve().parents[1] / "game/presentation/fixtures/original_campaign_controls.json"


def event(identifier, sequence, control="KeyD", pressed=True, device="keyboard"):
    return {
        "event_id": identifier, "sequence": sequence, "device_class": device,
        "control_path": control, "modifiers": [], "pressed": pressed,
    }


class InputRoutingTests(unittest.TestCase):
    def setUp(self):
        self.raw = json.loads(PROFILE.read_text(encoding="utf-8"))
        self.profile = InputProfile.load(self.raw)

    def test_real_device_events_map_to_semantic_commands(self):
        session = InputSession(self.profile)
        first = session.step(InputEvent.load(event("press", 0)))
        self.assertEqual(first.events[0]["command"], {"kind": "move", "target": "east"})
        released = first.step(InputEvent.load(event("release", 1, pressed=False)))
        self.assertIsNone(released.events[-1]["command"])
        controller = released.step(InputEvent.load(event("pad", 2, "DPadRight", device="controller")))
        self.assertEqual(controller.events[-1]["action_id"], "move-east")
        self.assertEqual(InputSession.restore(self.profile, controller.snapshot()), controller)
        self.assertEqual(controller.snapshot(), InputSession.restore(self.profile, controller.snapshot()).snapshot())

    def test_receipts_cannot_mutate_authoritative_session(self):
        session = InputSession(self.profile).step(InputEvent.load(event("one", 0)))
        before = session.snapshot()
        leaked = session.events[0]
        leaked["command"]["target"] = "west"
        leaked["event"]["event_id"] = "forged"
        self.assertEqual(session.snapshot(), before)
        self.assertEqual(InputSession.restore(self.profile, before), session)

    def test_rebinding_is_revision_fenced_and_session_source_bound(self):
        revised = self.profile.rebind("keyboard-east", "ArrowRight", 0)
        self.assertEqual(revised.revision, 1)
        self.assertNotEqual(revised.digest, self.profile.digest)
        self.assertEqual(InputSession(revised).step(InputEvent.load(event("new", 0, "ArrowRight")))
                         .events[0]["command"]["target"], "east")
        with self.assertRaises(PresentationContractError):
            self.profile.rebind("keyboard-east", "ArrowRight", 1)
        with self.assertRaises(PresentationContractError):
            revised.rebind("keyboard-east", "KeyA", 1)
        snapshot = InputSession(self.profile).step(InputEvent.load(event("old", 0))).snapshot()
        with self.assertRaises(PresentationContractError):
            InputSession.restore(revised, snapshot)

    def test_unknown_chord_duplicate_event_and_sequence_rejected(self):
        session = InputSession(self.profile)
        with self.assertRaises(PresentationContractError):
            session.step(InputEvent.load(event("gap", 2)))
        with self.assertRaises(PresentationContractError):
            session.step(InputEvent.load(event("unknown", 0, "KeyZ")))
        advanced = session.step(InputEvent.load(event("one", 0)))
        with self.assertRaises(PresentationContractError):
            advanced.step(InputEvent.load(event("one", 1)))
        with self.assertRaises(PresentationContractError):
            InputEvent.load(event("bad", True))
        self.assertEqual(len(advanced.events), 1)

    def test_invalid_profile_and_tampered_replay(self):
        invalid = [
            lambda p: p["bindings"].append(dict(p["bindings"][0])),
            lambda p: p["bindings"][0].update(control_path="KeyA"),
            lambda p: p["bindings"][0].update(action_id="execute-shell"),
            lambda p: p.update(version=True),
            lambda p: p.update(revision=-1),
        ]
        for mutate in invalid:
            raw = copy.deepcopy(self.raw)
            mutate(raw)
            with self.subTest(raw=raw), self.assertRaises(PresentationContractError):
                InputProfile.load(raw)
        session = InputSession(self.profile).step(InputEvent.load(event("one", 0)))
        for field, value in (("digest", "0" * 64), ("action_id", "move-west")):
            raw = copy.deepcopy(session.snapshot())
            raw["events"][0][field] = value
            with self.subTest(field=field), self.assertRaises(PresentationContractError):
                InputSession.restore(self.profile, raw)

    def test_cli_route_and_rebind(self):
        with tempfile.TemporaryDirectory() as tmp:
            events = Path(tmp) / "events.json"
            events.write_text(json.dumps([event("one", 0)]), encoding="utf-8")
            routed = subprocess.run(
                [sys.executable, "-m", "scripts.game.route_inputs", "--profile",
                 str(PROFILE), "--events", str(events)],
                capture_output=True, text=True, check=False,
            )
            self.assertEqual(routed.returncode, 0, routed.stderr)
            self.assertEqual(json.loads(routed.stdout)["events"][0]["command"]["target"], "east")
            rebound = subprocess.run(
                [sys.executable, "-m", "scripts.game.route_inputs", "--profile",
                 str(PROFILE), "--rebind", "keyboard-east", "--control", "ArrowRight",
                 "--revision", "0"],
                capture_output=True, text=True, check=False,
            )
            self.assertEqual(rebound.returncode, 0, rebound.stderr)
            self.assertEqual(json.loads(rebound.stdout)["profile"]["revision"], 1)


if __name__ == "__main__":
    unittest.main()
