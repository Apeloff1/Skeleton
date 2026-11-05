"""Real game checkpoint-chain publication and independent inspection acceptance."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from skeleton.app.cli import run_app_cli
from skeleton.app.offline_mixed_library_checkpoint_handoff import (
    inspect_mixed_library_checkpoint_handoff,
    publish_mixed_library_checkpoint_handoff,
)
from skeleton.testing.test_app_offline_mixed_library_epoch_receipt_chain import (
    _checkpoints, _cli, _private_checkpoint_file,
)
from skeleton.testing.test_app_offline_mixed_library_epoch_chain import catalog

pytestmark = pytest.mark.skipif(os.name != "posix", reason="POSIX private custody")


def _handoff_cli(checkpoints, *, output=None, inspect=None, pin=None):
    args = ["mixed-library-checkpoint-handoff"]
    inline = _cli(checkpoints)
    args += inline[1:-1]
    if output is not None:
        args += ["--output", str(output)]
    else:
        args += ["--inspect-receipt", str(inspect),
                 "--expected-receipt-sha256", pin]
    return args + ["--trusted-local-operator"]


def test_real_checkpoint_chain_handoff_publishes_and_replays(
    catalog, tmp_path, capsys,
):
    checkpoints = _checkpoints(catalog, tmp_path)
    target = tmp_path / "private-chain-handoff.json"
    assert run_app_cli(_handoff_cli(checkpoints, output=target)) == 0
    published = json.loads(capsys.readouterr().out)
    assert published["checkpoint_count"] == 3
    assert published["game_count"] == 2
    assert published["receipt_published"] is True
    assert published["native_device_qualified"] is False
    assert published["release_certified"] is False
    assert target.stat().st_mode & 0o077 == 0
    assert run_app_cli(_handoff_cli(
        checkpoints, inspect=target, pin=published["receipt_sha256"],
    )) == 0
    checked = json.loads(capsys.readouterr().out)
    assert checked["receipt_integrity_verified"] is True
    assert checked["all_historical_games_reexecuted"] is True
    assert checked["checkpoint_evidence_sha256"] == published["checkpoint_evidence_sha256"]
    assert checked["release_certified"] is False
    assert run_app_cli(_handoff_cli(checkpoints, output=target)) == 2
    assert json.loads(capsys.readouterr().err)["status"] == "blocked"


def test_handoff_tamper_and_independent_pin_rejected(catalog, tmp_path):
    checkpoints = _checkpoints(catalog, tmp_path)
    target = tmp_path / "handoff.json"
    published = publish_mixed_library_checkpoint_handoff(
        checkpoints, target, authorized=True,
    )
    with pytest.raises(ValueError):
        inspect_mixed_library_checkpoint_handoff(
            checkpoints, target, expected_receipt_sha256="0" * 64,
            authorized=True,
        )
    with open(target, "ab") as stream:
        stream.write(b" ")
    with pytest.raises(ValueError):
        inspect_mixed_library_checkpoint_handoff(
            checkpoints, target,
            expected_receipt_sha256=published["receipt_sha256"],
            authorized=True,
        )


def test_handoff_rejects_protected_historical_receipt_destination(
    catalog, tmp_path,
):
    checkpoints = _checkpoints(catalog, tmp_path)
    original = Path(checkpoints[0].receipt).read_bytes()
    with pytest.raises(ValueError):
        publish_mixed_library_checkpoint_handoff(
            checkpoints, checkpoints[0].receipt, authorized=True,
        )
    assert Path(checkpoints[0].receipt).read_bytes() == original


def test_handoff_rejects_same_byte_historical_receipt_swap(
    catalog, tmp_path, monkeypatch,
):
    from skeleton.app import offline_mixed_library_checkpoint_handoff as module

    checkpoints = _checkpoints(catalog, tmp_path)
    original = module.audit_mixed_library_epoch_receipt_chain
    calls = 0

    def swap_on_first(*args, **kwargs):
        nonlocal calls
        result = original(*args, **kwargs)
        calls += 1
        if calls == 1:
            target = Path(checkpoints[1].receipt)
            replacement = tmp_path / "replacement-historical.json"
            _private_checkpoint_file(replacement, target.read_text())
            os.replace(replacement, target)
        return result

    monkeypatch.setattr(module, "audit_mixed_library_epoch_receipt_chain", swap_on_first)
    with pytest.raises(ValueError):
        module.publish_mixed_library_checkpoint_handoff(
            checkpoints, tmp_path / "blocked-handoff.json", authorized=True,
        )
    assert not (tmp_path / "blocked-handoff.json").exists()


def test_checkpoint_handoff_file_cli_requires_private_inputs(
    catalog, tmp_path, capsys,
):
    checkpoints = _checkpoints(catalog, tmp_path)
    inline = _cli(checkpoints)
    files = [
        _private_checkpoint_file(
            tmp_path / f"handoff-checkpoint-{index}.json", inline[position + 1],
        )
        for index, position in enumerate(range(1, len(inline) - 1, 2))
    ]
    args = ["mixed-library-checkpoint-handoff"]
    for file in files:
        args += ["--checkpoint-file", file]
    args += ["--output", str(tmp_path / "private-handoff.json"),
             "--trusted-local-operator"]
    assert run_app_cli(args) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["receipt_published"] is True
    assert result["release_certified"] is False


def test_handoff_cli_detects_checkpoint_file_swap_during_publication(
    catalog, tmp_path, monkeypatch, capsys,
):
    from skeleton.app import offline_mixed_library_checkpoint_handoff as module

    checkpoints = _checkpoints(catalog, tmp_path)
    inline = _cli(checkpoints)
    files = [
        _private_checkpoint_file(
            tmp_path / f"swap-checkpoint-{index}.json", inline[position + 1],
        )
        for index, position in enumerate(range(1, len(inline) - 1, 2))
    ]
    original = module.publish_mixed_library_checkpoint_handoff

    def swap_after_publication(*args, **kwargs):
        result = original(*args, **kwargs)
        target = Path(files[1])
        replacement = tmp_path / "replacement-input.json"
        _private_checkpoint_file(replacement, target.read_text())
        os.replace(replacement, target)
        return result

    monkeypatch.setattr(
        module, "publish_mixed_library_checkpoint_handoff",
        swap_after_publication,
    )
    args = ["mixed-library-checkpoint-handoff"]
    for file in files:
        args += ["--checkpoint-file", file]
    args += ["--output", str(tmp_path / "uncertain-handoff.json"),
             "--trusted-local-operator"]
    assert run_app_cli(args) == 2
    assert json.loads(capsys.readouterr().err)["status"] == "blocked"
    # A post-publication failure is an uncertain receipt requiring quarantine;
    # never delete or silently reissue it.
    assert (tmp_path / "uncertain-handoff.json").exists()
