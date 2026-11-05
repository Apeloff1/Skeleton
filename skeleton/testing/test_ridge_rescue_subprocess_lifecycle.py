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


def test_oversized_action_json_is_rejected_before_parsing_and_preserves_save(tmp_path: Path):
    """External action payloads have a fixed budget, even when JSON is valid."""
    home = tmp_path / "bounded-action"
    initial = _json(home, "new")
    oversized = json.dumps({"verb": "move", "padding": "x" * 5000})
    rejected = _invoke(home, "step", "--action", oversized,
                       "--expected-head", initial["head"])
    assert rejected.returncode != 0
    assert b"action JSON exceeds byte budget" in rejected.stderr
    unchanged = _json(home, "status")
    assert unchanged["head"] == initial["head"]
    assert unchanged["revision"] == 0
    assert _json(home, "audit")["audit_entries"] == 0
    advanced = _json(home, "step", "--action", json.dumps(initial["actions"][0]),
                     "--expected-head", initial["head"])
    assert advanced["revision"] == 1
    assert _json(home, "audit")["verified"] is True


def test_ambiguous_action_json_rejected_without_mutating_save(tmp_path: Path):
    home = tmp_path / "strict-json"
    initial = _json(home, "new")
    invalid = ('{"verb":"move","verb":"rest"}',
               '{"verb":"move","distance":NaN}',
               '{"verb":"move","distance":Infinity}',
               '{"verb":"move","nested":{"x":1,"x":2}}')
    for payload in invalid:
        failed = _invoke(home, "step", "--action", payload,
                         "--expected-head", initial["head"])
        assert failed.returncode != 0
        assert _json(home, "status")["head"] == initial["head"]
        assert _json(home, "audit")["audit_entries"] == 0
    committed = _json(home, "step", "--action", json.dumps(initial["actions"][0]),
                      "--expected-head", initial["head"])
    assert committed["revision"] == 1
    assert _json(home, "audit")["verified"] is True


def test_exponent_overflow_action_rejected_without_save_mutation(tmp_path: Path):
    """Valid JSON exponent syntax must not smuggle infinity into a game action."""
    home = tmp_path / "overflow-action"
    initial = _json(home, "new")
    for number in ("1e999", "-1e999", "9.9e999"):
        payload = '{"verb":"move","distance":' + number + "}"
        rejected = _invoke(home, "step", "--action", payload,
                           "--expected-head", initial["head"])
        assert rejected.returncode != 0
        assert b"non-finite action JSON number" in rejected.stderr
        assert _json(home, "status")["head"] == initial["head"]
        assert _json(home, "audit")["audit_entries"] == 0
    committed = _json(home, "step", "--action", json.dumps(initial["actions"][0]),
                      "--expected-head", initial["head"])
    assert committed["revision"] == 1
    assert _json(home, "audit")["verified"] is True



def test_mid_campaign_backup_restore_and_independent_ending_replay(tmp_path: Path):
    """A real process may resume from a mid-campaign backup and earn the same ending.

    This crosses separate SQLite stores and interpreter boundaries rather than
    merely checking that an exported snapshot can be decoded.
    """
    original_home = tmp_path / "original"
    recovered_home = tmp_path / "recovered"
    state = _json(original_home, "new")
    sequence = acceptance_actions("protect") + LAST_SIGNAL
    midpoint = len(sequence) // 2
    assert 0 < midpoint < len(sequence)

    for action in sequence[:midpoint]:
        state = _json(original_home, "step", "--action", json.dumps(action),
                      "--expected-head", state["head"])
    assert state["revision"] == midpoint
    mid_head = state["head"]
    backup = _json(original_home, "backup")
    backup_bytes = Path(backup["path"]).read_bytes()

    # Recovery is intentionally performed in a separate private data root.
    restored_process = _invoke(recovered_home, "restore-backup",
                               "--file", "-", stdin=backup_bytes)
    assert restored_process.returncode == 0, (
        restored_process.stdout.decode(errors="replace"),
        restored_process.stderr.decode(errors="replace"),
    )
    restored = _json(recovered_home, "status")
    assert restored["head"] == mid_head
    assert restored["revision"] == midpoint
    assert _json(recovered_home, "audit")["audit_entries"] == midpoint

    # Both stores must produce exactly the same deterministic head at every
    # subsequent turn, despite having independent SQLite connections/files.
    for revision, action in enumerate(sequence[midpoint:], midpoint + 1):
        original = _json(original_home, "step", "--action", json.dumps(action),
                         "--expected-head", state["head"])
        recovered = _json(recovered_home, "step", "--action", json.dumps(action),
                          "--expected-head", restored["head"])
        assert original["head"] == recovered["head"]
        assert original["revision"] == recovered["revision"] == revision
        assert original["status"] == recovered["status"]
        state, restored = original, recovered

    assert state["status"] == "completed"
    assert restored["status"] == "completed"
    assert state["index"] == restored["index"] == 2
    for home in (original_home, recovered_home):
        audit = _json(home, "audit")
        assert audit["verified"] is True
        assert audit["audit_entries"] == len(sequence)
        assert audit["head"] == state["head"]
        exported = _json(home, "export")
        export_bytes = Path(exported["path"]).read_bytes()
        verified = _invoke(home, "verify-export", "--file", "-", stdin=export_bytes)
        assert verified.returncode == 0, verified.stderr.decode(errors="replace")
        assert json.loads(verified.stdout)["head"] == state["head"]


def test_rejected_backup_cannot_replace_independent_playable_slot(tmp_path: Path):
    """A failed cross-install restore must preserve both existing game histories."""
    source_home = tmp_path / "source"
    target_home = tmp_path / "target"
    source = _json(source_home, "new")
    target = _json(target_home, "new")
    source = _json(source_home, "step", "--action",
                   json.dumps(source["actions"][0]), "--expected-head", source["head"])
    target = _json(target_home, "step", "--action",
                   json.dumps(target["actions"][0]), "--expected-head", target["head"])
    source_backup = Path(_json(source_home, "backup")["path"]).read_bytes()
    assert source_backup
    corrupted = bytearray(source_backup)
    corrupted[len(corrupted) // 2] ^= 1
    before = _json(target_home, "status")
    for payload in (bytes(corrupted), b"{}", b""):
        rejected = _invoke(target_home, "restore-backup", "--file", "-", stdin=payload)
        assert rejected.returncode != 0
        assert _json(target_home, "status")["head"] == before["head"]
        assert _json(target_home, "audit")["verified"] is True
    assert _json(source_home, "status")["head"] == source["head"]
    assert _json(source_home, "audit")["verified"] is True
    # A failed restore must not lock out subsequent valid user actions.
    resumed = _json(target_home, "status")
    if resumed["actions"]:
        advanced = _json(target_home, "step", "--action",
                         json.dumps(resumed["actions"][0]),
                         "--expected-head", resumed["head"])
        assert advanced["revision"] == resumed["revision"] + 1
        assert _json(target_home, "audit")["verified"] is True
