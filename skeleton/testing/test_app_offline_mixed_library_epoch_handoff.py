"""Durable private receipt handoff with full real game replay acceptance."""
from __future__ import annotations

from dataclasses import asdict, replace
import json
import os

import pytest

from skeleton.app.cli import run_app_cli
from skeleton.app.offline_mixed_library_epoch_handoff import (
    inspect_mixed_library_epoch_handoff, publish_mixed_library_epoch_handoff,
)
from skeleton.testing.test_app_offline_mixed_library_epoch_chain import (
    _epoch, catalog,
)
from skeleton.testing.test_app_offline_mixed_game_library_continuity import _advance

pytestmark = pytest.mark.skipif(os.name != "posix", reason="POSIX private custody")


def _args(epochs):
    result = ["mixed-library-epoch-handoff"]
    for epoch in epochs:
        result += [
            "--unsigned-generation", json.dumps([asdict(x) for x in epoch.unsigned]),
            "--signed-generation", json.dumps([asdict(x) for x in epoch.signed]),
        ]
    return result + ["--trusted-local-operator"]


def test_real_three_epoch_publish_and_independent_inspect(catalog, tmp_path, capsys):
    unsigned, signed = catalog
    u1 = _advance(unsigned, tmp_path / "handoff-epoch-u1.json")
    s2 = _advance(signed, tmp_path / "handoff-epoch-s2.json")
    epochs = (_epoch(unsigned, signed), _epoch(u1, signed), _epoch(u1, s2))
    target = tmp_path / "independent-epoch-handoff.json"
    assert run_app_cli(_args(epochs) + ["--output", str(target)]) == 0
    created = json.loads(capsys.readouterr().out)
    assert created["receipt_published"] is True
    assert created["generation_count"] == 3
    assert created["release_certified"] is False
    assert target.stat().st_mode & 0o077 == 0
    before = target.read_bytes()
    assert run_app_cli(_args(epochs) + [
        "--inspect-receipt", str(target),
        "--expected-receipt-sha256", created["receipt_sha256"],
    ]) == 0
    verified = json.loads(capsys.readouterr().out)
    assert verified["receipt_integrity_verified"] is True
    assert verified["all_transitions_reexecuted"] is True
    assert verified["signed_policy_history_reverified"] is True
    assert verified["native_device_qualified"] is False
    assert verified["epoch_chain_sha256"] == created["epoch_chain_sha256"]
    assert target.read_bytes() == before


def test_no_clobber_and_independent_pin_required(catalog, tmp_path):
    unsigned, signed = catalog
    u1 = _advance(unsigned, tmp_path / "handoff-u1.json")
    epochs = (_epoch(unsigned, signed), _epoch(u1, signed))
    target = tmp_path / "handoff.json"
    created = publish_mixed_library_epoch_handoff(
        epochs, target, authorized=True,
    )
    before = target.read_bytes()
    with pytest.raises(ValueError):
        publish_mixed_library_epoch_handoff(epochs, target, authorized=True)
    assert target.read_bytes() == before
    with pytest.raises(ValueError):
        inspect_mixed_library_epoch_handoff(
            epochs, target, expected_receipt_sha256="0" * 64,
            authorized=True,
        )
    assert inspect_mixed_library_epoch_handoff(
        epochs, target, expected_receipt_sha256=created["receipt_sha256"],
        authorized=True,
    )["receipt_integrity_verified"] is True


def test_replay_change_invalidates_pinned_handoff(catalog, tmp_path):
    unsigned, signed = catalog
    u1 = _advance(unsigned, tmp_path / "handoff-u2.json")
    epochs = (_epoch(unsigned, signed), _epoch(u1, signed))
    target = tmp_path / "handoff-change.json"
    receipt = publish_mixed_library_epoch_handoff(epochs, target, authorized=True)
    s1 = _advance(signed, tmp_path / "handoff-s1.json")
    altered = (_epoch(unsigned, signed), _epoch(u1, s1))
    with pytest.raises(ValueError):
        inspect_mixed_library_epoch_handoff(
            altered, target, expected_receipt_sha256=receipt["receipt_sha256"],
            authorized=True,
        )


def test_receipt_cannot_be_published_inside_source(catalog, tmp_path):
    unsigned, signed = catalog
    u1 = _advance(unsigned, tmp_path / "handoff-protected.json")
    epochs = (_epoch(unsigned, signed), _epoch(u1, signed))
    with pytest.raises(ValueError):
        publish_mixed_library_epoch_handoff(
            epochs, os.path.join(unsigned.installed_source, "receipt.json"),
            authorized=True,
        )


def test_operator_authorization_required(catalog, tmp_path):
    unsigned, signed = catalog
    epochs = (_epoch(unsigned, signed), _epoch(unsigned, signed))
    with pytest.raises(PermissionError):
        publish_mixed_library_epoch_handoff(
            epochs, tmp_path / "denied.json", authorized=False,
        )
    with pytest.raises(PermissionError):
        inspect_mixed_library_epoch_handoff(
            epochs, tmp_path / "missing.json",
            expected_receipt_sha256="0" * 64, authorized=False,
        )


def test_cli_rejects_missing_inspection_pin(capsys):
    assert run_app_cli([
        "mixed-library-epoch-handoff",
        "--unsigned-generation", "[]",
        "--unsigned-generation", "[]",
        "--signed-generation", "[]",
        "--signed-generation", "[]",
        "--inspect-receipt", "/nonexistent/receipt.json",
        "--trusted-local-operator",
    ]) == 2
    assert json.loads(capsys.readouterr().err)["status"] == "blocked"
