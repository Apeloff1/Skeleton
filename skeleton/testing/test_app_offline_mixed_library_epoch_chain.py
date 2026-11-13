"""Real original-game multi-generation continuity acceptance and failure fences."""
from __future__ import annotations

from dataclasses import asdict, replace
import json
import os

import pytest

from skeleton.app.cli import run_app_cli
from skeleton.app.offline_mixed_library_epoch_chain import (
    MAX_GENERATION_BYTES, MixedLibraryEpoch,
    OfflineMixedLibraryEpochChainError, _parse_generation,
    assure_mixed_library_epoch_chain,
)
from skeleton.testing.test_app_offline_mixed_game_library_continuity import (
    _advance, catalog,
)
from skeleton.testing.test_app_offline_mixed_game_library_continuity import chain_delivery  # noqa: F401  (transitive fixture)
from skeleton.testing.test_app_offline_policy_chain_delivery import delivered  # noqa: F401  (transitive fixture)
from skeleton.testing.test_app_offline_policy_signed_delivery import policy_migration  # noqa: F401  (transitive fixture)
from skeleton.testing.test_app_offline_policy_signed_progress_migration import migration  # noqa: F401  (transitive fixture)
from skeleton.testing.test_app_offline_signed_progress_migration import signed  # noqa: F401  (transitive fixture)

pytestmark = pytest.mark.skipif(os.name != "posix", reason="POSIX private custody")


def _epoch(unsigned, signed):
    return MixedLibraryEpoch((unsigned,), (signed,))


def _cli(*epochs):
    arguments = ["audit-mixed-library-epochs"]
    for epoch in epochs:
        arguments += [
            "--unsigned-generation", json.dumps([asdict(x) for x in epoch.unsigned]),
            "--signed-generation", json.dumps([asdict(x) for x in epoch.signed]),
        ]
    return arguments + ["--trusted-local-operator"]


def test_three_real_generations_signed_unsigned_cli(catalog, tmp_path, capsys):
    unsigned, signed = catalog
    original = (open(unsigned.private_save, "rb").read(),
                open(signed.private_save, "rb").read())
    u1 = _advance(unsigned, tmp_path / "epoch-u1.json")
    s2 = _advance(signed, tmp_path / "epoch-s2.json")
    epochs = (_epoch(unsigned, signed), _epoch(u1, signed), _epoch(u1, s2))
    assert run_app_cli(_cli(*epochs)) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["generation_count"] == 3
    assert result["transition_count"] == 2
    assert result["game_count"] == 2
    assert [t["advanced_games"] for t in result["transitions"]] == [1, 1]
    assert result["transitions"][0]["current_library_receipt_sha256"] == (
        result["transitions"][1]["previous_library_receipt_sha256"]
    )
    assert len(result["chain_sha256"]) == 64
    assert result["all_transitions_reexecuted"] is True
    assert result["read_only"] is True
    assert result["save_written"] is False
    assert result["release_certified"] is False
    assert result["native_device_qualified"] is False
    assert (open(unsigned.private_save, "rb").read(),
            open(signed.private_save, "rb").read()) == original


def test_three_generations_direct_api_is_deterministic(catalog, tmp_path):
    unsigned, signed = catalog
    u1 = _advance(unsigned, tmp_path / "epoch-direct-u1.json")
    s2 = _advance(signed, tmp_path / "epoch-direct-s2.json")
    epochs = (_epoch(unsigned, signed), _epoch(u1, signed), _epoch(u1, s2))
    a = assure_mixed_library_epoch_chain(epochs, authorized=True)
    b = assure_mixed_library_epoch_chain(epochs, authorized=True)
    assert a == b
    assert a["chain_sha256"] == b["chain_sha256"]
    assert a["source_and_signer_policy_history_preserved"] is True
    assert a["persistent_rollback_protection"] is False


def test_rollback_at_last_generation_fails_closed(catalog, tmp_path):
    unsigned, signed = catalog
    u1 = _advance(unsigned, tmp_path / "epoch-rollback-u1.json")
    s2 = _advance(signed, tmp_path / "epoch-rollback-s2.json")
    epochs = (_epoch(unsigned, signed), _epoch(u1, s2), _epoch(unsigned, s2))
    with pytest.raises(ValueError):
        assure_mixed_library_epoch_chain(epochs, authorized=True)


def test_no_progress_boundary_cannot_be_attested(catalog, tmp_path):
    unsigned, signed = catalog
    u1 = _advance(unsigned, tmp_path / "epoch-no-progress.json")
    epochs = (_epoch(unsigned, signed), _epoch(u1, signed), _epoch(u1, signed))
    with pytest.raises(ValueError):
        assure_mixed_library_epoch_chain(epochs, authorized=True)


def test_source_or_policy_switch_is_not_epoch_continuity(catalog, tmp_path):
    unsigned, signed = catalog
    u1 = _advance(unsigned, tmp_path / "epoch-source-u1.json")
    s2 = _advance(signed, tmp_path / "epoch-source-s2.json")
    replaced = replace(s2, expected_public_key_sha256="0" * 64)
    with pytest.raises(ValueError):
        assure_mixed_library_epoch_chain((
            _epoch(unsigned, signed), _epoch(u1, signed), _epoch(u1, replaced),
        ), authorized=True)


def test_missing_authorization_rejected_before_io(catalog):
    unsigned, signed = catalog
    with pytest.raises(PermissionError):
        assure_mixed_library_epoch_chain((
            _epoch(unsigned, signed), _epoch(unsigned, signed),
        ), authorized=False)


@pytest.mark.parametrize("count", [0, 1, 7])
def test_generation_count_bounds(catalog, count):
    unsigned, signed = catalog
    with pytest.raises(OfflineMixedLibraryEpochChainError):
        assure_mixed_library_epoch_chain(
            tuple(_epoch(unsigned, signed) for _ in range(count)),
            authorized=True,
        )


def test_reject_duplicate_keys_and_unbounded_generation():
    with pytest.raises(ValueError):
        _parse_generation('[{"archive":"a","archive":"b"}]', signed=False)
    with pytest.raises(OfflineMixedLibraryEpochChainError):
        _parse_generation("x" * (MAX_GENERATION_BYTES + 1), signed=False)
    with pytest.raises(OfflineMixedLibraryEpochChainError):
        _parse_generation("[]", signed=True)
    with pytest.raises(ValueError):
        _parse_generation('[NaN]', signed=True)


def test_cli_rejects_mismatched_epochs_before_source_access(capsys):
    assert run_app_cli([
        "audit-mixed-library-epochs",
        "--unsigned-generation", "[]",
        "--unsigned-generation", "[]",
        "--signed-generation", "[]",
        "--trusted-local-operator",
    ]) == 2
    err = json.loads(capsys.readouterr().err)
    assert err["status"] == "blocked"
    assert err["release_certified"] is False


def test_cli_requires_operator_acknowledgement(capsys):
    assert run_app_cli([
        "audit-mixed-library-epochs",
        "--unsigned-generation", "[]",
        "--unsigned-generation", "[]",
        "--signed-generation", "[]",
        "--signed-generation", "[]",
    ]) == 2
    assert json.loads(capsys.readouterr().err)["status"] == "blocked"
