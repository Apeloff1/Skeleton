"""Concurrent consumer export and backup must reflect authoritative saved progress."""
from __future__ import annotations

from skeleton.game.gameplay.ridge_rescue.consumer_cli import play
from skeleton.game.gameplay.ridge_rescue.consumer_store import SlotStore
from skeleton.game.gameplay.ridge_rescue.campaign import verify_export
from skeleton.game.gameplay.ridge_rescue.consumer_backup import verify_backup
from skeleton.game.gameplay.ridge_rescue.consumer_store import _source


def test_export_after_another_process_advances_uses_authoritative_head(tmp_path):
    root = tmp_path / "saves"
    foreground = SlotStore(root)
    other = SlotStore(root)
    initial = foreground.new("journey")
    committed = {}

    def read(_prompt):
        if not committed:
            committed["state"] = other.step(
                "journey", initial["actions"][0], expected_head=initial["head"]
            )
            return "e"
        return "q"

    messages = []
    result = play(foreground, "journey", read=read, write=messages.append)
    exports = list((root / "exports").glob("*.json"))
    assert len(exports) == 1
    verified = verify_export(exports[0].read_bytes())
    assert verified["head"] == committed["state"]["head"]
    assert result["head"] == committed["state"]["head"]
    assert foreground.audit("journey")["verified"]
    assert any("Exported:" in message for message in messages)


def test_backup_after_another_process_advances_preserves_replay(tmp_path):
    root = tmp_path / "saves"
    foreground = SlotStore(root)
    other = SlotStore(root)
    initial = foreground.new("journey")
    committed = {}

    def read(_prompt):
        if not committed:
            committed["state"] = other.step(
                "journey", initial["actions"][0], expected_head=initial["head"]
            )
            return "b"
        return "q"

    messages = []
    result = play(foreground, "journey", read=read, write=messages.append)
    backups = list((root / "exports").glob("*-backup-*.json"))
    assert len(backups) == 1
    session, history = verify_backup(backups[0].read_bytes(), _source())
    assert session["head"] == committed["state"]["head"]
    assert len(history) == committed["state"]["revision"]
    assert result["head"] == committed["state"]["head"]
    assert foreground.audit("journey")["verified"]
    assert any("Backup created:" in message for message in messages)
