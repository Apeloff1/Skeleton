from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from scripts import verify_vol005_state_migration_closure as verifier


REPO_ROOT = Path(__file__).resolve().parents[1]
HEAD = "a" * 40


def test_current_vol005_independent_verifier_is_valid() -> None:
    receipt = verifier.verify(REPO_ROOT, head_sha=HEAD)

    assert receipt["valid"] is True
    assert receipt["verifier"] == "independent-vol005-state-migration-v1"
    assert receipt["head_sha"] == HEAD
    assert receipt["physical_store_count"] == 9
    assert receipt["state_domain_count"] == 20
    assert receipt["source_of_truth_domain_count"] == 13
    assert receipt["scenario_count"] >= 9
    assert len(receipt["authority_digest"]) == 64


def test_independent_verifier_rejects_reintroduced_ghost_authority(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = verifier._json

    def fake_json(path: Path):
        payload = original(path)
        if path.name == "state_topology.json":
            payload = deepcopy(payload)
            payload["physical_stores"].append(
                {
                    "id": "verification-evidence-unbound",
                    "technology": "ghost",
                }
            )
        return payload

    monkeypatch.setattr(verifier, "_json", fake_json)

    with pytest.raises(verifier.VerificationError, match="retired authority remains active"):
        verifier.verify(REPO_ROOT, head_sha=HEAD)


def test_independent_verifier_rejects_missing_domain_coverage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = verifier._json

    def fake_json(path: Path):
        payload = original(path)
        if path.name == "state_migration_qualification.json":
            payload = deepcopy(payload)
            payload["domain_qualification"] = payload["domain_qualification"][1:]
        return payload

    monkeypatch.setattr(verifier, "_json", fake_json)

    with pytest.raises(verifier.VerificationError, match="coverage is not exact"):
        verifier.verify(REPO_ROOT, head_sha=HEAD)


def test_independent_verifier_rejects_release_gate_weakening(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = verifier._json

    def fake_json(path: Path):
        payload = original(path)
        if path.name == "ai_app_construction.json":
            payload = deepcopy(payload)
            gate = next(
                item
                for item in payload["acceptance_gates"]
                if item["id"] == "state-migration-qualification"
            )
            gate["required"] = False
        return payload

    monkeypatch.setattr(verifier, "_json", fake_json)

    with pytest.raises(
        verifier.VerificationError,
        match="does not require exact state migration qualification gate",
    ):
        verifier.verify(REPO_ROOT, head_sha=HEAD)


def test_independent_verifier_rejects_placeholder_source_of_truth(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = verifier._json

    def fake_json(path: Path):
        payload = original(path)
        if path.name == "state_topology.json":
            payload = deepcopy(payload)
            domain = next(
                item
                for item in payload["state_domains"]
                if item.get("source_of_truth") is True
            )
            domain["status"] = "declared-partial"
        return payload

    monkeypatch.setattr(verifier, "_json", fake_json)

    with pytest.raises(verifier.VerificationError, match="placeholder source-of-truth status"):
        verifier.verify(REPO_ROOT, head_sha=HEAD)


def test_independent_verifier_requires_full_sha() -> None:
    with pytest.raises(verifier.VerificationError, match="full lowercase git SHA"):
        verifier.verify(REPO_ROOT, head_sha="abc123")
