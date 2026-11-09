from __future__ import annotations

import json
from pathlib import Path

import pytest

import scripts.build_p1_terminal_failure_journeys as builder


REPOSITORY = "Apeloff1/Skeleton"
HEAD = "a" * 40


def _policy() -> dict:
    return {
        "required_families": ["restore"],
        "journey_classes": {"restore": ["restore"]},
        "failure_families": [
            {
                "family": "restore",
                "test_paths": ["tests/test_restore_fixture.py"],
            }
        ],
    }


def _prom01(**overrides: object) -> dict:
    value: dict[str, object] = {
        "accepted": True,
        "task_id": "P1-PROM-01",
        "accountability_id": "ACC-P1-PROM-01",
        "repository": REPOSITORY,
        "commit_sha": HEAD,
        "promotion_authority": False,
        "signed_promotion": False,
        "decision_digest": "b" * 64,
    }
    value.update(overrides)
    return value


def _configure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    prom01: dict,
) -> Path:
    policy_path = Path("policy.json")
    (tmp_path / policy_path).write_text(
        json.dumps(_policy()),
        encoding="utf-8",
    )
    prom01_path = tmp_path / "prom01.json"
    prom01_path.write_text(json.dumps(prom01), encoding="utf-8")
    monkeypatch.setattr(builder, "ROOT", tmp_path)
    monkeypatch.setattr(builder, "POLICY_PATH", policy_path)
    monkeypatch.setattr(
        builder,
        "validate_repository",
        lambda root: {"valid": True},
    )
    monkeypatch.setattr(
        builder,
        "_digest_paths",
        lambda paths: "c" * 64,
    )
    return prom01_path


def test_builder_accepts_exact_prom01_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prom01_path = _configure(tmp_path, monkeypatch, _prom01())
    payload, refs = builder.build_bundle(
        repository=REPOSITORY,
        commit_sha=HEAD,
        prom01_bundle_path=prom01_path,
    )

    assert payload["accepted"] is True
    assert payload["prom01_bundle_digest"] == "b" * 64
    assert payload["observation_count"] == 1
    assert refs[0]["category"] == "p1_terminal_failure_journeys"


@pytest.mark.parametrize(
    ("override", "match"),
    (
        ({"task_id": "P1-PROM-99"}, "task identity mismatch"),
        (
            {"accountability_id": "ACC-P1-PROM-99"},
            "accountability identity mismatch",
        ),
        ({"repository": "Other/Skeleton"}, "repository mismatch"),
        ({"commit_sha": "d" * 40}, "exact-head mismatch"),
        (
            {"promotion_authority": True},
            "unexpectedly carries promotion authority",
        ),
        (
            {"signed_promotion": True},
            "unexpectedly carries signed promotion",
        ),
        (
            {"decision_digest": "not-a-digest"},
            "decision digest missing or malformed",
        ),
    ),
)
def test_builder_rejects_prom01_substitution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    override: dict,
    match: str,
) -> None:
    prom01_path = _configure(
        tmp_path,
        monkeypatch,
        _prom01(**override),
    )

    with pytest.raises(builder.FailureJourneyBuildError, match=match):
        builder.build_bundle(
            repository=REPOSITORY,
            commit_sha=HEAD,
            prom01_bundle_path=prom01_path,
        )


def test_builder_rejects_rejected_prom01(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prom01_path = _configure(
        tmp_path,
        monkeypatch,
        _prom01(accepted=False),
    )

    with pytest.raises(
        builder.FailureJourneyBuildError,
        match="bundle is not accepted",
    ):
        builder.build_bundle(
            repository=REPOSITORY,
            commit_sha=HEAD,
            prom01_bundle_path=prom01_path,
        )
