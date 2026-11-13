"""Real installed original-game relocation and private replay continuity."""
from __future__ import annotations

from dataclasses import asdict, replace
import json
import os

import pytest

from skeleton.app.cli import run_app_cli
from skeleton.app.offline_game_library_audit import OfflineGameLibraryEntry
from skeleton.app.offline_game_library_relocation import (
    OfflineGameLibraryRelocationError, assure_offline_library_relocation,
)
from skeleton.testing.test_app_offline_delivery_assurance import delivered

pytestmark = pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor custody")


def _pair(delivered, tmp_path, capsys):
    installed, archive, save, manifest, archive_pin, save_pin, _ = delivered
    fresh = tmp_path / "relocated-install"
    assert run_app_cli([
        "studio-journey", "--install-archive", "--archive", str(archive),
        "--expected-archive-sha256", archive_pin,
        "--expected-manifest-sha256", manifest,
        "--output", str(fresh), "--trusted-local-operator",
    ]) == 0
    capsys.readouterr()
    old = OfflineGameLibraryEntry(
        str(installed), str(archive), str(save),
        manifest, archive_pin, save_pin,
    )
    new = replace(old, installed_source=str(fresh))
    return old, new


def _cli(old, new):
    return [
        "audit-offline-library-relocation",
        "--before", json.dumps(asdict(old)),
        "--after", json.dumps(asdict(new)),
        "--trusted-local-operator",
    ]


def test_real_reinstalled_source_retains_private_progress(delivered, tmp_path, capsys):
    old, new = _pair(delivered, tmp_path, capsys)
    before = (
        delivered[1].read_bytes(), delivered[2].read_bytes(),
        (tmp_path / "relocated-install" / "release.json").read_bytes(),
    )
    assert run_app_cli(_cli(old, new)) == 0
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["game_count"] == 1
    assert receipt["private_progress_preserved"] is True
    assert receipt["old_and_new_installations_replayed"] is True
    assert receipt["relocation_performed"] is False
    assert receipt["migration_atomicity_proven"] is False
    assert receipt["release_certified"] is False
    assert before == (
        delivered[1].read_bytes(), delivered[2].read_bytes(),
        (tmp_path / "relocated-install" / "release.json").read_bytes(),
    )


def test_same_install_root_is_not_relocation(delivered, tmp_path, capsys):
    old, _ = _pair(delivered, tmp_path, capsys)
    with pytest.raises(OfflineGameLibraryRelocationError, match="distinct"):
        assure_offline_library_relocation([old], [old], authorized=True)


def test_foreign_archive_or_save_pin_fails_closed(delivered, tmp_path, capsys):
    old, new = _pair(delivered, tmp_path, capsys)
    for key in ("expected_archive_sha256", "expected_save_sha256"):
        with pytest.raises((OSError, ValueError)):
            assure_offline_library_relocation(
                [old], [replace(new, **{key: "0" * 64})], authorized=True,
            )


def test_source_mutation_blocks_relocation(delivered, tmp_path, capsys):
    old, new = _pair(delivered, tmp_path, capsys)
    (tmp_path / "relocated-install" / "index.html").write_text("tampered")
    with pytest.raises((OSError, ValueError)):
        assure_offline_library_relocation([old], [new], authorized=True)


def test_cli_denies_missing_operator_acknowledgement(delivered, tmp_path, capsys):
    old, new = _pair(delivered, tmp_path, capsys)
    argv = _cli(old, new)
    argv.remove("--trusted-local-operator")
    assert run_app_cli(argv) == 2
    assert json.loads(capsys.readouterr().err)["status"] == "blocked"


def test_authority_precedes_any_reads(delivered, tmp_path, capsys, monkeypatch):
    old, new = _pair(delivered, tmp_path, capsys)
    import skeleton.app.offline_game_library_relocation as module
    monkeypatch.setattr(
        module, "_custody",
        lambda *_: pytest.fail("read attempted without authority"),
    )
    with pytest.raises(PermissionError):
        assure_offline_library_relocation([old], [new], authorized=False)


def test_source_directory_substitution_during_proof_rejected(
    delivered, tmp_path, capsys, monkeypatch,
):
    old, new = _pair(delivered, tmp_path, capsys)
    import skeleton.app.offline_game_library_relocation as module
    original = module.audit_offline_game_library
    calls = 0

    def substitute(*args, **kwargs):
        nonlocal calls
        receipt = original(*args, **kwargs)
        calls += 1
        if calls == 1:
            source = tmp_path / "relocated-install"
            replacement = tmp_path / "replacement-source"
            replacement.mkdir()
            # The proof must reject a directory replacement during the
            # cross-library audit; no destructive cleanup is attempted.
            os.rename(source, tmp_path / "old-source-moved")
            os.rename(replacement, source)
        return receipt

    monkeypatch.setattr(module, "audit_offline_game_library", substitute)
    with pytest.raises((OSError, ValueError)):
        assure_offline_library_relocation([old], [new], authorized=True)
