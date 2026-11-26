"""Terminal acceptance: advisory commands cannot consume saved turns.

These checks use the real canonical SlotStore and interactive command loop,
rather than replacing the campaign engine with a fake.
"""
from pathlib import Path

from skeleton.game.gameplay.ridge_rescue.consumer_cli import play
from skeleton.game.gameplay.ridge_rescue.consumer_store import SlotStore


def test_advisory_commands_and_invalid_choices_preserve_save(tmp_path: Path):
    store = SlotStore(tmp_path / "save")
    store.new("advisory")
    before = store.load("advisory")
    messages = []
    commands = iter(("help", "h", "j", "999999999", "１２", "not-an-action", "q"))
    result = play(store, "advisory", read=lambda _: next(commands), write=messages.append,
                  ascii_mode=True)
    after = SlotStore(tmp_path / "save").load("advisory")
    assert result["revision"] == after["revision"] == before["revision"] == 0
    assert result["head"] == after["head"] == before["head"]
    assert result["status"] == "playing"
    assert any("Unavailable command" in message for message in messages)
    assert all(message.isascii() for message in messages)


def test_eof_and_keyboard_interrupt_preserve_committed_turn(tmp_path: Path):
    for interruption in (EOFError, KeyboardInterrupt):
        store = SlotStore(tmp_path / interruption.__name__)
        initial = store.new("interrupted")
        action = initial["actions"][0]
        commands = iter(("0",))

        def read(_):
            try:
                return next(commands)
            except StopIteration:
                raise interruption()

        finished = play(store, "interrupted", read=read, write=lambda _: None,
                        ascii_mode=True)
        reopened = SlotStore(tmp_path / interruption.__name__).load("interrupted")
        assert reopened["revision"] == finished["revision"] == 1
        assert reopened["head"] == finished["head"]
        assert reopened["head"] != initial["head"]
