"""Bounded, fail-closed, read-only multi-epoch signer history acceptance."""
from __future__ import annotations

from hashlib import sha256
import json
import os

import pytest

from skeleton.app.cli import run_app_cli
from skeleton.app.offline_source_trust_policy import SCHEMA as POLICY_SCHEMA
from skeleton.app.offline_trust_policy_chain import (
    OfflineTrustPolicyChainError, inspect_offline_trust_policy_chain,
)

pytestmark = pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor custody")


def _policy(path, epoch, allowed, revoked):
    payload = {
        "schema": POLICY_SCHEMA, "epoch": epoch,
        "archive_sha256": "a" * 64,
        "manifest_sha256": "b" * 64,
        "authorized_key_sha256": allowed,
        "revoked_key_sha256": revoked,
    }
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    path.chmod(0o600)
    return sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def chain(tmp_path):
    old, middle, final = (tmp_path / f"policy-{i}.json" for i in range(3))
    pins = [
        _policy(old, 2, ["c" * 64], []),
        _policy(middle, 3, ["d" * 64], ["c" * 64]),
        _policy(final, 7, ["e" * 64], ["c" * 64, "d" * 64]),
    ]
    return {
        "policies": [old, middle, final],
        "expected_policy_sha256": pins,
        "expected_archive_sha256": "a" * 64,
        "expected_manifest_sha256": "b" * 64,
        "authorized": True,
    }


def test_three_epoch_rotation_retains_revocation_and_never_certifies(chain):
    before = [p.read_bytes() for p in chain["policies"]]
    result = inspect_offline_trust_policy_chain(**chain)
    assert result["epoch_chain"] == [2, 3, 7]
    assert result["transition_count"] == 2
    assert result["final_active_key_sha256"] == ["e" * 64]
    assert result["final_revoked_key_sha256"] == ["c" * 64, "d" * 64]
    assert result["revocation_monotonic_in_supplied_chain"] is True
    assert result["read_only"] is True
    assert result["policy_transition_published"] is False
    assert result["persistent_epoch_rollback_protection"] is False
    assert result["release_certified"] is False
    assert [p.read_bytes() for p in chain["policies"]] == before


def test_missing_operator_authority_denied_before_reads(chain, monkeypatch):
    import skeleton.app.offline_trust_policy_chain as module
    monkeypatch.setattr(
        module, "_read_policy",
        lambda *_: pytest.fail("read attempted without authorization"),
    )
    with pytest.raises(PermissionError):
        inspect_offline_trust_policy_chain(**{**chain, "authorized": False})


def test_duplicate_path_and_duplicate_pin_denied(chain):
    for paths, pins in (
        ([chain["policies"][0]] * 2, chain["expected_policy_sha256"][:2]),
        (chain["policies"][:2], [chain["expected_policy_sha256"][0]] * 2),
    ):
        with pytest.raises(OfflineTrustPolicyChainError, match="repeated"):
            inspect_offline_trust_policy_chain(**{
                **chain, "policies": paths, "expected_policy_sha256": pins,
            })


def test_boundaries_and_wrong_independent_pin_denied(chain):
    with pytest.raises(OfflineTrustPolicyChainError, match="2-16"):
        inspect_offline_trust_policy_chain(**{
            **chain, "policies": chain["policies"][:1],
            "expected_policy_sha256": chain["expected_policy_sha256"][:1],
        })
    with pytest.raises(OfflineTrustPolicyChainError, match="pin mismatch"):
        inspect_offline_trust_policy_chain(**{
            **chain, "expected_policy_sha256": [
                *chain["expected_policy_sha256"][:2], "0" * 64,
            ],
        })


def test_revocation_resurrection_denied(chain):
    last = chain["policies"][-1]
    pin = _policy(last, 7, ["c" * 64, "e" * 64], ["d" * 64])
    with pytest.raises(OfflineTrustPolicyChainError, match="revocation"):
        inspect_offline_trust_policy_chain(**{
            **chain, "expected_policy_sha256": [
                *chain["expected_policy_sha256"][:2], pin,
            ],
        })


def test_epoch_rollback_denied(chain):
    last = chain["policies"][-1]
    pin = _policy(last, 2, ["e" * 64], ["c" * 64, "d" * 64])
    with pytest.raises(OfflineTrustPolicyChainError, match="epoch"):
        inspect_offline_trust_policy_chain(**{
            **chain, "expected_policy_sha256": [
                *chain["expected_policy_sha256"][:2], pin,
            ],
        })


def test_symlink_policy_denied(chain, tmp_path):
    alias = tmp_path / "alias-policy.json"
    alias.symlink_to(chain["policies"][2])
    with pytest.raises((OSError, ValueError)):
        inspect_offline_trust_policy_chain(**{
            **chain, "policies": [*chain["policies"][:2], alias],
        })


def test_early_policy_replacement_during_chain_denied(chain, monkeypatch):
    import skeleton.app.offline_trust_policy_chain as module
    original = module.inspect_offline_trust_policy_transition
    count = 0

    def changed(*args, **kwargs):
        nonlocal count
        receipt = original(*args, **kwargs)
        count += 1
        if count == 2:
            path = chain["policies"][0]
            data = path.read_bytes()
            path.unlink()
            path.write_bytes(data)
            path.chmod(0o600)
        return receipt

    monkeypatch.setattr(module, "inspect_offline_trust_policy_transition", changed)
    with pytest.raises(OfflineTrustPolicyChainError, match="changed"):
        inspect_offline_trust_policy_chain(**chain)


def test_cli_authority_and_three_epoch_acceptance(chain, capsys):
    argv = ["inspect-trust-policy-chain"]
    for path, pin in zip(chain["policies"], chain["expected_policy_sha256"]):
        argv += ["--policy", str(path), "--expected-policy-sha256", pin]
    argv += [
        "--expected-archive-sha256", chain["expected_archive_sha256"],
        "--expected-manifest-sha256", chain["expected_manifest_sha256"],
    ]
    assert run_app_cli(argv) == 2
    assert json.loads(capsys.readouterr().err)["status"] == "blocked"
    assert run_app_cli(argv + ["--trusted-local-operator"]) == 0
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["transition_count"] == 2
    assert receipt["release_certified"] is False
