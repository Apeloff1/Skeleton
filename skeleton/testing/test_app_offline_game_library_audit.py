"""End-to-end bounded offline library custody and fail-closed acceptance."""
from __future__ import annotations

from dataclasses import asdict
import json
import os

import pytest

from skeleton.app.cli import run_app_cli
from skeleton.app.offline_game_library_audit import (
    OfflineGameLibraryAuditError, OfflineGameLibraryEntry,
    audit_offline_game_library, parse_library_entry,
)
from skeleton.testing.test_app_offline_delivery_assurance import delivered

pytestmark = pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor custody")


def _entry(delivered):
    installed, archive, save, manifest, archive_pin, save_pin, _ = delivered
    return OfflineGameLibraryEntry(
        str(installed), str(archive), str(save),
        manifest, archive_pin, save_pin,
    )


def _cli(entry):
    return ["audit-offline-game-library", "--entry",
            json.dumps(asdict(entry)), "--trusted-local-operator"]


def test_real_source_archive_private_save_library_audit(delivered, capsys):
    entry = _entry(delivered)
    before = (
        (delivered[0] / "release.json").read_bytes(),
        delivered[1].read_bytes(),
        delivered[2].read_bytes(),
    )
    assert run_app_cli(_cli(entry)) == 0
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["game_count"] == 1
    assert receipt["games"][0]["replay_digest"] == delivered[-1]
    assert receipt["all_source_archive_save_bindings_verified"] is True
    assert receipt["custody_unchanged_across_batch"] is True
    assert receipt["release_certified"] is False
    assert receipt["package_signed"] is False
    assert "installed_source" not in json.dumps(receipt)
    assert before == (
        (delivered[0] / "release.json").read_bytes(),
        delivered[1].read_bytes(),
        delivered[2].read_bytes(),
    )


@pytest.mark.parametrize("field", [
    "expected_manifest_sha256", "expected_archive_sha256",
    "expected_save_sha256",
])
def test_wrong_independent_pin_blocks_entire_library(delivered, field, capsys):
    payload = asdict(_entry(delivered))
    payload[field] = "0" * 64
    assert run_app_cli(["audit-offline-game-library", "--entry",
                        json.dumps(payload), "--trusted-local-operator"]) == 2
    assert json.loads(capsys.readouterr().err)["status"] == "blocked"


@pytest.mark.parametrize("kind", ["archive", "save", "installed_source"])
def test_hostile_library_member_rejects_success(delivered, kind, tmp_path):
    payload = asdict(_entry(delivered))
    original = payload[kind]
    alias = tmp_path / ("malicious-" + kind)
    alias.symlink_to(original, target_is_directory=kind == "installed_source")
    payload[kind] = str(alias)
    with pytest.raises((OSError, ValueError)):
        audit_offline_game_library(
            [OfflineGameLibraryEntry(**payload)], authorized=True,
        )


def test_duplicate_project_and_duplicate_custody_rejected(delivered):
    entry = _entry(delivered)
    with pytest.raises(OfflineGameLibraryAuditError, match="repeated"):
        audit_offline_game_library([entry, entry], authorized=True)


def test_entry_parser_rejects_duplicate_keys_unknown_fields_and_bad_types(delivered):
    valid = json.dumps(asdict(_entry(delivered)))
    for raw in (
        '{"archive":"a","archive":"b"}',
        valid[:-1] + ',"unexpected":true}',
        valid.replace('"installed_source": "', '"installed_source": 7, "extra": "'),
        "null", "[]", "NaN",
    ):
        with pytest.raises((ValueError, TypeError)):
            parse_library_entry(raw)


def test_missing_authority_rejected_before_any_source_reads(delivered, monkeypatch):
    import skeleton.app.offline_game_library_audit as module
    monkeypatch.setattr(
        module, "_custody",
        lambda *_: pytest.fail("unauthorized source was accessed"),
    )
    with pytest.raises(PermissionError):
        audit_offline_game_library([_entry(delivered)], authorized=False)


def test_cli_missing_authority_rejected(delivered, capsys):
    command = _cli(_entry(delivered))
    command.remove("--trusted-local-operator")
    assert run_app_cli(command) == 2
    assert json.loads(capsys.readouterr().err)["status"] == "blocked"


def test_library_over_limit_rejected_without_read(delivered, monkeypatch):
    import skeleton.app.offline_game_library_audit as module
    monkeypatch.setattr(
        module, "_custody",
        lambda *_: pytest.fail("over-limit library accessed"),
    )
    with pytest.raises(OfflineGameLibraryAuditError, match="1-8"):
        audit_offline_game_library([_entry(delivered)] * 9, authorized=True)


def test_same_bytes_inode_swap_between_game_passes_is_rejected(
    delivered, tmp_path, monkeypatch,
):
    import skeleton.app.offline_game_library_audit as module
    archive = delivered[1]
    original = module._verify
    calls = 0

    def swap_after_first(*args):
        nonlocal calls
        result = original(*args)
        calls += 1
        if calls == 1:
            replacement = tmp_path / "replacement.zip"
            replacement.write_bytes(archive.read_bytes())
            replacement.chmod(0o600)
            os.replace(replacement, archive)
        return result

    monkeypatch.setattr(module, "_verify", swap_after_first)
    with pytest.raises(OfflineGameLibraryAuditError, match="custody changed"):
        audit_offline_game_library([_entry(delivered)], authorized=True)


def test_second_pass_receipt_divergence_is_rejected(delivered, monkeypatch):
    import skeleton.app.offline_game_library_audit as module
    original = module._verify
    calls = 0

    def changed(*args):
        nonlocal calls
        result = original(*args)
        calls += 1
        if calls == 2:
            return {**result, "replay_digest": "0" * 64}
        return result

    monkeypatch.setattr(module, "_verify", changed)
    with pytest.raises(OfflineGameLibraryAuditError, match="final replay"):
        audit_offline_game_library([_entry(delivered)], authorized=True)
