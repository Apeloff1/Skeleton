"""End-to-end successor acceptance: two private receipts and real replay."""
from __future__ import annotations

from dataclasses import asdict, replace
import json
import os

import pytest

from skeleton.app.cli import run_app_cli
from skeleton.app.offline_mixed_library_epoch_handoff import (
    publish_mixed_library_epoch_handoff,
)
from skeleton.app.offline_mixed_library_epoch_successor import (
    assure_mixed_library_epoch_successor,
)
from skeleton.testing.test_app_offline_mixed_library_epoch_chain import (
    _epoch, catalog,
)
from skeleton.testing.test_app_offline_mixed_game_library_continuity import _advance

pytestmark = pytest.mark.skipif(os.name != "posix", reason="POSIX private custody")


def _histories(catalog, tmp_path):
    unsigned, signed = catalog
    u1 = _advance(unsigned, tmp_path / "successor-u1.json")
    s2 = _advance(signed, tmp_path / "successor-s2.json")
    previous = (_epoch(unsigned, signed), _epoch(u1, signed))
    current = previous + (_epoch(u1, s2),)
    return previous, current


def _publish(previous, current, tmp_path):
    old = tmp_path / "previous-handoff.json"
    new = tmp_path / "current-handoff.json"
    a = publish_mixed_library_epoch_handoff(previous, old, authorized=True)
    b = publish_mixed_library_epoch_handoff(current, new, authorized=True)
    return old, new, a["receipt_sha256"], b["receipt_sha256"]


def _verify(previous, current, old, new, old_pin, new_pin):
    return assure_mixed_library_epoch_successor(
        previous, current, old, new,
        previous_sha256=old_pin, current_sha256=new_pin,
        authorized=True,
    )


def _cli(previous, current, old, new, old_pin, new_pin):
    args = ["audit-mixed-library-epoch-successor"]
    for prefix, epochs in (("previous", previous), ("current", current)):
        for epoch in epochs:
            args += [
                "--" + prefix + "-unsigned-generation",
                json.dumps([asdict(x) for x in epoch.unsigned]),
                "--" + prefix + "-signed-generation",
                json.dumps([asdict(x) for x in epoch.signed]),
            ]
    return args + [
        "--previous-receipt", str(old), "--current-receipt", str(new),
        "--previous-receipt-sha256", old_pin,
        "--current-receipt-sha256", new_pin,
        "--trusted-local-operator",
    ]


def test_real_signed_unsigned_successor_cli_and_read_only(
    catalog, tmp_path, capsys,
):
    previous, current = _histories(catalog, tmp_path)
    old, new, old_pin, new_pin = _publish(previous, current, tmp_path)
    old_bytes, new_bytes = old.read_bytes(), new.read_bytes()
    assert run_app_cli(_cli(
        previous, current, old, new, old_pin, new_pin,
    )) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["previous_generation_count"] == 2
    assert result["current_generation_count"] == 3
    assert result["game_count"] == 2
    assert result["both_receipts_independently_pinned"] is True
    assert result["both_complete_histories_reexecuted"] is True
    assert result["historical_replay_prefix_preserved"] is True
    assert result["new_generation_advanced"] is True
    assert result["persistent_rollback_protection"] is False
    assert result["native_device_qualified"] is False
    assert result["release_certified"] is False
    assert old.read_bytes() == old_bytes
    assert new.read_bytes() == new_bytes
    assert result == _verify(
        previous, current, old, new, old_pin, new_pin,
    )


def test_rejects_missing_authorization(catalog, tmp_path):
    previous, current = _histories(catalog, tmp_path)
    old, new, old_pin, new_pin = _publish(previous, current, tmp_path)
    with pytest.raises(PermissionError):
        assure_mixed_library_epoch_successor(
            previous, current, old, new,
            previous_sha256=old_pin, current_sha256=new_pin,
            authorized=False,
        )


def test_rejects_forked_historical_prefix(catalog, tmp_path):
    previous, current = _histories(catalog, tmp_path)
    old, new, old_pin, new_pin = _publish(previous, current, tmp_path)
    unsigned = current[0].unsigned[0]
    bad = replace(unsigned, expected_save_sha256="0" * 64)
    forked = (_epoch(bad, current[0].signed[0]), *current[1:])
    with pytest.raises(ValueError):
        _verify(previous, forked, old, new, old_pin, new_pin)


def test_rejects_tampered_receipt_and_bad_pin(catalog, tmp_path):
    previous, current = _histories(catalog, tmp_path)
    old, new, old_pin, new_pin = _publish(previous, current, tmp_path)
    with pytest.raises(ValueError):
        _verify(previous, current, old, new, old_pin, "0" * 64)
    with pytest.raises(ValueError):
        _verify(previous, current, old, new, old_pin, new_pin.upper())
    new.write_bytes(new.read_bytes() + b" ")
    with pytest.raises(ValueError):
        _verify(previous, current, old, new, old_pin, new_pin)


def test_rejects_same_receipt_inode_and_protected_root(catalog, tmp_path):
    previous, current = _histories(catalog, tmp_path)
    old, new, old_pin, new_pin = _publish(previous, current, tmp_path)
    alias = tmp_path / "receipt-alias.json"
    os.link(old, alias)
    with pytest.raises(ValueError):
        _verify(previous, current, old, alias, old_pin, new_pin)
    with pytest.raises(ValueError):
        _verify(
            previous, current, current[0].unsigned[0].private_save,
            new, old_pin, new_pin,
        )


def test_rejects_rollback_to_old_generation(catalog, tmp_path):
    previous, current = _histories(catalog, tmp_path)
    old, new, old_pin, new_pin = _publish(previous, current, tmp_path)
    with pytest.raises(ValueError):
        _verify(previous, previous, old, new, old_pin, new_pin)
    reverted = previous + (previous[-1],)
    with pytest.raises(ValueError):
        _verify(previous, reverted, old, new, old_pin, new_pin)


def test_cli_fails_closed_without_pin(capsys):
    assert run_app_cli([
        "audit-mixed-library-epoch-successor",
        "--previous-unsigned-generation", "[]",
        "--previous-signed-generation", "[]",
        "--current-unsigned-generation", "[]",
        "--current-signed-generation", "[]",
        "--previous-receipt", "/missing/previous.json",
        "--current-receipt", "/missing/current.json",
        "--previous-receipt-sha256", "0" * 64,
        "--trusted-local-operator",
    ]) == 2



def test_same_byte_receipt_inode_swap_during_replay_rejected(
    catalog, tmp_path, monkeypatch,
):
    """Replacing a receipt with byte-identical content must still fail."""
    from skeleton.app import offline_mixed_library_epoch_successor as module

    previous, current = _histories(catalog, tmp_path)
    old, new, old_pin, new_pin = _publish(previous, current, tmp_path)
    original = module.inspect_mixed_library_epoch_handoff
    seen = 0

    def replace_after_inspection(*args, **kwargs):
        nonlocal seen
        result = original(*args, **kwargs)
        seen += 1
        if seen == 2:
            replacement = tmp_path / "receipt-swap.json"
            replacement.write_bytes(new.read_bytes())
            os.chmod(replacement, 0o600)
            os.replace(replacement, new)
        return result

    monkeypatch.setattr(
        module, "inspect_mixed_library_epoch_handoff",
        replace_after_inspection,
    )
    with pytest.raises(ValueError):
        _verify(previous, current, old, new, old_pin, new_pin)
    assert seen == 2


def test_cli_rejects_unpaired_historical_generations(capsys):
    assert run_app_cli([
        "audit-mixed-library-epoch-successor",
        "--previous-unsigned-generation", "[]",
        "--previous-unsigned-generation", "[]",
        "--previous-signed-generation", "[]",
        "--current-unsigned-generation", "[]",
        "--current-unsigned-generation", "[]",
        "--current-unsigned-generation", "[]",
        "--current-signed-generation", "[]",
        "--current-signed-generation", "[]",
        "--current-signed-generation", "[]",
        "--previous-receipt", "/missing/old.json",
        "--current-receipt", "/missing/new.json",
        "--previous-receipt-sha256", "0" * 64,
        "--current-receipt-sha256", "1" * 64,
        "--trusted-local-operator",
    ]) == 2
    assert json.loads(capsys.readouterr().err)["release_certified"] is False
