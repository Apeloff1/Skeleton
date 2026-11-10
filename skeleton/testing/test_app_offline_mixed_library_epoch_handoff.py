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
from skeleton.testing.test_app_offline_mixed_game_library_continuity import chain_delivery  # noqa: F401  (transitive fixture)
from skeleton.testing.test_app_offline_policy_chain_delivery import delivered  # noqa: F401  (transitive fixture)
from skeleton.testing.test_app_offline_policy_signed_delivery import policy_migration  # noqa: F401  (transitive fixture)
from skeleton.testing.test_app_offline_policy_signed_progress_migration import migration  # noqa: F401  (transitive fixture)
from skeleton.testing.test_app_offline_signed_progress_migration import signed  # noqa: F401  (transitive fixture)

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


def test_real_epoch_handoff_post_link_failure_is_recoverable(
    catalog, tmp_path, monkeypatch,
):
    """An observable published receipt is never silently removed on EIO."""
    import errno
    import stat
    from hashlib import sha256

    from skeleton.ai.game_builder import offline_receipt_publication as publication
    from skeleton.ai.game_builder.dual_runtime_verify import _canonical_bytes
    from skeleton.app.offline_mixed_library_epoch_chain import (
        assure_mixed_library_epoch_chain,
    )
    from skeleton.app.offline_mixed_library_epoch_handoff import _envelope

    unsigned, signed = catalog
    u1 = _advance(unsigned, tmp_path / "uncertain-handoff-u1.json")
    epochs = (_epoch(unsigned, signed), _epoch(u1, signed))
    target = tmp_path / "uncertain-epoch-handoff.json"

    # Compute the expected pin from a separately replayed source chain,
    # not by trusting bytes discovered in the failed publication destination.
    chain = assure_mixed_library_epoch_chain(epochs, authorized=True)
    expected = sha256(_canonical_bytes(_envelope(chain))).hexdigest()
    original_fsync = os.fsync
    failures = 0

    def fail_first_parent_fsync(fd):
        nonlocal failures
        if stat.S_ISDIR(os.fstat(fd).st_mode) and failures == 0:
            failures += 1
            raise OSError(errno.EIO, "simulated post-link durability uncertainty")
        return original_fsync(fd)

    with monkeypatch.context() as patch:
        patch.setattr(publication.os, "fsync", fail_first_parent_fsync)
        with pytest.raises(publication.ReceiptPublicationError):
            publish_mixed_library_epoch_handoff(epochs, target, authorized=True)

    assert failures == 1
    assert target.exists()
    assert sha256(target.read_bytes()).hexdigest() == expected
    assert target.stat().st_mode & 0o077 == 0
    assert not list(tmp_path.glob(".receipt-*"))
    # The independent verifier must reexecute the actual original game
    # histories and signer policies, not merely accept the saved JSON.
    verified = inspect_mixed_library_epoch_handoff(
        epochs, target, expected_receipt_sha256=expected, authorized=True,
    )
    assert verified["receipt_integrity_verified"] is True
    assert verified["all_transitions_reexecuted"] is True
    assert verified["release_certified"] is False
    with pytest.raises(ValueError):
        publish_mixed_library_epoch_handoff(epochs, target, authorized=True)
    assert sha256(target.read_bytes()).hexdigest() == expected


def test_real_epoch_handoff_recovery_rejects_modified_game_after_uncertainty(
    catalog, tmp_path, monkeypatch,
):
    """A published but uncertain receipt never grants authority after rollback."""
    import errno
    import stat
    from hashlib import sha256

    from skeleton.ai.game_builder import offline_receipt_publication as publication
    from skeleton.ai.game_builder.dual_runtime_verify import _canonical_bytes
    from skeleton.app.offline_mixed_library_epoch_chain import (
        assure_mixed_library_epoch_chain,
    )
    from skeleton.app.offline_mixed_library_epoch_handoff import _envelope

    unsigned, signed = catalog
    u1 = _advance(unsigned, tmp_path / "rollback-handoff-u1.json")
    epochs = (_epoch(unsigned, signed), _epoch(u1, signed))
    target = tmp_path / "rollback-handoff.json"
    expected = sha256(_canonical_bytes(_envelope(
        assure_mixed_library_epoch_chain(epochs, authorized=True),
    ))).hexdigest()
    original_fsync = os.fsync
    failures = 0

    def fail_parent_once(fd):
        nonlocal failures
        if stat.S_ISDIR(os.fstat(fd).st_mode) and failures == 0:
            failures += 1
            raise OSError(errno.EIO, "simulated post-publication EIO")
        return original_fsync(fd)

    with monkeypatch.context() as patch:
        patch.setattr(publication.os, "fsync", fail_parent_once)
        with pytest.raises(publication.ReceiptPublicationError):
            publish_mixed_library_epoch_handoff(epochs, target, authorized=True)
    assert failures == 1
    assert target.exists()

    # Replacing the latest save with the old independently valid save is a
    # rollback even though the receipt file itself remains unmodified.
    reverted = (
        epochs[0],
        _epoch(unsigned, signed),
    )
    with pytest.raises(ValueError):
        inspect_mixed_library_epoch_handoff(
            reverted, target, expected_receipt_sha256=expected, authorized=True,
        )
    assert target.exists()
    assert sha256(target.read_bytes()).hexdigest() == expected
