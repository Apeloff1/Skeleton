"""Real process-boundary lifecycle for the original Cinder Ridge consumer.

Unlike in-process acceptance, every action below starts a fresh interpreter,
loads the previous SQLite revision and exits. The test uses a private XDG
directory, never the developer's actual saves or network services.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

from skeleton.game.gameplay.ridge_rescue.acceptance import acceptance_actions
from skeleton.game.gameplay.ridge_rescue.campaign_acceptance import LAST_SIGNAL


MODULE = "skeleton.game.gameplay.ridge_rescue.consumer_cli"


def _invoke(home: Path, command: str, *options: str, stdin: bytes | None = None):
    env = dict(os.environ)
    # The consumer selects LOCALAPPDATA on Windows and XDG_DATA_HOME elsewhere.
    # Isolate both so a subprocess can never touch a real user save.
    env["XDG_DATA_HOME"] = str(home)
    env["LOCALAPPDATA"] = str(home)
    result = subprocess.run(
        [sys.executable, "-m", MODULE, command, "--slot", "process-game", *options],
        input=stdin, capture_output=True, env=env, timeout=25, check=False,
    )
    return result


def _json(home: Path, command: str, *options: str):
    result = _invoke(home, command, *options)
    assert result.returncode == 0, (
        command, result.stdout.decode(errors="replace"),
        result.stderr.decode(errors="replace"),
    )
    return json.loads(result.stdout)


def test_real_interpreter_restart_every_turn_and_earned_ending(tmp_path: Path):
    home = tmp_path / "private-data"
    state = _json(home, "new")
    assert not (tmp_path / "unrelated").exists()
    assert state["status"] == "playing"
    assert state["revision"] == 0
    sequence = acceptance_actions("protect") + LAST_SIGNAL
    assert len(sequence) > 10
    for revision, action in enumerate(sequence, 1):
        old_head = state["head"]
        state = _json(home, "step", "--action", json.dumps(action),
                      "--expected-head", old_head)
        assert state["revision"] == revision
        assert state["head"] != old_head
        restarted = _json(home, "status")
        assert restarted["head"] == state["head"]
        assert restarted["revision"] == revision
        assert restarted["index"] == state["index"]
    assert state["status"] == "completed"
    assert state["index"] == 2
    audit = _json(home, "audit")
    assert audit["verified"] is True
    assert audit["audit_entries"] == len(sequence)
    assert audit["head"] == state["head"]
    exported = _json(home, "export")
    backup = _json(home, "backup")
    export_path = Path(exported["path"])
    backup_path = Path(backup["path"])
    assert export_path.is_file() and backup_path.is_file()
    verified = _invoke(home, "verify-export", "--file", "-", stdin=export_path.read_bytes())
    assert verified.returncode == 0, verified.stderr.decode(errors="replace")
    assert json.loads(verified.stdout)["head"] == state["head"]
    checked_backup = _invoke(home, "verify-backup", "--file", "-", stdin=backup_path.read_bytes())
    assert checked_backup.returncode == 0, checked_backup.stderr.decode(errors="replace")
    assert json.loads(checked_backup.stdout)["actions"] == len(sequence)
    restored = _invoke(home, "restore-backup", "--slot", "recovered",
                       "--file", "-", stdin=backup_path.read_bytes())
    assert restored.returncode == 0, restored.stderr.decode(errors="replace")
    recovered = json.loads(restored.stdout)
    assert recovered["head"] == state["head"]
    assert recovered["status"] == "completed"
    original = _json(home, "status")
    assert original["head"] == state["head"]
    assert original["revision"] == len(sequence)


def test_stale_process_command_and_corrupt_restore_leave_slot_unchanged(tmp_path: Path):
    home = tmp_path / "private-data"
    first = _json(home, "new")
    action = first["actions"][0]
    advanced = _json(home, "step", "--action", json.dumps(action),
                     "--expected-head", first["head"])
    stale = _invoke(home, "step", "--action", json.dumps(action),
                    "--expected-head", first["head"])
    assert stale.returncode != 0
    assert _json(home, "status")["head"] == advanced["head"]
    malformed = _invoke(home, "restore-backup", "--slot", "bad-restore",
                        "--file", "-", stdin=b'{"invalid":true}')
    assert malformed.returncode != 0
    missing = _invoke(home, "status", "--slot", "bad-restore")
    assert missing.returncode != 0
    assert _json(home, "status")["head"] == advanced["head"]


def test_read_only_journal_survives_process_restart(tmp_path: Path):
    """The noninteractive journal must not mutate the authoritative save."""
    home = tmp_path / "private-data"
    initial = _json(home, "new")
    empty = _json(home, "journal")
    assert empty["slot"] == "process-game"
    assert empty["head"] == initial["head"]
    assert empty["revision"] == 0
    assert isinstance(empty["journal"], str)
    action = initial["actions"][0]
    advanced = _json(home, "step", "--action", json.dumps(action),
                     "--expected-head", initial["head"])
    journal = _json(home, "journal")
    assert journal["head"] == advanced["head"]
    assert journal["revision"] == 1
    assert isinstance(journal["journal"], str)
    assert _json(home, "status")["head"] == advanced["head"]
    assert _json(home, "audit")["audit_entries"] == 1


def test_interactive_journal_refreshes_concurrent_save_without_consuming_turn(tmp_path: Path):
    """An interactive player must not display an obsolete journal after another writer commits."""
    from skeleton.game.gameplay.ridge_rescue.consumer_cli import play
    from skeleton.game.gameplay.ridge_rescue.consumer_store import SlotStore

    root = tmp_path / "private-game"
    player = SlotStore(root)
    initial = player.new("shared")
    displayed: list[str] = []
    commands = iter(("j", "q"))
    advanced = None

    def read(_prompt: str) -> str:
        nonlocal advanced
        command = next(commands)
        if command == "j":
            other = SlotStore(root)
            advanced = other.step("shared", initial["actions"][0],
                                  expected_head=initial["head"])
        return command

    result = play(player, "shared", read=read, write=displayed.append)
    assert advanced is not None
    assert result["head"] == advanced["head"]
    assert result["revision"] == 1
    from skeleton.game.gameplay.ridge_rescue.consumer_experience import recent_events
    assert recent_events(advanced) in displayed
    assert player.audit("shared")["audit_entries"] == 1


def test_interactive_hint_refreshes_concurrent_save_without_consuming_turn(tmp_path: Path):
    """A hint is advisory but must use the latest authoritative state."""
    from skeleton.game.gameplay.ridge_rescue.consumer_cli import play
    from skeleton.game.gameplay.ridge_rescue.consumer_store import SlotStore
    from skeleton.game.gameplay.ridge_rescue.consumer_experience import navigation_hint

    root = tmp_path / "private-game"
    player = SlotStore(root)
    initial = player.new("shared")
    displayed: list[str] = []
    commands = iter(("h", "q"))
    advanced = None

    def read(_prompt: str) -> str:
        nonlocal advanced
        command = next(commands)
        if command == "h":
            advanced = SlotStore(root).step("shared", initial["actions"][0],
                                            expected_head=initial["head"])
        return command

    result = play(player, "shared", read=read, write=displayed.append)
    assert advanced is not None
    assert result["head"] == advanced["head"]
    assert result["revision"] == 1
    assert navigation_hint(advanced) in displayed
    assert player.audit("shared")["audit_entries"] == 1


def test_interactive_export_and_backup_refresh_concurrent_save(tmp_path: Path):
    """Read-only custody commands must refresh the next interactive menu."""
    from skeleton.game.gameplay.ridge_rescue.consumer_cli import play
    from skeleton.game.gameplay.ridge_rescue.consumer_store import SlotStore

    for command, confirmation in (("e", "Exported:"), ("b", "Backup created:")):
        root = tmp_path / command
        store = SlotStore(root)
        initial = store.new("shared")
        messages: list[str] = []
        commands = iter((command, "q"))
        advanced = None

        def read(_prompt: str) -> str:
            nonlocal advanced
            answer = next(commands)
            if answer == command:
                advanced = SlotStore(root).step(
                    "shared", initial["actions"][0], expected_head=initial["head"]
                )
            return answer

        final = play(store, "shared", read=read, write=messages.append)
        assert advanced is not None
        assert final["head"] == advanced["head"]
        assert any(message.startswith(confirmation) for message in messages)
        assert any("Revision: 1" in message for message in messages)
        assert store.audit("shared")["audit_entries"] == 1


def test_malformed_subprocess_action_never_advances_saved_revision(tmp_path: Path):
    """Malformed external commands must not corrupt a valid restarted game."""
    home = tmp_path / "isolated-save"
    initial = _json(home, "new")
    malformed = (
        b"{",
        b"null",
        b"[]",
        b'"not-an-action"',
    )
    for payload in malformed:
        failed = _invoke(
            home, "step", "--action", payload.decode("ascii"),
            "--expected-head", initial["head"],
        )
        assert failed.returncode != 0
        after = _json(home, "status")
        assert after["head"] == initial["head"]
        assert after["revision"] == 0
        audit = _json(home, "audit")
        assert audit["verified"] is True
        assert audit["audit_entries"] == 0

    action = initial["actions"][0]
    advanced = _json(
        home, "step", "--action", json.dumps(action),
        "--expected-head", initial["head"],
    )
    assert advanced["revision"] == 1
    assert _json(home, "audit")["audit_entries"] == 1


def test_interactive_eof_preserves_committed_turn_and_restart(tmp_path: Path):
    """A closed terminal must quit cleanly without rolling back the last turn."""
    from skeleton.game.gameplay.ridge_rescue.consumer_cli import play
    from skeleton.game.gameplay.ridge_rescue.consumer_store import SlotStore

    root = tmp_path / "closed-terminal"
    store = SlotStore(root)
    initial = store.new("shared")
    responses = iter(("0",))

    def read(_prompt: str) -> str:
        try:
            return next(responses)
        except StopIteration:
            raise EOFError from None

    displayed: list[str] = []
    result = play(store, "shared", read=read, write=displayed.append)
    assert result["revision"] == 1
    assert result["head"] != initial["head"]
    restarted = SlotStore(root).load("shared")
    assert restarted["head"] == result["head"]
    assert restarted["revision"] == 1
    assert SlotStore(root).audit("shared")["audit_entries"] == 1


def test_interactive_stale_number_is_rejected_and_new_state_displayed(tmp_path: Path):
    """A menu choice from an old revision cannot replay against another writer."""
    from skeleton.game.gameplay.ridge_rescue.consumer_cli import play
    from skeleton.game.gameplay.ridge_rescue.consumer_store import SlotStore

    root = tmp_path / "concurrent-menu"
    store = SlotStore(root)
    initial = store.new("shared")
    responses = iter(("0", "q"))
    messages: list[str] = []
    advanced = None

    def read(_prompt: str) -> str:
        nonlocal advanced
        answer = next(responses)
        if answer == "0":
            advanced = SlotStore(root).step(
                "shared", initial["actions"][0], expected_head=initial["head"]
            )
        return answer

    final = play(store, "shared", read=read, write=messages.append)
    assert advanced is not None
    assert final["head"] == advanced["head"]
    assert final["revision"] == 1
    assert any("Action not saved; refreshing authoritative slot:" in m for m in messages)
    assert any("Revision: 1" in m for m in messages)
    assert SlotStore(root).audit("shared")["audit_entries"] == 1
