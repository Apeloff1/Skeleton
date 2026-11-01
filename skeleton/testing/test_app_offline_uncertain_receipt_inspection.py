"""End-to-end quarantine inspection of actual offline game handoff receipts."""
from __future__ import annotations

from hashlib import sha256
import json
import os

import pytest

from skeleton.app.cli import run_app_cli
from skeleton.app.offline_mixed_library_epoch_handoff import (
    publish_mixed_library_epoch_handoff,
)
from skeleton.app.offline_uncertain_receipt_inspection import (
    inspect_uncertain_receipt,
)
from skeleton.testing.test_app_offline_mixed_library_epoch_chain import (
    _epoch, catalog,
)
from skeleton.testing.test_app_offline_mixed_game_library_continuity import _advance

pytestmark = pytest.mark.skipif(os.name != "posix", reason="POSIX private custody")


def _setup(catalog, tmp_path):
    unsigned, signed = catalog
    later = _advance(unsigned, tmp_path / "triage-later.json")
    epochs = (_epoch(unsigned, signed), _epoch(later, signed))
    target = tmp_path / "triage-receipt.json"
    roots = (
        unsigned.installed_source, unsigned.archive, unsigned.private_save,
        signed.installed_source, signed.archive, signed.private_save,
        signed.public_key_file, signed.signature_file, *signed.policies,
    )
    return epochs, target, roots


def test_real_handoff_receipt_can_be_triaged_without_granting_replay(
    catalog, tmp_path, capsys,
):
    epochs, target, roots = _setup(catalog, tmp_path)
    published = publish_mixed_library_epoch_handoff(
        epochs, target, authorized=True,
    )
    original = target.read_bytes()
    command = [
        "inspect-uncertain-offline-receipt",
        "--receipt", str(target),
        "--expected-receipt-sha256", published["receipt_sha256"],
        "--trusted-local-operator",
    ]
    for root in roots:
        command += ["--protected-root", str(root)]
    assert run_app_cli(command) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["receipt_integrity_verified"] is True
    assert result["game_replay_reverified"] is False
    assert result["publication_durability_proven"] is False
    assert result["operator_quarantine_required"] is True
    assert result["release_certified"] is False
    assert target.read_bytes() == original


def test_triage_rejects_wrong_independent_pin(catalog, tmp_path):
    epochs, target, roots = _setup(catalog, tmp_path)
    publish_mixed_library_epoch_handoff(epochs, target, authorized=True)
    with pytest.raises(ValueError):
        inspect_uncertain_receipt(
            target, expected_receipt_sha256="0" * 64,
            protected_roots=roots, authorized=True,
        )


def test_triage_rejects_protected_source_alias(catalog, tmp_path):
    epochs, target, roots = _setup(catalog, tmp_path)
    with pytest.raises(ValueError):
        inspect_uncertain_receipt(
            roots[0], expected_receipt_sha256="0" * 64,
            protected_roots=roots, authorized=True,
        )


def test_triage_rejects_symlink_receipt(catalog, tmp_path):
    epochs, target, roots = _setup(catalog, tmp_path)
    published = publish_mixed_library_epoch_handoff(
        epochs, target, authorized=True,
    )
    alias = tmp_path / "receipt-alias.json"
    alias.symlink_to(target)
    with pytest.raises((OSError, ValueError)):
        inspect_uncertain_receipt(
            alias, expected_receipt_sha256=published["receipt_sha256"],
            protected_roots=roots, authorized=True,
        )


def test_triage_requires_authorization_and_roots(catalog, tmp_path):
    epochs, target, roots = _setup(catalog, tmp_path)
    with pytest.raises(PermissionError):
        inspect_uncertain_receipt(
            target, expected_receipt_sha256="0" * 64,
            protected_roots=roots, authorized=False,
        )
    with pytest.raises(ValueError):
        inspect_uncertain_receipt(
            target, expected_receipt_sha256="0" * 64,
            protected_roots=[], authorized=True,
        )


def test_cli_never_reports_success_without_pin_or_authorization(capsys):
    assert run_app_cli([
        "inspect-uncertain-offline-receipt",
        "--receipt", "/nonexistent/receipt.json",
        "--expected-receipt-sha256", "0" * 64,
        "--protected-root", "/nonexistent/game",
    ]) == 2
    assert json.loads(capsys.readouterr().err)["status"] == "blocked"
