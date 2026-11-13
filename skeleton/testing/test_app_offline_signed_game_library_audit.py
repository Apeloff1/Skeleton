"""Signed original-game library end-to-end and adversarial acceptance."""
from __future__ import annotations

from dataclasses import asdict
import json
import os

import pytest

from skeleton.app.cli import run_app_cli
from skeleton.app.offline_signed_game_library_audit import (
    SignedGameLibraryAuditError, SignedGameLibraryEntry,
    audit_signed_game_library, parse_signed_game_entry,
)
from skeleton.testing.test_app_offline_policy_chain_delivery import chain_delivery
from skeleton.testing.test_app_offline_policy_signed_delivery import delivered
from skeleton.testing.test_app_offline_policy_signed_delivery import policy_migration  # noqa: F401  (transitive fixture)
from skeleton.testing.test_app_offline_policy_signed_progress_migration import migration  # noqa: F401  (transitive fixture)
from skeleton.testing.test_app_offline_signed_progress_migration import signed  # noqa: F401  (transitive fixture)

pytestmark = pytest.mark.skipif(os.name != "posix", reason="POSIX custody")


def _entry(chain_delivery):
    return SignedGameLibraryEntry(
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


def _cli(entry):
    return ["audit-signed-game-library", "--entry",
            json.dumps(asdict(entry)), "--trusted-local-operator"]


def test_real_signed_policy_history_source_and_private_replay(chain_delivery, capsys):
    entry = _entry(chain_delivery)
    before = [
        path.read_bytes() for path in
        [chain_delivery["archive"], chain_delivery["private_save"],
         *chain_delivery["policies"]]
    ]
    assert run_app_cli(_cli(entry)) == 0
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["game_count"] == 1
    assert receipt["games"][0]["policy_epoch_chain"] == [2, 3]
    assert receipt["source_archive_signatures_verified"] is True
    assert receipt["installed_game_and_private_save_replayed"] is True
    assert receipt["policy_freshness_independently_proven"] is False
    assert receipt["native_device_qualified"] is False
    assert receipt["release_certified"] is False
    assert before == [
        path.read_bytes() for path in
        [chain_delivery["archive"], chain_delivery["private_save"],
         *chain_delivery["policies"]]
    ]


def test_wrong_key_and_policy_pins_fail_closed(chain_delivery, capsys):
    entry = _entry(chain_delivery)
    for name in ("expected_public_key_sha256", "expected_save_sha256"):
        payload = asdict(entry)
        payload[name] = "0" * 64
        assert run_app_cli(["audit-signed-game-library", "--entry",
                            json.dumps(payload), "--trusted-local-operator"]) == 2
        assert json.loads(capsys.readouterr().err)["status"] == "blocked"
    payload = asdict(entry)
    payload["expected_policy_sha256"] = [
        *payload["expected_policy_sha256"][:-1], "0" * 64,
    ]
    with pytest.raises(ValueError):
        audit_signed_game_library(
            [parse_signed_game_entry(json.dumps(payload))], authorized=True,
        )


def test_policy_snapshot_same_bytes_replacement_between_passes_rejected(
    chain_delivery, tmp_path, monkeypatch,
):
    import skeleton.app.offline_signed_game_library_audit as module
    old = chain_delivery["policies"][0]
    original = module._verify
    calls = 0

    def substitute(*args):
        nonlocal calls
        result = original(*args)
        calls += 1
        if calls == 1:
            other = tmp_path / "identical-policy.json"
            other.write_bytes(old.read_bytes())
            other.chmod(0o600)
            os.replace(other, old)
        return result

    monkeypatch.setattr(module, "_verify", substitute)
    with pytest.raises(SignedGameLibraryAuditError, match="custody changed"):
        audit_signed_game_library([_entry(chain_delivery)], authorized=True)


def test_duplicate_signed_game_paths_rejected(chain_delivery):
    entry = _entry(chain_delivery)
    with pytest.raises(SignedGameLibraryAuditError, match="duplicate"):
        audit_signed_game_library([entry, entry], authorized=True)


def test_unauthorized_batch_never_reads(chain_delivery, monkeypatch):
    import skeleton.app.offline_signed_game_library_audit as module
    monkeypatch.setattr(
        module, "_identities",
        lambda *_: pytest.fail("unauthorized read attempted"),
    )
    with pytest.raises(PermissionError):
        audit_signed_game_library([_entry(chain_delivery)], authorized=False)


def test_malformed_and_oversized_signed_entries_rejected(chain_delivery):
    entry = _entry(chain_delivery)
    for raw in ("null", "[]", '{"archive":"x","archive":"y"}',
                "{" + "x" * 8200 + "}"):
        with pytest.raises((ValueError, TypeError)):
            parse_signed_game_entry(raw)


def test_repeated_policy_path_and_malformed_epoch_chain_denied(chain_delivery):
    payload = asdict(_entry(chain_delivery))
    payload["policies"] = list(payload["policies"])
    payload["policies"][1] = payload["policies"][0]
    with pytest.raises(SignedGameLibraryAuditError, match="duplicate"):
        audit_signed_game_library(
            [parse_signed_game_entry(json.dumps(payload))], authorized=True,
        )


def test_no_authority_cli_denial(chain_delivery, capsys):
    argv = _cli(_entry(chain_delivery))
    argv.remove("--trusted-local-operator")
    assert run_app_cli(argv) == 2
    assert json.loads(capsys.readouterr().err)["status"] == "blocked"
