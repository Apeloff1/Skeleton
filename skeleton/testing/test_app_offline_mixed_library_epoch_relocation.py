"""Real multi-epoch signed/unsigned relocation acceptance and fail-closed cases."""
from __future__ import annotations

from dataclasses import asdict, replace
import json
import os
from pathlib import Path
import shutil

import pytest

from skeleton.app.cli import run_app_cli
from skeleton.app.offline_mixed_library_epoch_relocation import (
    assure_mixed_library_epoch_relocation,
)
from skeleton.testing.test_app_offline_mixed_library_epoch_chain import (
    _epoch, catalog,
)
from skeleton.testing.test_app_offline_mixed_game_library_continuity import _advance

pytestmark = pytest.mark.skipif(os.name != "posix", reason="POSIX private custody")


def _relocated(entry, destination):
    shutil.copytree(entry.installed_source, destination)
    return replace(entry, installed_source=str(destination))


def _catalogs(catalog, tmp_path):
    unsigned, signed = catalog
    u1 = _advance(unsigned, tmp_path / "relocation-epoch-u1.json")
    s2 = _advance(signed, tmp_path / "relocation-epoch-s2.json")
    original = (_epoch(unsigned, signed), _epoch(u1, signed), _epoch(u1, s2))
    relocated_unsigned = _relocated(unsigned, tmp_path / "new-unsigned-game")
    relocated_signed = _relocated(signed, tmp_path / "new-signed-game")
    ru1 = replace(u1, installed_source=relocated_unsigned.installed_source)
    rs2 = replace(s2, installed_source=relocated_signed.installed_source)
    moved = (
        _epoch(relocated_unsigned, relocated_signed),
        _epoch(ru1, relocated_signed),
        _epoch(ru1, rs2),
    )
    return original, moved


def _cli(original, moved):
    result = ["audit-mixed-library-epoch-relocation"]
    for name, epochs, attr in (
        ("before-unsigned-generation", original, "unsigned"),
        ("before-signed-generation", original, "signed"),
        ("after-unsigned-generation", moved, "unsigned"),
        ("after-signed-generation", moved, "signed"),
    ):
        for epoch in epochs:
            result.extend(("--" + name, json.dumps([
                asdict(item) for item in getattr(epoch, attr)
            ])))
    return result + ["--trusted-local-operator"]


def test_real_three_generation_relocation_replays_all_games(catalog, tmp_path, capsys):
    original, moved = _catalogs(catalog, tmp_path)
    assert run_app_cli(_cli(original, moved)) == 0
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["generation_count"] == 3
    assert receipt["game_count"] == 2
    assert receipt["all_original_and_relocated_games_reexecuted"] is True
    assert receipt["all_private_replay_prefixes_preserved"] is True
    assert receipt["signer_policy_history_preserved"] is True
    assert receipt["distinct_original_and_relocated_installations"] is True
    assert receipt["original_chain_sha256"] == receipt["relocated_chain_sha256"]
    assert len(receipt["relocation_receipt_sha256_chain"]) == 3
    assert receipt["relocation_performed"] is False
    assert receipt["native_device_qualified"] is False
    assert receipt["release_certified"] is False


def test_relocation_receipt_is_deterministic(catalog, tmp_path):
    original, moved = _catalogs(catalog, tmp_path)
    first = assure_mixed_library_epoch_relocation(
        original, moved, authorized=True,
    )
    second = assure_mixed_library_epoch_relocation(
        original, moved, authorized=True,
    )
    assert first == second
    assert first["evidence_sha256"] == second["evidence_sha256"]


def test_relocation_to_same_source_inode_rejected(catalog, tmp_path):
    original, moved = _catalogs(catalog, tmp_path)
    with pytest.raises(ValueError):
        assure_mixed_library_epoch_relocation(
            original, original, authorized=True,
        )


def test_relocated_save_rollback_rejected(catalog, tmp_path):
    original, moved = _catalogs(catalog, tmp_path)
    reverted = _epoch(
        replace(moved[2].unsigned[0],
                private_save=moved[0].unsigned[0].private_save,
                expected_save_sha256=moved[0].unsigned[0].expected_save_sha256),
        moved[2].signed[0],
    )
    with pytest.raises(ValueError):
        assure_mixed_library_epoch_relocation(
            original, (*moved[:2], reverted), authorized=True,
        )


def test_relocated_signer_pin_switch_rejected(catalog, tmp_path):
    original, moved = _catalogs(catalog, tmp_path)
    bad = _epoch(
        moved[1].unsigned[0],
        replace(moved[1].signed[0], expected_public_key_sha256="0" * 64),
    )
    with pytest.raises(ValueError):
        assure_mixed_library_epoch_relocation(
            original, (moved[0], bad, moved[2]), authorized=True,
        )


def test_requires_authorization_and_matching_epochs(catalog, tmp_path):
    original, moved = _catalogs(catalog, tmp_path)
    with pytest.raises(PermissionError):
        assure_mixed_library_epoch_relocation(
            original, moved, authorized=False,
        )
    with pytest.raises(ValueError):
        assure_mixed_library_epoch_relocation(
            original, moved[:-1], authorized=True,
        )


def test_cli_rejects_unpaired_generation_inputs(capsys):
    assert run_app_cli([
        "audit-mixed-library-epoch-relocation",
        "--before-unsigned-generation", "[]",
        "--before-unsigned-generation", "[]",
        "--before-signed-generation", "[]",
        "--after-unsigned-generation", "[]",
        "--after-signed-generation", "[]",
        "--trusted-local-operator",
    ]) == 2
    assert json.loads(capsys.readouterr().err)["status"] == "blocked"
