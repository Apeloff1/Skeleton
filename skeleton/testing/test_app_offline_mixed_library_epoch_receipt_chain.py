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
from skeleton.testing.test_app_offline_mixed_game_library_continuity import chain_delivery  # noqa: F401  (transitive fixture)
from skeleton.testing.test_app_offline_policy_chain_delivery import delivered  # noqa: F401  (transitive fixture)
from skeleton.testing.test_app_offline_policy_signed_delivery import policy_migration  # noqa: F401  (transitive fixture)
from skeleton.testing.test_app_offline_policy_signed_progress_migration import migration  # noqa: F401  (transitive fixture)
from skeleton.testing.test_app_offline_signed_progress_migration import signed  # noqa: F401  (transitive fixture)

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



def test_receipt_chain_mid_replay_swap_rejected(
    catalog, tmp_path, monkeypatch,
):
    """A receipt changed after the first successor must fail identity fencing."""
    from pathlib import Path
    from skeleton.app import offline_mixed_library_epoch_receipt_chain as module

    checkpoints = _checkpoints(catalog, tmp_path)
    original = module.assure_mixed_library_epoch_successor
    seen = 0

    def swap_after_first(*args, **kwargs):
        nonlocal seen
        result = original(*args, **kwargs)
        seen += 1
        if seen == 1:
            target = Path(checkpoints[1].receipt)
            replacement = tmp_path / "checkpoint-replacement.json"
            replacement.write_bytes(target.read_bytes())
            os.chmod(replacement, 0o600)
            os.replace(replacement, target)
        return result

    monkeypatch.setattr(
        module, "assure_mixed_library_epoch_successor", swap_after_first,
    )
    with pytest.raises(ValueError):
        audit_mixed_library_epoch_receipt_chain(
            checkpoints, authorized=True,
        )
    assert seen >= 1


def test_checkpoint_duplicate_json_keys_rejected(capsys):
    bad = '{"receipt":"/missing.json","receipt":"/other.json"}'
    assert run_app_cli([
        "audit-mixed-library-epoch-receipts",
        "--checkpoint", bad,
        "--checkpoint", bad,
        "--trusted-local-operator",
    ]) == 2
    assert json.loads(capsys.readouterr().err)["status"] == "blocked"


def _private_checkpoint_file(path, payload):
    import os
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        stream.write(payload)
    return str(path)


def test_private_checkpoint_files_replay_real_game_history(
    catalog, tmp_path, capsys,
):
    """End-to-end CLI path: owner-private files -> pinned receipts -> replay."""
    checkpoints = _checkpoints(catalog, tmp_path)
    inline = _cli(checkpoints)
    files = [
        _private_checkpoint_file(
            tmp_path / f"operator-checkpoint-{index}.json", inline[position + 1],
        )
        for index, position in enumerate(range(1, len(inline) - 1, 2))
    ]
    args = ["audit-mixed-library-epoch-receipts"]
    for path in files:
        args += ["--checkpoint-file", path]
    args += ["--trusted-local-operator"]
    assert run_app_cli(args) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["checkpoint_count"] == 3
    assert result["all_pinned_receipts_reverified"] is True
    assert result["all_historical_games_reexecuted"] is True
    assert result["native_device_qualified"] is False
    assert result["release_certified"] is False


def test_private_checkpoint_files_reject_symlink_and_open_permissions(
    tmp_path, capsys,
):
    target = tmp_path / "private.json"
    _private_checkpoint_file(target, "{}")
    symlink = tmp_path / "alias.json"
    symlink.symlink_to(target)
    args = ["audit-mixed-library-epoch-receipts", "--checkpoint-file"]
    assert run_app_cli(
        args + [str(symlink), "--checkpoint-file", str(target),
                "--trusted-local-operator"]
    ) == 2
    assert json.loads(capsys.readouterr().err)["status"] == "blocked"
    os.chmod(target, 0o644)
    assert run_app_cli(
        args + [str(target), "--checkpoint-file", str(target) + "2",
                "--trusted-local-operator"]
    ) == 2
    assert json.loads(capsys.readouterr().err)["status"] == "blocked"


def test_private_checkpoint_file_rejects_same_byte_inode_replacement(
    tmp_path, monkeypatch,
):
    from skeleton.app import offline_mixed_library_epoch_receipt_chain as module
    source = tmp_path / "checkpoint.json"
    _private_checkpoint_file(source, "{}")
    original = module._read
    calls = 0

    def replace_after_first(*args, **kwargs):
        nonlocal calls
        data = original(*args, **kwargs)
        calls += 1
        if calls == 1:
            replacement = tmp_path / "replacement.json"
            _private_checkpoint_file(replacement, "{}")
            os.replace(replacement, source)
        return data

    monkeypatch.setattr(module, "_read", replace_after_first)
    with pytest.raises(ValueError):
        module._read_checkpoint_file(str(source))
    assert calls == 2


def test_checkpoint_file_cli_rejects_mixed_input_and_oversize(tmp_path, capsys):
    from skeleton.app.offline_mixed_library_epoch_receipt_chain import (
        MAX_CHECKPOINT_JSON_BYTES,
    )
    oversized = tmp_path / "oversized.json"
    _private_checkpoint_file(
        oversized, "x" * (MAX_CHECKPOINT_JSON_BYTES + 1),
    )
    base = ["audit-mixed-library-epoch-receipts"]
    assert run_app_cli(
        base + ["--checkpoint-file", str(oversized),
                "--checkpoint-file", str(oversized) + "2",
                "--trusted-local-operator"]
    ) == 2
    assert json.loads(capsys.readouterr().err)["status"] == "blocked"
    # argparse rejects conflicting input modes before invoking any verifier.
    with pytest.raises(SystemExit) as rejected:
        run_app_cli(
            base + ["--checkpoint", "{}",
                    "--checkpoint-file", str(oversized),
                    "--trusted-local-operator"]
        )
    assert rejected.value.code == 2


def test_checkpoint_file_cli_detects_same_byte_swap_during_replay(
    catalog, tmp_path, monkeypatch, capsys,
):
    from pathlib import Path
    from skeleton.app import offline_mixed_library_epoch_receipt_chain as module

    checkpoints = _checkpoints(catalog, tmp_path)
    inline = _cli(checkpoints)
    files = [
        _private_checkpoint_file(
            tmp_path / f"chain-swap-{index}.json", inline[position + 1],
        )
        for index, position in enumerate(range(1, len(inline) - 1, 2))
    ]
    original = module.audit_mixed_library_epoch_receipt_chain

    def swap_after_replay(*args, **kwargs):
        result = original(*args, **kwargs)
        target = Path(files[0])
        replacement = tmp_path / "chain-swap-replacement.json"
        _private_checkpoint_file(replacement, target.read_text())
        os.replace(replacement, target)
        return result

    monkeypatch.setattr(
        module, "audit_mixed_library_epoch_receipt_chain", swap_after_replay,
    )
    args = ["audit-mixed-library-epoch-receipts"]
    for file in files:
        args += ["--checkpoint-file", file]
    args += ["--trusted-local-operator"]
    assert run_app_cli(args) == 2
    assert json.loads(capsys.readouterr().err)["status"] == "blocked"
