"""Real three-checkpoint handoff acceptance, replay, tamper and fork tests."""
from __future__ import annotations

from dataclasses import asdict
import json
import os

import pytest

from skeleton.app.cli import run_app_cli
from skeleton.app.offline_mixed_library_epoch_handoff import (
    publish_mixed_library_epoch_handoff,
)
from skeleton.app.offline_mixed_library_epoch_receipt_chain import (
    EpochReceiptCheckpoint, audit_mixed_library_epoch_receipt_chain,
)
from skeleton.testing.test_app_offline_mixed_library_epoch_chain import (
    _epoch, catalog,
)
from skeleton.testing.test_app_offline_mixed_game_library_continuity import _advance

pytestmark = pytest.mark.skipif(os.name != "posix", reason="POSIX private custody")


def _checkpoints(catalog, tmp_path):
    unsigned, signed = catalog
    u1 = _advance(unsigned, tmp_path / "receipt-chain-u1.json")
    s2 = _advance(signed, tmp_path / "receipt-chain-s2.json")
    u3 = _advance(u1, tmp_path / "receipt-chain-u3.json")
    epochs = (
        _epoch(unsigned, signed), _epoch(u1, signed),
        _epoch(u1, s2), _epoch(u3, s2),
    )
    result = []
    for count in (2, 3, 4):
        path = tmp_path / ("checkpoint-" + str(count) + ".json")
        published = publish_mixed_library_epoch_handoff(
            epochs[:count], path, authorized=True,
        )
        result.append(EpochReceiptCheckpoint(
            epochs[:count], str(path), published["receipt_sha256"],
        ))
    return tuple(result)


def _cli(checkpoints):
    args = ["audit-mixed-library-epoch-receipts"]
    for item in checkpoints:
        args += ["--checkpoint", json.dumps({
            "unsigned_generations": [
                [asdict(game) for game in epoch.unsigned]
                for epoch in item.epochs
            ],
            "signed_generations": [
                [asdict(game) for game in epoch.signed]
                for epoch in item.epochs
            ],
            "receipt": str(item.receipt),
            "sha256": item.expected_sha256,
        })]
    return args + ["--trusted-local-operator"]


def test_three_real_pinned_receipts_replay_all_games(catalog, tmp_path, capsys):
    checkpoints = _checkpoints(catalog, tmp_path)
    original = tuple(
        open(item.receipt, "rb").read() for item in checkpoints
    )
    assert run_app_cli(_cli(checkpoints)) == 0
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["checkpoint_count"] == 3
    assert receipt["generation_count"] == 4
    assert receipt["game_count"] == 2
    assert len(receipt["successor_evidence_sha256_chain"]) == 2
    assert receipt["all_pinned_receipts_reverified"] is True
    assert receipt["all_successors_advanced"] is True
    assert receipt["historical_replay_prefixes_preserved"] is True
    assert receipt["persistent_rollback_protection"] is False
    assert receipt["release_certified"] is False
    assert receipt == audit_mixed_library_epoch_receipt_chain(
        checkpoints, authorized=True,
    )
    assert tuple(open(item.receipt, "rb").read() for item in checkpoints) == original


def test_middle_receipt_tamper_rejected(catalog, tmp_path):
    checkpoints = _checkpoints(catalog, tmp_path)
    path = checkpoints[1].receipt
    with open(path, "ab") as stream:
        stream.write(b" ")
    with pytest.raises(ValueError):
        audit_mixed_library_epoch_receipt_chain(
            checkpoints, authorized=True,
        )


def test_middle_independent_pin_switch_rejected(catalog, tmp_path):
    checkpoints = _checkpoints(catalog, tmp_path)
    bad = EpochReceiptCheckpoint(
        checkpoints[1].epochs, checkpoints[1].receipt, "0" * 64,
    )
    with pytest.raises(ValueError):
        audit_mixed_library_epoch_receipt_chain(
            (checkpoints[0], bad, checkpoints[2]), authorized=True,
        )


def test_missing_checkpoint_and_fork_rejected(catalog, tmp_path):
    checkpoints = _checkpoints(catalog, tmp_path)
    with pytest.raises(ValueError):
        audit_mixed_library_epoch_receipt_chain(
            (checkpoints[0], checkpoints[2]), authorized=True,
        )
    forked = EpochReceiptCheckpoint(
        checkpoints[1].epochs[:-1] + checkpoints[1].epochs[:1],
        checkpoints[1].receipt, checkpoints[1].expected_sha256,
    )
    with pytest.raises(ValueError):
        audit_mixed_library_epoch_receipt_chain(
            (checkpoints[0], forked, checkpoints[2]), authorized=True,
        )


def test_duplicate_receipt_and_unauthorized_rejected(catalog, tmp_path):
    checkpoints = _checkpoints(catalog, tmp_path)
    duplicate = EpochReceiptCheckpoint(
        checkpoints[1].epochs, checkpoints[0].receipt,
        checkpoints[1].expected_sha256,
    )
    with pytest.raises(ValueError):
        audit_mixed_library_epoch_receipt_chain(
            (checkpoints[0], duplicate, checkpoints[2]), authorized=True,
        )
    with pytest.raises(PermissionError):
        audit_mixed_library_epoch_receipt_chain(
            checkpoints, authorized=False,
        )


def test_cli_requires_bounded_pinned_checkpoints(capsys):
    assert run_app_cli([
        "audit-mixed-library-epoch-receipts",
        "--checkpoint", "{}",
        "--trusted-local-operator",
    ]) == 2
    assert json.loads(capsys.readouterr().err)["status"] == "blocked"
