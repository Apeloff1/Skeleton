from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.check_p1_champion_registry import (
    ChampionRegistryValidationError,
    compare_registries,
    validate_repository,
)
from skeleton.eval.champion_registry import (
    CandidateArtifact,
    PromotionTransition,
)


ROOT = Path(__file__).resolve().parents[1]
REGISTRY = Path("machine/p1_champion_registry.json")


def _payload() -> dict:
    return json.loads((ROOT / REGISTRY).read_text(encoding="utf-8"))


def _write(root: Path, payload: dict, name: str) -> Path:
    path = Path(name)
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


def _candidate(
    candidate_id: str,
    version: str,
    candidate_ref: str,
    *,
    artifact_digest: str,
    parent_candidate_digest: str | None = None,
) -> tuple[dict, CandidateArtifact]:
    row = {
        "candidate_id": candidate_id,
        "version": version,
        "candidate_ref": candidate_ref,
        "artifact_digest": artifact_digest,
        "source_commit": "a" * 40,
        "experiment_manifest_digest": "1" * 64,
        "benchmark_manifest_digest": "2" * 64,
        "benchmark_qualification_digest": "3" * 64,
        "reproducibility_bundle_digest": "4" * 64,
        "parent_candidate_digest": parent_candidate_digest,
        "tags": ["core"],
    }
    artifact = CandidateArtifact(
        candidate_id=row["candidate_id"],
        version=row["version"],
        candidate_ref=row["candidate_ref"],
        artifact_digest=row["artifact_digest"],
        source_commit=row["source_commit"],
        experiment_manifest_digest=row["experiment_manifest_digest"],
        benchmark_manifest_digest=row["benchmark_manifest_digest"],
        benchmark_qualification_digest=row[
            "benchmark_qualification_digest"
        ],
        reproducibility_bundle_digest=row[
            "reproducibility_bundle_digest"
        ],
        parent_candidate_digest=row["parent_candidate_digest"],
        tags=tuple(row["tags"]),
    )
    return row, artifact


def _registry(
    *,
    with_challenger: bool = True,
    with_transition: bool = False,
) -> dict:
    champion_row, champion = _candidate(
        "candidate-v1",
        "v1",
        "candidate:v1",
        artifact_digest="5" * 64,
    )
    candidates = [champion_row]
    challenger = None
    if with_challenger:
        challenger_row, challenger = _candidate(
            "candidate-v2",
            "v2",
            "candidate:v2",
            artifact_digest="6" * 64,
            parent_candidate_digest=champion.candidate_digest,
        )
        candidates.append(challenger_row)

    transitions: list[dict] = []
    if with_transition:
        assert challenger is not None
        transition = PromotionTransition(
            sequence=1,
            previous_champion_digest=champion.candidate_digest,
            challenger_digest=challenger.candidate_digest,
            candidate_qualification_digest="7" * 64,
            benchmark_qualification_digest="8" * 64,
            improvement_claim_digest="9" * 64,
            baseline_observation_digest="a" * 64,
            candidate_observation_digest="b" * 64,
            prior_transition_digest=None,
        )
        transitions.append(
            {
                "sequence": transition.sequence,
                "previous_champion_digest": (
                    transition.previous_champion_digest
                ),
                "challenger_digest": transition.challenger_digest,
                "candidate_qualification_digest": (
                    transition.candidate_qualification_digest
                ),
                "benchmark_qualification_digest": (
                    transition.benchmark_qualification_digest
                ),
                "improvement_claim_digest": (
                    transition.improvement_claim_digest
                ),
                "baseline_observation_digest": (
                    transition.baseline_observation_digest
                ),
                "candidate_observation_digest": (
                    transition.candidate_observation_digest
                ),
                "prior_transition_digest": (
                    transition.prior_transition_digest
                ),
            }
        )

    return {
        "registry_id": "core-model",
        "candidates": candidates,
        "initial_champion_digest": champion.candidate_digest,
        "transitions": transitions,
    }


def test_repository_registry_is_valid_and_non_authoritative() -> None:
    report = validate_repository(ROOT)

    assert report["valid"] is True
    assert report["task_id"] == "P1-LEARN-03"
    assert report["accountability_ref"] == "ACC-P1-LEARN-03"
    assert report["production_authority"] is False
    assert len(report["registry_digest"]) == 64


def test_valid_registry_entry_is_accepted(tmp_path: Path) -> None:
    payload = _payload()
    payload["registries"] = [_registry()]
    path = _write(
        tmp_path,
        payload,
        "machine/p1_champion_registry.json",
    )

    report = validate_repository(tmp_path, registry_path=path)

    assert report["registry_count"] == 1


def test_policy_weakening_fails_closed(tmp_path: Path) -> None:
    payload = _payload()
    payload["policy"]["candidate_self_promotion"] = True
    path = _write(
        tmp_path,
        payload,
        "machine/p1_champion_registry.json",
    )

    with pytest.raises(
        ChampionRegistryValidationError,
        match="policy drift",
    ):
        validate_repository(tmp_path, registry_path=path)


def test_initial_champion_cannot_be_rewritten(tmp_path: Path) -> None:
    baseline = _payload()
    registry = _registry()
    baseline["registries"] = [registry]
    candidate = json.loads(json.dumps(baseline))

    challenger_row = candidate["registries"][0]["candidates"][1]
    challenger = CandidateArtifact(
        candidate_id=challenger_row["candidate_id"],
        version=challenger_row["version"],
        candidate_ref=challenger_row["candidate_ref"],
        artifact_digest=challenger_row["artifact_digest"],
        source_commit=challenger_row["source_commit"],
        experiment_manifest_digest=challenger_row[
            "experiment_manifest_digest"
        ],
        benchmark_manifest_digest=challenger_row[
            "benchmark_manifest_digest"
        ],
        benchmark_qualification_digest=challenger_row[
            "benchmark_qualification_digest"
        ],
        reproducibility_bundle_digest=challenger_row[
            "reproducibility_bundle_digest"
        ],
        parent_candidate_digest=challenger_row[
            "parent_candidate_digest"
        ],
        tags=tuple(challenger_row["tags"]),
    )
    candidate["registries"][0][
        "initial_champion_digest"
    ] = challenger.candidate_digest

    before = _write(tmp_path, baseline, "machine/baseline.json")
    after = _write(tmp_path, candidate, "machine/candidate.json")
    report = compare_registries(
        tmp_path,
        baseline_path=before,
        candidate_path=after,
    )

    assert report["accepted"] is False
    assert report["initial_champion_rewritten"] == ["core-model"]


def test_existing_candidate_identity_cannot_mutate(
    tmp_path: Path,
) -> None:
    baseline = _payload()
    baseline["registries"] = [_registry()]
    candidate = json.loads(json.dumps(baseline))
    candidate["registries"][0]["candidates"][1][
        "artifact_digest"
    ] = "f" * 64

    before = _write(tmp_path, baseline, "machine/baseline.json")
    after = _write(tmp_path, candidate, "machine/candidate.json")
    report = compare_registries(
        tmp_path,
        baseline_path=before,
        candidate_path=after,
    )

    assert report["accepted"] is False
    assert report["mutated_candidates"] == [
        ["core-model", "candidate-v2", "v2"]
    ]


def test_existing_candidate_cannot_be_deleted(tmp_path: Path) -> None:
    baseline = _payload()
    baseline["registries"] = [_registry()]
    candidate = json.loads(json.dumps(baseline))
    candidate["registries"][0]["candidates"].pop()

    before = _write(tmp_path, baseline, "machine/baseline.json")
    after = _write(tmp_path, candidate, "machine/candidate.json")
    report = compare_registries(
        tmp_path,
        baseline_path=before,
        candidate_path=after,
    )

    assert report["accepted"] is False
    assert report["removed_candidates"] == [
        ["core-model", "candidate-v2", "v2"]
    ]


def test_transition_history_cannot_be_rewritten(
    tmp_path: Path,
) -> None:
    baseline = _payload()
    baseline["registries"] = [_registry(with_transition=True)]
    candidate = json.loads(json.dumps(baseline))
    candidate["registries"][0]["transitions"][0][
        "improvement_claim_digest"
    ] = "c" * 64

    before = _write(tmp_path, baseline, "machine/baseline.json")
    after = _write(tmp_path, candidate, "machine/candidate.json")
    report = compare_registries(
        tmp_path,
        baseline_path=before,
        candidate_path=after,
    )

    assert report["accepted"] is False
    assert report["rewritten_transitions"] == ["core-model"]


def test_transition_history_cannot_be_deleted(
    tmp_path: Path,
) -> None:
    baseline = _payload()
    baseline["registries"] = [_registry(with_transition=True)]
    candidate = json.loads(json.dumps(baseline))
    candidate["registries"][0]["transitions"] = []

    before = _write(tmp_path, baseline, "machine/baseline.json")
    after = _write(tmp_path, candidate, "machine/candidate.json")
    report = compare_registries(
        tmp_path,
        baseline_path=before,
        candidate_path=after,
    )

    assert report["accepted"] is False
    assert report["rewritten_transitions"] == ["core-model"]


def test_additive_candidate_is_allowed(tmp_path: Path) -> None:
    baseline = _payload()
    baseline["registries"] = [_registry()]
    candidate = json.loads(json.dumps(baseline))
    parent_row = candidate["registries"][0]["candidates"][1]
    parent = CandidateArtifact(
        candidate_id=parent_row["candidate_id"],
        version=parent_row["version"],
        candidate_ref=parent_row["candidate_ref"],
        artifact_digest=parent_row["artifact_digest"],
        source_commit=parent_row["source_commit"],
        experiment_manifest_digest=parent_row[
            "experiment_manifest_digest"
        ],
        benchmark_manifest_digest=parent_row[
            "benchmark_manifest_digest"
        ],
        benchmark_qualification_digest=parent_row[
            "benchmark_qualification_digest"
        ],
        reproducibility_bundle_digest=parent_row[
            "reproducibility_bundle_digest"
        ],
        parent_candidate_digest=parent_row[
            "parent_candidate_digest"
        ],
        tags=tuple(parent_row["tags"]),
    )
    row, _ = _candidate(
        "candidate-v3",
        "v3",
        "candidate:v3",
        artifact_digest="d" * 64,
        parent_candidate_digest=parent.candidate_digest,
    )
    candidate["registries"][0]["candidates"].append(row)

    before = _write(tmp_path, baseline, "machine/baseline.json")
    after = _write(tmp_path, candidate, "machine/candidate.json")
    report = compare_registries(
        tmp_path,
        baseline_path=before,
        candidate_path=after,
    )

    assert report["accepted"] is True
    assert report["added_candidates"] == [
        ["core-model", "candidate-v3", "v3"]
    ]


def test_append_only_promotion_transition_is_allowed(
    tmp_path: Path,
) -> None:
    baseline = _payload()
    baseline["registries"] = [_registry()]
    candidate = _payload()
    candidate["registries"] = [_registry(with_transition=True)]

    before = _write(tmp_path, baseline, "machine/baseline.json")
    after = _write(tmp_path, candidate, "machine/candidate.json")
    report = compare_registries(
        tmp_path,
        baseline_path=before,
        candidate_path=after,
    )

    assert report["accepted"] is True
    assert report["appended_transitions"] == {"core-model": 1}


def test_unknown_registry_fields_fail_closed(tmp_path: Path) -> None:
    payload = _payload()
    registry = _registry()
    registry["force_champion"] = True
    payload["registries"] = [registry]
    path = _write(
        tmp_path,
        payload,
        "machine/p1_champion_registry.json",
    )

    with pytest.raises(
        ChampionRegistryValidationError,
        match="unknown fields",
    ):
        validate_repository(tmp_path, registry_path=path)
