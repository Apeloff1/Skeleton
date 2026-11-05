"""Durable mixed original-game handoff with live signed replay reinspection."""
from __future__ import annotations

from dataclasses import asdict
import json
import os

import pytest

from skeleton.app.cli import run_app_cli
from skeleton.app.offline_mixed_game_library_handoff import (
    OfflineMixedGameLibraryHandoffError,
    inspect_mixed_game_library_handoff,
    publish_mixed_game_library_handoff,
)
from skeleton.testing.test_app_offline_game_library_audit import (
    _independent_installed_game,
)
from skeleton.testing.test_app_offline_signed_game_library_audit import (
    _entry as _signed_entry,
)
from skeleton.testing.test_app_offline_policy_chain_delivery import chain_delivery

pytestmark = pytest.mark.skipif(os.name != "posix", reason="POSIX custody")


@pytest.fixture
def catalog(chain_delivery, tmp_path, capsys):
    unsigned = _independent_installed_game(
        tmp_path, capsys, "mixed-handoff-original-unsigned", 927,
    )
    signed = _signed_entry(chain_delivery)
    destination = tmp_path / "mixed-game-handoff.json"
    return unsigned, signed, destination


def _args(catalog):
    unsigned, signed, _ = catalog
    return [
        "mixed-library-handoff",
        "--unsigned-entry", json.dumps(asdict(unsigned)),
        "--signed-entry", json.dumps(asdict(signed)),
        "--trusted-local-operator",
    ]


def test_real_signed_and_unsigned_handoff_publish_and_inspect(
    catalog, capsys,
):
    unsigned, signed, destination = catalog
    source_before = (
        open(unsigned.archive, "rb").read(),
        open(unsigned.private_save, "rb").read(),
        open(signed.archive, "rb").read(),
        open(signed.private_save, "rb").read(),
    )
    assert run_app_cli(_args(catalog) + ["--output", str(destination)]) == 0
    published = json.loads(capsys.readouterr().out)
    assert published["receipt_published"] is True
    assert published["game_count"] == 2
    assert published["release_certified"] is False
    assert destination.is_file()
    assert destination.stat().st_mode & 0o077 == 0
    assert run_app_cli(_args(catalog) + [
        "--inspect-receipt", str(destination),
        "--expected-receipt-sha256", published["receipt_sha256"],
    ]) == 0
    inspected = json.loads(capsys.readouterr().out)
    assert inspected["receipt_integrity_verified"] is True
    assert inspected["live_original_gameplay_reexecuted"] is True
    assert inspected["source_signer_history_reverified"] is True
    assert inspected["library_receipt_sha256"] == published["library_receipt_sha256"]
    assert inspected["release_certified"] is False
    assert source_before == (
        open(unsigned.archive, "rb").read(),
        open(unsigned.private_save, "rb").read(),
        open(signed.archive, "rb").read(),
        open(signed.private_save, "rb").read(),
    )


def test_receipt_destination_never_overwritten(catalog):
    unsigned, signed, destination = catalog
    destination.write_text("existing", encoding="utf-8")
    with pytest.raises((OSError, ValueError)):
        publish_mixed_game_library_handoff(
            [unsigned], [signed], destination, authorized=True,
        )
    assert destination.read_text(encoding="utf-8") == "existing"


def test_receipt_cannot_be_written_inside_game_source(catalog):
    unsigned, signed, _ = catalog
    destination = os.path.join(unsigned.installed_source, "unsafe-handoff.json")
    with pytest.raises((OSError, ValueError)):
        publish_mixed_game_library_handoff(
            [unsigned], [signed], destination, authorized=True,
        )
    assert not os.path.exists(destination)


def test_receipt_pin_required_for_read_only_inspection(catalog):
    unsigned, signed, destination = catalog
    published = publish_mixed_game_library_handoff(
        [unsigned], [signed], destination, authorized=True,
    )
    with pytest.raises((OSError, ValueError, TypeError)):
        inspect_mixed_game_library_handoff(
            [unsigned], [signed], destination,
            expected_receipt_sha256="0" * 64, authorized=True,
        )
    assert published["receipt_published"] is True


def test_signed_policy_downgrade_blocks_existing_handoff(catalog):
    unsigned, signed, destination = catalog
    published = publish_mixed_game_library_handoff(
        [unsigned], [signed], destination, authorized=True,
    )
    from dataclasses import replace
    with pytest.raises((OSError, ValueError)):
        inspect_mixed_game_library_handoff(
            [unsigned], [replace(signed, expected_policy_sha256=(
                *signed.expected_policy_sha256[:-1], "0" * 64,
            ))], destination,
            expected_receipt_sha256=published["receipt_sha256"], authorized=True,
        )


def test_same_byte_receipt_inode_swap_during_inspection_rejected(
    catalog, tmp_path, monkeypatch,
):
    unsigned, signed, destination = catalog
    published = publish_mixed_game_library_handoff(
        [unsigned], [signed], destination, authorized=True,
    )
    import skeleton.app.offline_mixed_game_library_handoff as module
    original = module.audit_mixed_game_library

    def replace(*args, **kwargs):
        result = original(*args, **kwargs)
        replacement = tmp_path / "same-bytes-handoff.json"
        replacement.write_bytes(destination.read_bytes())
        replacement.chmod(0o600)
        os.replace(replacement, destination)
        return result

    monkeypatch.setattr(module, "audit_mixed_game_library", replace)
    with pytest.raises((OSError, ValueError)):
        inspect_mixed_game_library_handoff(
            [unsigned], [signed], destination,
            expected_receipt_sha256=published["receipt_sha256"], authorized=True,
        )


def test_mutation_before_publication_blocks_no_clobber_write(
    catalog, monkeypatch,
):
    unsigned, signed, destination = catalog
    import skeleton.app.offline_mixed_game_library_handoff as module
    original = module.audit_mixed_game_library
    calls = 0

    def change(*args, **kwargs):
        nonlocal calls
        result = original(*args, **kwargs)
        calls += 1
        if calls == 1:
            with open(unsigned.archive, "ab") as stream:
                stream.write(b"tampered")
        return result

    monkeypatch.setattr(module, "audit_mixed_game_library", change)
    with pytest.raises((OSError, ValueError)):
        publish_mixed_game_library_handoff(
            [unsigned], [signed], destination, authorized=True,
        )
    assert not destination.exists()


def test_operator_authority_precedes_any_game_read(catalog, monkeypatch):
    unsigned, signed, destination = catalog
    import skeleton.app.offline_mixed_game_library_handoff as module
    monkeypatch.setattr(
        module, "_snapshot",
        lambda *_: pytest.fail("unauthorized game read"),
    )
    with pytest.raises(PermissionError):
        publish_mixed_game_library_handoff(
            [unsigned], [signed], destination, authorized=False,
        )


def test_cli_missing_authority_returns_blocked_json(catalog, capsys):
    argv = _args(catalog)
    argv.remove("--trusted-local-operator")
    assert run_app_cli(argv + ["--output", str(catalog[-1])]) == 2
    assert json.loads(capsys.readouterr().err)["status"] == "blocked"


def test_inspection_does_not_accept_source_save_as_receipt(catalog):
    unsigned, signed, _ = catalog
    with pytest.raises(OfflineMixedGameLibraryHandoffError, match="protected"):
        inspect_mixed_game_library_handoff(
            [unsigned], [signed], unsigned.private_save,
            expected_receipt_sha256=unsigned.expected_save_sha256,
            authorized=True,
        )
