"""Canonical app end-to-end historical receipt/live source reconciliation."""
from __future__ import annotations

from hashlib import sha256
import json

import pytest

from skeleton.app.cli import run_app_cli
from skeleton.app import studio_journey


def _build(tmp_path, capsys, project_id="first-game", seed=1729):
    source = tmp_path / (project_id + "-game")
    receipt = tmp_path / (project_id + "-receipt.json")
    result = run_app_cli([
        "studio-journey", "--onboard", "--project-id", project_id,
        "--title", "Original Beacon", "--seed", str(seed),
        "--output", str(source), "--receipt", str(receipt),
        "--trusted-local-operator",
    ])
    assert result == 0
    built = json.loads(capsys.readouterr().out)
    assert built["offline_gameplay_reexecuted"] is True
    return source, receipt, built


def _reconcile(source, receipt, built, *, authorized=True):
    return [
        "studio-journey", "--reconcile-receipt", "--output", str(source),
        "--receipt", str(receipt),
        "--expected-manifest-sha256", built["trusted_in_process_manifest_sha256"],
        "--expected-receipt-sha256", built["independent_receipt_sha256"],
        *(["--trusted-local-operator"] if authorized else []),
    ]


def test_live_source_is_replayed_and_bound_to_independently_pinned_receipt(tmp_path, capsys):
    source, receipt, built = _build(tmp_path, capsys)
    source_before = (source / "release.json").read_bytes()
    receipt_before = receipt.read_bytes()
    assert run_app_cli(_reconcile(source, receipt, built)) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["schema"] == studio_journey.RECONCILE_SCHEMA
    assert result["project_id"] == "first-game"
    assert result["receipt_source_binding_verified"] is True
    assert result["offline_gameplay_reexecuted"] is True
    assert result["release_certified"] is False
    assert result["native_device_qualified"] is False
    assert (source / "release.json").read_bytes() == source_before
    assert receipt.read_bytes() == receipt_before


def test_cross_game_receipt_rejected_even_when_both_receipts_are_valid(tmp_path, capsys):
    source, _, built = _build(tmp_path, capsys, "alpha", 1729)
    _, foreign_receipt, foreign = _build(tmp_path, capsys, "beta", 1729)
    args = _reconcile(source, foreign_receipt, built)
    args[args.index("--expected-receipt-sha256") + 1] = foreign["independent_receipt_sha256"]
    assert run_app_cli(args) == 2
    assert json.loads(capsys.readouterr().err)["status"] == "blocked"


def test_receipt_tampering_and_source_tampering_both_fail_closed(tmp_path, capsys):
    source, receipt, built = _build(tmp_path, capsys)
    receipt.write_bytes(receipt.read_bytes() + b" ")
    assert run_app_cli(_reconcile(source, receipt, built)) == 2
    assert json.loads(capsys.readouterr().err)["status"] == "blocked"
    receipt.write_bytes(receipt.read_bytes()[:-1])
    (source / "index.html").write_bytes(b"tampered browser game")
    assert run_app_cli(_reconcile(source, receipt, built)) == 2
    assert json.loads(capsys.readouterr().err)["status"] == "blocked"


def test_source_mutation_between_binding_and_final_replay_is_rejected(tmp_path, capsys, monkeypatch):
    source, receipt, built = _build(tmp_path, capsys)
    original = studio_journey.verify_exported_package
    calls = 0

    def mutate_after_first_replay(*args, **kwargs):
        nonlocal calls
        result = original(*args, **kwargs)
        calls += 1
        if calls == 1:
            (source / "index.html").write_bytes(b"replaced after historical binding")
        return result

    monkeypatch.setattr(studio_journey, "verify_exported_package", mutate_after_first_replay)
    assert run_app_cli(_reconcile(source, receipt, built)) == 2
    assert calls == 1  # second canonical verifier rejects modified source
    assert json.loads(capsys.readouterr().err)["status"] == "blocked"


@pytest.mark.parametrize("extra", [
    ["--onboard"], ["--verify-existing"], ["--inspect-receipt"],
    ["--intent", "foreign.json"], ["--project-id", "foreign"],
    ["--practice-games", "1"], ["--mirror-attempts", "65"],
])
def test_reconciliation_rejects_conflicting_modes_before_filesystem_access(
    tmp_path, capsys, extra,
):
    args = [
        "studio-journey", "--reconcile-receipt", "--output", str(tmp_path / "missing"),
        "--receipt", str(tmp_path / "missing.json"),
        "--expected-manifest-sha256", "a" * 64,
        "--expected-receipt-sha256", "b" * 64,
        "--trusted-local-operator", *extra,
    ]
    assert run_app_cli(args) == 2
    assert json.loads(capsys.readouterr().err)["status"] == "blocked"


def test_reconciliation_requires_authority_and_both_independent_pins(tmp_path, capsys):
    source, receipt, built = _build(tmp_path, capsys)
    assert run_app_cli(_reconcile(source, receipt, built, authorized=False)) == 2
    assert json.loads(capsys.readouterr().err)["status"] == "blocked"
    args = _reconcile(source, receipt, built)
    args[args.index("--expected-receipt-sha256") + 1] = "0" * 64
    assert run_app_cli(args) == 2
    assert json.loads(capsys.readouterr().err)["status"] == "blocked"


def test_reconciliation_rejects_symlinked_historical_receipt(tmp_path, capsys):
    source, receipt, built = _build(tmp_path, capsys)
    alias = tmp_path / "receipt-alias.json"
    alias.symlink_to(receipt)
    assert run_app_cli(_reconcile(source, alias, built)) == 2
    assert json.loads(capsys.readouterr().err)["status"] == "blocked"
