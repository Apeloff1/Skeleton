"""Real mixed-catalog acceptance from independently generated original games."""
from __future__ import annotations

from dataclasses import asdict
import json
import os

import pytest

from skeleton.app.cli import run_app_cli
from skeleton.app.offline_game_library_audit import OfflineGameLibraryEntry
from skeleton.app.offline_mixed_game_library_audit import (
    OfflineMixedGameLibraryError, audit_mixed_game_library,
)
from skeleton.testing.test_app_offline_game_library_audit import (
    _independent_installed_game,
)
from skeleton.testing.test_app_offline_signed_game_library_audit import (
    _entry as _signed_entry,
)
from skeleton.testing.test_app_offline_policy_chain_delivery import chain_delivery
from skeleton.testing.test_app_offline_policy_chain_delivery import delivered  # noqa: F401  (transitive fixture)
from skeleton.testing.test_app_offline_policy_signed_delivery import policy_migration  # noqa: F401  (transitive fixture)
from skeleton.testing.test_app_offline_policy_signed_progress_migration import migration  # noqa: F401  (transitive fixture)
from skeleton.testing.test_app_offline_signed_progress_migration import signed  # noqa: F401  (transitive fixture)

pytestmark = pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor custody")


@pytest.fixture
def mixed(chain_delivery, tmp_path, capsys):
    unsigned = _independent_installed_game(
        tmp_path, capsys, "mixed-library-unsigned-original", 874,
    )
    signed = _signed_entry(chain_delivery)
    return unsigned, signed


def _command(unsigned, signed):
    return [
        "audit-mixed-game-library",
        "--unsigned-entry", json.dumps(asdict(unsigned)),
        "--signed-entry", json.dumps(asdict(signed)),
        "--trusted-local-operator",
    ]


def test_real_original_unsigned_and_ed25519_signed_games_replay(mixed, capsys):
    unsigned, signed = mixed
    before = (
        open(unsigned.archive, "rb").read(),
        open(unsigned.private_save, "rb").read(),
        open(signed.archive, "rb").read(),
        open(signed.private_save, "rb").read(),
    )
    assert run_app_cli(_command(unsigned, signed)) == 0
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["game_count"] == 2
    assert receipt["unsigned_game_count"] == 1
    assert receipt["source_signed_game_count"] == 1
    assert receipt["all_gameplay_and_private_progress_replayed"] is True
    assert receipt["signed_sources_independently_verified"] is True
    assert receipt["unsigned_sources_explicitly_disclosed"] is True
    assert receipt["cross_mode_custody_unchanged"] is True
    assert receipt["native_device_qualified"] is False
    assert receipt["package_signed"] is False
    assert receipt["release_certified"] is False
    assert {item["source_signed"] for item in receipt["games"]} == {True, False}
    assert all(item["release_certified"] is False for item in receipt["games"])
    assert before == (
        open(unsigned.archive, "rb").read(),
        open(unsigned.private_save, "rb").read(),
        open(signed.archive, "rb").read(),
        open(signed.private_save, "rb").read(),
    )


def test_independent_pins_and_signed_history_are_required(mixed):
    unsigned, signed = mixed
    from dataclasses import replace
    with pytest.raises((OSError, ValueError)):
        audit_mixed_game_library(
            [replace(unsigned, expected_save_sha256="0" * 64)],
            [signed], authorized=True,
        )
    with pytest.raises((OSError, ValueError)):
        audit_mixed_game_library(
            [unsigned],
            [replace(signed, expected_policy_sha256=(
                *signed.expected_policy_sha256[:-1], "0" * 64,
            ))], authorized=True,
        )


def test_cross_mode_path_alias_rejected_before_audit(mixed, monkeypatch):
    unsigned, signed = mixed
    import skeleton.app.offline_mixed_game_library_audit as module
    monkeypatch.setattr(
        module, "audit_offline_game_library",
        lambda *_a, **_k: pytest.fail("alias accessed during verification"),
    )
    from dataclasses import replace
    with pytest.raises(OfflineMixedGameLibraryError, match="path alias"):
        audit_mixed_game_library(
            [replace(unsigned, archive=signed.archive)],
            [signed], authorized=True,
        )


def test_cross_mode_inode_alias_rejected_even_for_different_names(
    mixed, monkeypatch,
):
    unsigned, signed = mixed
    import skeleton.app.offline_mixed_game_library_audit as module
    original = module._snapshot

    def fake_alias(*args):
        plain, trusted = original(*args)
        replacement = list(trusted)
        member = list(replacement[0])
        member[0] = plain[0][0]
        replacement[0] = tuple(member)
        return plain, tuple(replacement)

    monkeypatch.setattr(module, "_snapshot", fake_alias)
    with pytest.raises(OfflineMixedGameLibraryError, match="inode alias"):
        audit_mixed_game_library([unsigned], [signed], authorized=True)


def test_cross_mode_policy_inode_alias_rejected(mixed, monkeypatch):
    unsigned, signed = mixed
    import skeleton.app.offline_mixed_game_library_audit as module
    original = module._snapshot

    def fake_alias(*args):
        plain, trusted = original(*args)
        first = list(plain[0])
        # A policy is nested under the signed material identity. An alias
        # against an unsigned archive must not disappear during flattening.
        first[1] = trusted[0][5][0][1]
        return (tuple(first),), trusted

    monkeypatch.setattr(module, "_snapshot", fake_alias)
    with pytest.raises(OfflineMixedGameLibraryError, match="inode alias"):
        audit_mixed_game_library([unsigned], [signed], authorized=True)


def test_unauthorized_audit_never_reads_any_game(mixed, monkeypatch):
    unsigned, signed = mixed
    import skeleton.app.offline_mixed_game_library_audit as module
    monkeypatch.setattr(
        module, "_snapshot",
        lambda *_a: pytest.fail("unauthorized custody access"),
    )
    with pytest.raises(PermissionError):
        audit_mixed_game_library([unsigned], [signed], authorized=False)


def test_missing_cli_authority_returns_blocked_json(mixed, capsys):
    argv = _command(*mixed)
    argv.remove("--trusted-local-operator")
    assert run_app_cli(argv) == 2
    receipt = json.loads(capsys.readouterr().err)
    assert receipt["status"] == "blocked"
    assert receipt["release_certified"] is False


def test_bad_entry_json_rejected_without_success_receipt(mixed, capsys):
    argv = _command(*mixed)
    argv[2] = '{"archive":"x","archive":"y"}'
    assert run_app_cli(argv) == 2
    assert json.loads(capsys.readouterr().err)["status"] == "blocked"


def test_oversized_catalog_rejected_before_read(mixed, monkeypatch):
    unsigned, signed = mixed
    import skeleton.app.offline_mixed_game_library_audit as module
    monkeypatch.setattr(
        module, "_snapshot",
        lambda *_a: pytest.fail("over-budget inventory accessed"),
    )
    with pytest.raises(OfflineMixedGameLibraryError, match="both custody"):
        audit_mixed_game_library([unsigned] * 8, [signed], authorized=True)


def test_same_byte_archive_inode_swap_between_planes_rejected(
    mixed, tmp_path, monkeypatch,
):
    unsigned, signed = mixed
    import skeleton.app.offline_mixed_game_library_audit as module
    original = module.audit_signed_game_library
    calls = 0

    def substitute(*args, **kwargs):
        nonlocal calls
        receipt = original(*args, **kwargs)
        calls += 1
        if calls == 1:
            replacement = tmp_path / "mixed-identical-archive.zip"
            with open(unsigned.archive, "rb") as src:
                replacement.write_bytes(src.read())
            replacement.chmod(0o600)
            os.replace(replacement, unsigned.archive)
        return receipt

    monkeypatch.setattr(module, "audit_signed_game_library", substitute)
    with pytest.raises(OfflineMixedGameLibraryError, match="custody changed"):
        audit_mixed_game_library([unsigned], [signed], authorized=True)


def test_replayed_project_collision_rejected(mixed, monkeypatch):
    unsigned, signed = mixed
    import skeleton.app.offline_mixed_game_library_audit as module
    original = module.audit_signed_game_library
    first_plain = module.audit_offline_game_library([unsigned], authorized=True)
    project_id = first_plain["games"][0]["project_id"]

    def collision(*args, **kwargs):
        result = original(*args, **kwargs)
        return {**result, "games": [
            {**item, "project_id": project_id} for item in result["games"]
        ]}

    monkeypatch.setattr(module, "audit_signed_game_library", collision)
    with pytest.raises(OfflineMixedGameLibraryError, match="both catalogs"):
        audit_mixed_game_library([unsigned], [signed], authorized=True)


def test_audit_receipt_is_order_independent_for_each_plane(mixed):
    unsigned, signed = mixed
    first = audit_mixed_game_library([unsigned], [signed], authorized=True)
    second = audit_mixed_game_library((unsigned,), (signed,), authorized=True)
    assert first == second
    assert len(first["library_receipt_sha256"]) == 64
    assert all("private_save" not in item for item in first["games"])
