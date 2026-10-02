from __future__ import annotations

import json

import pytest

from skeleton.reliability.backup_restore import BackupManager


def _manager(tmp_path):
    root = tmp_path / ".skeleton"
    root.mkdir()
    return root, BackupManager(root)


def test_delete_state_purges_live_and_all_historical_backup_copies(tmp_path) -> None:
    root, manager = _manager(tmp_path)
    (root / "secrets.json").write_text('{"token":"secret-one"}', encoding="utf-8")
    (root / "events.jsonl").write_text('{"event":"keep"}\n', encoding="utf-8")
    first = manager.backup("first")

    (root / "secrets.json").write_text('{"token":"secret-two"}', encoding="utf-8")
    second = manager.backup("second")

    result = manager.delete_state("secrets.json")

    assert result["live_deleted"] is True
    assert result["purged_backups"] == (
        first["backup_id"],
        second["backup_id"],
    )
    assert not (root / "secrets.json").exists()

    for entry in manager.list_backups():
        assert "secrets.json" not in entry["files"]
        assert "secrets.json" not in entry["checksums"]
        blob = json.loads(
            (root / "backups" / f"{entry['backup_id']}.json").read_text(
                encoding="utf-8"
            )
        )
        assert "secrets.json" not in blob["files"]
        assert "secrets.json" not in blob["checksums"]
        assert "secret-one" not in json.dumps(blob)
        assert "secret-two" not in json.dumps(blob)

    manager.restore(first["backup_id"], dry_run=False)
    assert not (root / "secrets.json").exists()
    assert (root / "events.jsonl").exists()


def test_delete_state_fails_closed_before_live_delete_when_backup_is_unreadable(
    tmp_path,
) -> None:
    root, manager = _manager(tmp_path)
    live = root / "secrets.json"
    live.write_text('{"token":"must-survive-preflight"}', encoding="utf-8")
    entry = manager.backup("corrupt-me")
    backup = root / "backups" / f"{entry['backup_id']}.json"
    backup.write_text("{not-json", encoding="utf-8")

    with pytest.raises(RuntimeError, match="indexed backup is unreadable"):
        manager.delete_state("secrets.json")

    assert live.read_text(encoding="utf-8") == '{"token":"must-survive-preflight"}'


@pytest.mark.parametrize(
    "name",
    ["../secrets.json", "unknown.json", "", "/tmp/secrets.json"],
)
def test_delete_state_rejects_unmanaged_or_traversal_names(
    tmp_path,
    name: str,
) -> None:
    _root, manager = _manager(tmp_path)
    with pytest.raises(ValueError, match="not backup-managed"):
        manager.delete_state(name)
