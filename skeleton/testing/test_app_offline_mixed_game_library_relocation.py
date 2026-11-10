"""Real signed/unsigned original-game relocation and replay continuity."""
from __future__ import annotations

from dataclasses import asdict, replace
import json
import os

import pytest

from skeleton.app.cli import run_app_cli
from skeleton.app.offline_mixed_game_library_relocation import (
    OfflineMixedGameLibraryRelocationError,
    assure_mixed_game_library_relocation,
)
from skeleton.testing.test_app_offline_game_library_audit import (
    _independent_installed_game,
)
from skeleton.testing.test_app_offline_signed_game_library_relocation import (
    _pair as _signed_pair,
)
from skeleton.testing.test_app_offline_policy_chain_delivery import chain_delivery
from skeleton.testing.test_app_offline_policy_chain_delivery import delivered  # noqa: F401  (transitive fixture)
from skeleton.testing.test_app_offline_policy_signed_delivery import policy_migration  # noqa: F401  (transitive fixture)
from skeleton.testing.test_app_offline_policy_signed_progress_migration import migration  # noqa: F401  (transitive fixture)
from skeleton.testing.test_app_offline_signed_progress_migration import signed  # noqa: F401  (transitive fixture)

pytestmark = pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor custody")


@pytest.fixture
def relocated(chain_delivery, tmp_path, capsys):
    old_signed, new_signed = _signed_pair(chain_delivery, tmp_path, capsys)
    old_unsigned = _independent_installed_game(
        tmp_path, capsys, "mixed-relocation-unsigned-original", 614,
    )
    new_unsigned_root = tmp_path / "mixed-unsigned-relocated"
    assert run_app_cli([
        "studio-journey", "--install-archive",
        "--archive", old_unsigned.archive,
        "--expected-archive-sha256", old_unsigned.expected_archive_sha256,
        "--expected-manifest-sha256", old_unsigned.expected_manifest_sha256,
        "--output", str(new_unsigned_root), "--trusted-local-operator",
    ]) == 0
    capsys.readouterr()
    new_unsigned = replace(
        old_unsigned, installed_source=str(new_unsigned_root),
    )
    return old_unsigned, new_unsigned, old_signed, new_signed


def _call(items, **overrides):
    before_unsigned, after_unsigned, before_signed, after_signed = items
    kwargs = {
        "before_unsigned": [before_unsigned],
        "after_unsigned": [after_unsigned],
        "before_signed": [before_signed],
        "after_signed": [after_signed],
        "authorized": True,
    }
    kwargs.update(overrides)
    return assure_mixed_game_library_relocation(**kwargs)


def _cli(items):
    names = (
        "before-unsigned", "after-unsigned", "before-signed", "after-signed",
    )
    argv = ["audit-mixed-library-relocation"]
    for name, item in zip(names, items):
        argv.extend(("--" + name, json.dumps(asdict(item))))
    return argv + ["--trusted-local-operator"]


def test_real_signed_and_unsigned_reinstallation_preserves_replay(
    relocated, capsys,
):
    before = tuple(
        open(path, "rb").read() for path in (
            relocated[0].archive, relocated[0].private_save,
            relocated[2].archive, relocated[2].private_save,
        )
    )
    assert run_app_cli(_cli(relocated)) == 0
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["game_count"] == 2
    assert receipt["unsigned_game_count"] == 1
    assert receipt["source_signed_game_count"] == 1
    assert receipt["old_and_new_original_games_replayed"] is True
    assert receipt["private_progress_preserved"] is True
    assert receipt["signed_source_and_policy_history_preserved"] is True
    assert receipt["unsigned_sources_explicitly_disclosed"] is True
    assert receipt["relocation_performed"] is False
    assert receipt["migration_atomicity_proven"] is False
    assert receipt["native_device_qualified"] is False
    assert receipt["release_certified"] is False
    assert before == tuple(
        open(path, "rb").read() for path in (
            relocated[0].archive, relocated[0].private_save,
            relocated[2].archive, relocated[2].private_save,
        )
    )


def test_same_installed_root_cannot_count_as_relocation(relocated):
    old_unsigned, _, old_signed, new_signed = relocated
    with pytest.raises(OfflineMixedGameLibraryRelocationError, match="distinct"):
        _call((old_unsigned, old_unsigned, old_signed, new_signed))


def test_cross_mode_old_new_root_alias_rejected(relocated):
    old_unsigned, new_unsigned, old_signed, _ = relocated
    # The early cross-mode path-alias fence correctly blocks before any source
    # inode reads; the later distinct-root fence is also a valid denial.
    with pytest.raises(OfflineMixedGameLibraryRelocationError, match="distinct|path alias"):
        _call((old_unsigned, new_unsigned, old_signed,
               replace(old_signed, installed_source=new_unsigned.installed_source)))


def test_different_names_for_same_source_inode_are_not_relocation(
    relocated, monkeypatch,
):
    import skeleton.app.offline_mixed_game_library_relocation as module
    original = module._snapshot
    first = original([relocated[0]], [relocated[2]])
    calls = 0

    def alias(*args):
        nonlocal calls
        calls += 1
        snapshot = original(*args)
        if calls == 2:
            unsigned, signed = snapshot
            aliased = list(unsigned[0])
            aliased[0] = first[0][0][0]
            return ((tuple(aliased),), signed)
        return snapshot

    monkeypatch.setattr(module, "_snapshot", alias)
    with pytest.raises(OfflineMixedGameLibraryRelocationError, match="inodes"):
        _call(relocated)


def test_wrong_unsigned_save_pin_blocks_entire_relocation(relocated):
    old_unsigned, new_unsigned, old_signed, new_signed = relocated
    with pytest.raises((OSError, ValueError)):
        _call((
            old_unsigned,
            replace(new_unsigned, expected_save_sha256="0" * 64),
            old_signed, new_signed,
        ))


def test_signed_policy_history_downgrade_denied(relocated):
    old_unsigned, new_unsigned, old_signed, new_signed = relocated
    with pytest.raises((OSError, ValueError)):
        _call((
            old_unsigned, new_unsigned, old_signed,
            replace(new_signed, expected_policy_sha256=(
                *new_signed.expected_policy_sha256[:-1], "0" * 64,
            )),
        ))


def test_tampered_relocated_unsigned_game_denied(relocated):
    relocated_root = relocated[1].installed_source
    with open(os.path.join(relocated_root, "index.html"), "wb") as stream:
        stream.write(b"changed game")
    with pytest.raises((OSError, ValueError)):
        _call(relocated)


def test_malformed_signed_entry_rejected_before_custody_reads(
    relocated, monkeypatch,
):
    import skeleton.app.offline_mixed_game_library_relocation as module
    monkeypatch.setattr(
        module, "_snapshot",
        lambda *_: pytest.fail("invalid entry was read"),
    )
    old_unsigned, new_unsigned, _, new_signed = relocated
    with pytest.raises((ValueError, TypeError)):
        assure_mixed_game_library_relocation(
            [old_unsigned], [new_unsigned], [object()], [new_signed],
            authorized=True,
        )


def test_cross_mode_custody_alias_rejected_before_reads(
    relocated, monkeypatch,
):
    import skeleton.app.offline_mixed_game_library_relocation as module
    monkeypatch.setattr(
        module, "_snapshot",
        lambda *_: pytest.fail("cross-mode alias was read"),
    )
    old_unsigned, new_unsigned, old_signed, new_signed = relocated
    with pytest.raises(OfflineMixedGameLibraryRelocationError, match="path alias"):
        assure_mixed_game_library_relocation(
            [replace(old_unsigned, archive=old_signed.archive)],
            [new_unsigned], [old_signed], [new_signed], authorized=True,
        )


def test_missing_operator_authority_precedes_any_custody_reads(
    relocated, monkeypatch,
):
    import skeleton.app.offline_mixed_game_library_relocation as module
    monkeypatch.setattr(
        module, "_snapshot",
        lambda *_: pytest.fail("unauthorized read attempted"),
    )
    with pytest.raises(PermissionError):
        _call(relocated, authorized=False)


def test_cli_missing_authority_blocks_without_success(relocated, capsys):
    argv = _cli(relocated)
    argv.remove("--trusted-local-operator")
    assert run_app_cli(argv) == 2
    receipt = json.loads(capsys.readouterr().err)
    assert receipt["status"] == "blocked"
    assert receipt["release_certified"] is False


def test_final_mixed_replay_detects_same_byte_archive_swap(
    relocated, tmp_path, monkeypatch,
):
    import skeleton.app.offline_mixed_game_library_relocation as module
    original = module.assure_signed_library_relocation
    archive = relocated[0].archive

    def substitute(*args, **kwargs):
        receipt = original(*args, **kwargs)
        replacement = tmp_path / "same-byte-relocation-archive.zip"
        with open(archive, "rb") as stream:
            replacement.write_bytes(stream.read())
        replacement.chmod(0o600)
        os.replace(replacement, archive)
        return receipt

    monkeypatch.setattr(module, "assure_signed_library_relocation", substitute)
    with pytest.raises((OSError, ValueError)):
        _call(relocated)


def test_mixed_relocation_receipt_matches_stable_audit(relocated):
    first = _call(relocated)
    second = _call(relocated)
    assert first == second
    assert len(first["relocation_receipt_sha256"]) == 64
    assert all(item["release_certified"] is False for item in first["games"])
