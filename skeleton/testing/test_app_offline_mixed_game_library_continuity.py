"""End-to-end mixed library progress continuity with real signed/unsigned games."""
from __future__ import annotations

from dataclasses import asdict, replace
import json
import os

import pytest

from skeleton.app.cli import run_app_cli
from skeleton.app.offline_mixed_game_library_continuity import (
    OfflineMixedGameLibraryContinuityError,
    assure_mixed_game_library_continuity,
)
from skeleton.app.studio_journey import play_existing_source_game
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

pytestmark = pytest.mark.skipif(os.name != "posix", reason="POSIX private custody")


@pytest.fixture
def catalog(tmp_path, capsys, chain_delivery):
    unsigned = _independent_installed_game(
        tmp_path, capsys, "continuity-original-unsigned", 927,
    )
    signed = _signed_entry(chain_delivery)
    return unsigned, signed


def _advance(entry, destination, *, moves=("left",), fork_at_step=None):
    result = play_existing_source_game(
        entry.installed_source,
        expected_manifest_sha256=entry.expected_manifest_sha256,
        load_save=entry.private_save,
        expected_save_sha256=entry.expected_save_sha256,
        save_destination=destination,
        moves=moves,
        fork_at_step=fork_at_step,
        authorized=True,
    )
    return replace(
        entry, private_save=str(destination),
        expected_save_sha256=result["independent_save_sha256"],
    )


def _audit(before_unsigned, after_unsigned, before_signed, after_signed):
    return assure_mixed_game_library_continuity(
        before_unsigned, after_unsigned, before_signed, after_signed,
        authorized=True,
    )


def _cli(before_unsigned, after_unsigned, before_signed, after_signed):
    args = ["audit-mixed-library-continuity"]
    for name, entries in (
        ("before-unsigned-entry", before_unsigned),
        ("after-unsigned-entry", after_unsigned),
        ("before-signed-entry", before_signed),
        ("after-signed-entry", after_signed),
    ):
        for entry in entries:
            args.extend(("--" + name, json.dumps(asdict(entry))))
    return args + ["--trusted-local-operator"]


def test_real_signed_unsigned_progress_continuity_and_cli(catalog, tmp_path, capsys):
    unsigned, signed = catalog
    old = (
        open(unsigned.private_save, "rb").read(),
        open(signed.private_save, "rb").read(),
    )
    advanced_unsigned = _advance(unsigned, tmp_path / "new-unsigned.json")
    advanced_signed = _advance(signed, tmp_path / "new-signed.json")
    assert run_app_cli(_cli(
        [unsigned], [advanced_unsigned], [signed], [advanced_signed],
    )) == 0
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["game_count"] == 2
    assert receipt["advanced_games"] == 2
    assert receipt["unchanged_games"] == 0
    assert receipt["all_previous_actions_reexecuted_and_preserved"] is True
    assert receipt["source_and_signer_policy_history_preserved"] is True
    assert receipt["signed_and_unsigned_status_preserved"] is True
    assert receipt["read_only"] is True
    assert receipt["migration_performed"] is False
    assert receipt["persistent_rollback_protection"] is False
    assert receipt["release_certified"] is False
    assert "installed_source" not in json.dumps(receipt)
    assert old == (
        open(unsigned.private_save, "rb").read(),
        open(signed.private_save, "rb").read(),
    )


def test_unchanged_signed_game_allowed_if_other_game_advances(catalog, tmp_path):
    unsigned, signed = catalog
    newer = _advance(unsigned, tmp_path / "one-advance.json")
    result = _audit([unsigned], [newer], [signed], [signed])
    assert result["advanced_games"] == 1
    assert result["unchanged_games"] == 1
    assert result["release_certified"] is False


def test_no_progress_is_not_attested(catalog):
    unsigned, signed = catalog
    with pytest.raises(OfflineMixedGameLibraryContinuityError, match="no private replay"):
        _audit([unsigned], [unsigned], [signed], [signed])


def test_rollback_is_rejected(catalog, tmp_path):
    unsigned, signed = catalog
    newer = _advance(unsigned, tmp_path / "longer.json")
    with pytest.raises(OfflineMixedGameLibraryContinuityError):
        _audit([newer], [unsigned], [signed], [signed])


def test_fork_is_rejected_even_when_new_history_is_longer(catalog, tmp_path):
    unsigned, signed = catalog
    fork = _advance(
        unsigned, tmp_path / "forked.json",
        moves=("left", "right", "up", "down"),
        fork_at_step=1,
    )
    with pytest.raises(OfflineMixedGameLibraryContinuityError):
        _audit([unsigned], [fork], [signed], [signed])


def test_policy_history_downgrade_denied_before_game_replay(catalog):
    unsigned, signed = catalog
    downgraded = replace(
        signed, expected_policy_sha256=(
            *signed.expected_policy_sha256[:-1], "0" * 64,
        ),
    )
    with pytest.raises(OfflineMixedGameLibraryContinuityError, match="custody changed"):
        _audit([unsigned], [unsigned], [signed], [downgraded])


def test_cross_project_save_alias_rejected(catalog, tmp_path):
    unsigned, signed = catalog
    advanced = _advance(unsigned, tmp_path / "cross-save.json")
    invalid = replace(signed, private_save=unsigned.private_save)
    with pytest.raises(OfflineMixedGameLibraryContinuityError,
                       match="cross-project private save alias"):
        _audit([unsigned], [advanced], [signed], [invalid])


def test_invalid_authority_blocks_before_source_reads(catalog, monkeypatch):
    unsigned, signed = catalog
    import skeleton.app.offline_mixed_game_library_continuity as module
    monkeypatch.setattr(
        module, "_snapshot", lambda *_: pytest.fail("unauthorized read"),
    )
    with pytest.raises(PermissionError):
        module.assure_mixed_game_library_continuity(
            [unsigned], [unsigned], [signed], [signed], authorized=False,
        )


def test_final_audit_source_substitution_fails_closed(
    catalog, tmp_path, monkeypatch,
):
    unsigned, signed = catalog
    advanced = _advance(unsigned, tmp_path / "advanced.json")
    import skeleton.app.offline_mixed_game_library_continuity as module
    original = module.audit_mixed_game_library
    calls = 0

    def substitute(*args, **kwargs):
        nonlocal calls
        result = original(*args, **kwargs)
        calls += 1
        if calls == 2:
            archive = unsigned.archive
            with open(archive, "ab") as stream:
                stream.write(b"tampered")
        return result

    monkeypatch.setattr(module, "audit_mixed_game_library", substitute)
    with pytest.raises((OSError, ValueError)):
        _audit([unsigned], [advanced], [signed], [signed])


def test_cli_denies_missing_authority_and_mismatched_counts(catalog, capsys):
    unsigned, signed = catalog
    argv = _cli([unsigned], [unsigned], [signed], [signed])
    argv.remove("--trusted-local-operator")
    assert run_app_cli(argv) == 2
    assert json.loads(capsys.readouterr().err)["status"] == "blocked"
    bad = _cli([unsigned], [unsigned, unsigned], [signed], [signed])
    assert run_app_cli(bad) == 2
    assert json.loads(capsys.readouterr().err)["release_certified"] is False
