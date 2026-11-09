"""Signed source, historical signer policy and saved-game relocation acceptance."""
from __future__ import annotations

from dataclasses import asdict, replace
import json
import os

import pytest

from skeleton.app.cli import run_app_cli
from skeleton.app.offline_signed_game_library_audit import SignedGameLibraryEntry
from skeleton.app.offline_signed_game_library_relocation import (
    SignedGameLibraryRelocationError, assure_signed_library_relocation,
)
from skeleton.testing.test_app_offline_policy_chain_delivery import chain_delivery
from skeleton.testing.test_app_offline_policy_signed_delivery import delivered

pytestmark = pytest.mark.skipif(os.name != "posix", reason="POSIX custody")


def _pair(chain_delivery, tmp_path, capsys):
    old = SignedGameLibraryEntry(
        installed_source=str(chain_delivery["installed_source"]),
        archive=str(chain_delivery["archive"]),
        private_save=str(chain_delivery["private_save"]),
        public_key_file=str(chain_delivery["public_key_file"]),
        signature_file=str(chain_delivery["signature_file"]),
        policies=tuple(str(p) for p in chain_delivery["policies"]),
        expected_policy_sha256=tuple(chain_delivery["expected_policy_sha256"]),
        expected_archive_sha256=chain_delivery["expected_archive_sha256"],
        expected_manifest_sha256=chain_delivery["expected_manifest_sha256"],
        expected_save_sha256=chain_delivery["expected_save_sha256"],
        expected_public_key_sha256=chain_delivery["expected_public_key_sha256"],
    )
    new_root = tmp_path / "relocated-signed-game"
    assert run_app_cli([
        "studio-journey", "--install-archive",
        "--archive", old.archive,
        "--expected-archive-sha256", old.expected_archive_sha256,
        "--expected-manifest-sha256", old.expected_manifest_sha256,
        "--output", str(new_root), "--trusted-local-operator",
    ]) == 0
    capsys.readouterr()
    return old, replace(old, installed_source=str(new_root))


def _cli(old, new):
    return [
        "audit-signed-library-relocation",
        "--before", json.dumps(asdict(old)),
        "--after", json.dumps(asdict(new)),
        "--trusted-local-operator",
    ]


def test_real_signed_game_relocation_keeps_policy_history_and_replay(
    chain_delivery, tmp_path, capsys,
):
    old, new = _pair(chain_delivery, tmp_path, capsys)
    original_save = chain_delivery["private_save"].read_bytes()
    assert run_app_cli(_cli(old, new)) == 0
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["game_count"] == 1
    assert receipt["games"][0]["policy_epoch_chain"] == [2, 3]
    assert receipt["source_signatures_and_policy_history_preserved"] is True
    assert receipt["private_progress_preserved"] is True
    assert receipt["relocation_performed"] is False
    assert receipt["policy_freshness_independently_proven"] is False
    assert receipt["native_device_qualified"] is False
    assert receipt["release_certified"] is False
    assert chain_delivery["private_save"].read_bytes() == original_save


def test_same_root_not_accepted_as_relocation(chain_delivery, tmp_path, capsys):
    old, _ = _pair(chain_delivery, tmp_path, capsys)
    with pytest.raises(SignedGameLibraryRelocationError, match="independent"):
        assure_signed_library_relocation([old], [old], authorized=True)


def test_signer_pin_or_history_downgrade_rejected(chain_delivery, tmp_path, capsys):
    old, new = _pair(chain_delivery, tmp_path, capsys)
    for changed in (
        replace(new, expected_public_key_sha256="0" * 64),
        replace(new, expected_policy_sha256=(
            *new.expected_policy_sha256[:-1], "0" * 64,
        )),
    ):
        with pytest.raises((ValueError, OSError)):
            assure_signed_library_relocation([old], [changed], authorized=True)


def test_mutated_new_source_denies_signed_relocation(chain_delivery, tmp_path, capsys):
    old, new = _pair(chain_delivery, tmp_path, capsys)
    (tmp_path / "relocated-signed-game" / "index.html").write_text("tamper")
    with pytest.raises((ValueError, OSError)):
        assure_signed_library_relocation([old], [new], authorized=True)


def test_missing_operator_acknowledgement_blocks_cli(chain_delivery, tmp_path, capsys):
    old, new = _pair(chain_delivery, tmp_path, capsys)
    argv = _cli(old, new)
    argv.remove("--trusted-local-operator")
    assert run_app_cli(argv) == 2
    assert json.loads(capsys.readouterr().err)["status"] == "blocked"


def test_no_authority_precedes_any_reads(chain_delivery, tmp_path, capsys, monkeypatch):
    old, new = _pair(chain_delivery, tmp_path, capsys)
    import skeleton.app.offline_signed_game_library_relocation as module
    monkeypatch.setattr(
        module, "_identities",
        lambda *_: pytest.fail("unauthorized read attempted"),
    )
    with pytest.raises(PermissionError):
        assure_signed_library_relocation([old], [new], authorized=False)
