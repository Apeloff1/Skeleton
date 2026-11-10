"""Deterministic positive, negative and restore coverage for grid input bridge."""
import unittest

from skeleton.game.gameplay.flgb_gameplay_runtime import GameplayContractError
from skeleton.game.gameplay.offline_grid_campaign import Campaign, Session
from skeleton.game.gameplay.grid_input_adapter import InputEvent, apply_input, translate


def campaign():
    return Campaign.load({
        "version": 1, "game_id": "input-test", "title": "Original Input",
        "license": "CC0-1.0", "author": "studio-b",
        "rows": ["#####", "#S.G#", "#####"],
        "objects": [], "quests": [],
        "endings": [{"id": "victory", "requires_quests": [], "outcome": "victory"}],
    })


class GridInputAdapterTests(unittest.TestCase):
    def test_keyboard_to_ending_and_restart(self):
        source = campaign()
        state = Session.new(source)
        state = apply_input(state, InputEvent("keyboard", "ArrowRight", True))
        state = apply_input(state, InputEvent("keyboard", "KeyD", True))
        state = apply_input(state, InputEvent("keyboard", "KeyF", True, "victory"))
        self.assertEqual(state.ending, "victory")
        self.assertEqual(Session.restore(source, state.snapshot()).state_digest, state.state_digest)
        self.assertEqual([e["command_id"] for e in state.events], ["input-1", "input-2", "input-3"])

    def test_controller_and_release_do_not_mutate(self):
        state = Session.new(campaign())
        self.assertIs(apply_input(state, InputEvent("controller", "dpad_right", False)), state)
        moved = apply_input(state, InputEvent("controller", "dpad_right", True))
        self.assertEqual((moved.x, moved.tick), (2, 1))
        self.assertEqual(Session.restore(state.campaign, moved.snapshot()).state_digest, moved.state_digest)

    def test_collision_and_unbound_controls_fail_closed(self):
        state = Session.new(campaign())
        with self.assertRaises(GameplayContractError):
            apply_input(state, InputEvent("keyboard", "ArrowUp", True))
        self.assertEqual(state.tick, 0)
        for event in (
            InputEvent("keyboard", "Escape", True),
            InputEvent("controller", "button_99", True),
            InputEvent("keyboard", "KeyE", True),
            InputEvent("keyboard", "ArrowRight", True, "unexpected"),
        ):
            with self.subTest(event=event), self.assertRaises(GameplayContractError):
                apply_input(state, event)

    def test_malformed_inputs_and_sequences(self):
        for device, control, pressed, target in (
            ("mouse", "ArrowRight", True, ""),
            ("keyboard", "ArrowRight", 1, ""),
            ("keyboard", [], True, ""),
            ("keyboard", "KeyE", True, []),
            ("keyboard", "KeyE", True, "x" * 257),
        ):
            with self.assertRaises(GameplayContractError):
                InputEvent(device, control, pressed, target)
        for sequence in (True, 0, 4097, 1.5):
            with self.assertRaises(GameplayContractError):
                translate(InputEvent("keyboard", "ArrowRight", True), sequence)


if __name__ == "__main__":
    unittest.main()
