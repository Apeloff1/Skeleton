#!/usr/bin/env python3
"""Validate P1 candidate identity and append-only champion history."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

from skeleton.eval.champion_registry import (
    CandidateArtifact,
    ChampionRegistry,
    ChampionRegistryError,
    PromotionTransition,
)


ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = Path("machine/p1_champion_registry.json")
EXPECTED_TASK = "P1-LEARN-03"
EXPECTED_ACCOUNTABILITY = "ACC-P1-LEARN-03"
EXPECTED_POLICY = {
    "production_authority": False,
    "candidate_self_promotion": False,
    "comparative_evidence_required": True,
    "immutable_candidate_identity": True,
    "immutable_initial_champion": True,
    "append_only_transitions": True,
    "transition_hash_chain_required": True,
    "exact_benchmark_binding": True,
    "exact_reproducibility_binding": True,
}


class ChampionRegistryValidationError(RuntimeError):
    pass


def _load(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ChampionRegistryValidationError(
            f"cannot read {path}"
        ) from exc


def _strict_keys(
    row: dict[str, Any],
    allowed: set[str],
    label: str,
) -> None:
    unknown = set(row) - allowed
    if unknown:
        raise ChampionRegistryValidationError(
            f"{label}: unknown fields {sorted(unknown)}"
        )


def _candidate(row: object) -> CandidateArtifact:
    if not isinstance(row, dict):
        raise ChampionRegistryValidationError(
            "candidate entries must be objects"
        )
    _strict_keys(
        row,
        {
            "candidate_id",
            "version",
            "candidate_ref",
            "artifact_digest",
            "source_commit",
            "experiment_manifest_digest",
            "benchmark_manifest_digest",
            "benchmark_qualification_digest",
            "reproducibility_bundle_digest",
            "parent_candidate_digest",
            "tags",
        },
        str(row.get("candidate_id", "?")),
    )
    return CandidateArtifact(
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
        parent_candidate_digest=row.get("parent_candidate_digest"),
        tags=tuple(row.get("tags", [])),
    )


def _transition(row: object) -> PromotionTransition:
    if not isinstance(row, dict):
        raise ChampionRegistryValidationError(
            "transition entries must be objects"
        )
    _strict_keys(
        row,
        {
            "sequence",
            "previous_champion_digest",
            "challenger_digest",
            "candidate_qualification_digest",
            "benchmark_qualification_digest",
            "improvement_claim_digest",
            "baseline_observation_digest",
            "candidate_observation_digest",
            "prior_transition_digest",
        },
        f"transition:{row.get('sequence', '?')}",
    )
    return PromotionTransition(
        sequence=row["sequence"],
        previous_champion_digest=row["previous_champion_digest"],
        challenger_digest=row["challenger_digest"],
        candidate_qualification_digest=row[
            "candidate_qualification_digest"
        ],
        benchmark_qualification_digest=row[
            "benchmark_qualification_digest"
        ],
        improvement_claim_digest=row["improvement_claim_digest"],
        baseline_observation_digest=row[
            "baseline_observation_digest"
        ],
        candidate_observation_digest=row[
            "candidate_observation_digest"
        ],
        prior_transition_digest=row.get("prior_transition_digest"),
    )


def _registry(row: object) -> ChampionRegistry:
    if not isinstance(row, dict):
        raise ChampionRegistryValidationError(
            "registry entries must be objects"
        )
    _strict_keys(
        row,
        {
            "registry_id",
            "candidates",
            "initial_champion_digest",
            "transitions",
        },
        str(row.get("registry_id", "?")),
    )
    candidates = row.get("candidates")
    transitions = row.get("transitions")
    if not isinstance(candidates, list) or not candidates:
        raise ChampionRegistryValidationError(
            "registry candidates must be a non-empty list"
        )
    if not isinstance(transitions, list):
        raise ChampionRegistryValidationError(
            "registry transitions must be a list"
        )
    return ChampionRegistry(
        registry_id=row["registry_id"],
        candidates=tuple(_candidate(item) for item in candidates),
        initial_champion_digest=row["initial_champion_digest"],
        transitions=tuple(
            _transition(item) for item in transitions
        ),
    )


def load_registry(
    root: Path = ROOT,
    *,
    registry_path: Path = REGISTRY_PATH,
) -> tuple[dict[str, Any], tuple[ChampionRegistry, ...]]:
    payload = _load(root / registry_path)
    if not isinstance(payload, dict):
        raise ChampionRegistryValidationError(
            "registry root must be an object"
        )
    _strict_keys(
        payload,
        {
            "schema_version",
            "registry_version",
            "task_id",
            "accountability_ref",
            "authority",
            "policy",
            "registries",
        },
        "registry",
    )
    if payload.get("schema_version") != 1:
        raise ChampionRegistryValidationError(
            "schema_version must equal 1"
        )
    if payload.get("task_id") != EXPECTED_TASK:
        raise ChampionRegistryValidationError("task_id drift")
    if payload.get("accountability_ref") != EXPECTED_ACCOUNTABILITY:
        raise ChampionRegistryValidationError(
            "accountability_ref drift"
        )
    if payload.get("authority") != str(REGISTRY_PATH):
        raise ChampionRegistryValidationError(
            "authority path drift"
        )
    if payload.get("policy") != EXPECTED_POLICY:
        raise ChampionRegistryValidationError(
            "champion registry policy drift"
        )
    rows = payload.get("registries")
    if not isinstance(rows, list):
        raise ChampionRegistryValidationError(
            "registries must be a list"
        )
    registries = tuple(_registry(row) for row in rows)
    ids = [item.registry_id for item in registries]
    if len(ids) != len(set(ids)):
        raise ChampionRegistryValidationError(
            "registry IDs must be unique"
        )
    return payload, registries


def _registry_set_digest(
    registries: tuple[ChampionRegistry, ...],
) -> str:
    raw = json.dumps(
        {
            item.registry_id: item.registry_digest
            for item in sorted(
                registries,
                key=lambda row: row.registry_id,
            )
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def validate_repository(
    root: Path = ROOT,
    *,
    registry_path: Path = REGISTRY_PATH,
) -> dict[str, Any]:
    payload, registries = load_registry(
        root,
        registry_path=registry_path,
    )
    return {
        "schema_version": 1,
        "registry_version": payload.get("registry_version"),
        "task_id": EXPECTED_TASK,
        "accountability_ref": EXPECTED_ACCOUNTABILITY,
        "registry_count": len(registries),
        "registry_digest": _registry_set_digest(registries),
        "production_authority": False,
        "valid": True,
    }


def compare_registries(
    root: Path,
    *,
    baseline_path: Path,
    candidate_path: Path = REGISTRY_PATH,
) -> dict[str, Any]:
    _, baseline_rows = load_registry(
        root,
        registry_path=baseline_path,
    )
    _, candidate_rows = load_registry(
        root,
        registry_path=candidate_path,
    )
    before = {item.registry_id: item for item in baseline_rows}
    after = {item.registry_id: item for item in candidate_rows}

    removed_registries = sorted(set(before) - set(after))
    initial_champion_rewritten: list[str] = []
    removed_candidates: list[list[str]] = []
    mutated_candidates: list[list[str]] = []
    rewritten_transitions: list[str] = []
    added_candidates: list[list[str]] = []
    appended_transitions: dict[str, int] = {}

    for registry_id in sorted(set(before) & set(after)):
        old = before[registry_id]
        new = after[registry_id]
        if (
            old.initial_champion_digest
            != new.initial_champion_digest
        ):
            initial_champion_rewritten.append(registry_id)

        old_candidates = {
            (item.candidate_id, item.version): item
            for item in old.candidates
        }
        new_candidates = {
            (item.candidate_id, item.version): item
            for item in new.candidates
        }
        for key in sorted(set(old_candidates) - set(new_candidates)):
            removed_candidates.append([registry_id, *key])
        for key in sorted(set(old_candidates) & set(new_candidates)):
            if (
                old_candidates[key].candidate_digest
                != new_candidates[key].candidate_digest
            ):
                mutated_candidates.append([registry_id, *key])
        for key in sorted(set(new_candidates) - set(old_candidates)):
            added_candidates.append([registry_id, *key])

        old_transitions = tuple(
            item.transition_digest for item in old.transitions
        )
        new_transitions = tuple(
            item.transition_digest for item in new.transitions
        )
        if (
            len(new_transitions) < len(old_transitions)
            or new_transitions[: len(old_transitions)]
            != old_transitions
        ):
            rewritten_transitions.append(registry_id)
        else:
            appended_transitions[registry_id] = (
                len(new_transitions) - len(old_transitions)
            )

    added_registries = sorted(set(after) - set(before))
    accepted = not (
        removed_registries
        or initial_champion_rewritten
        or removed_candidates
        or mutated_candidates
        or rewritten_transitions
    )
    return {
        "accepted": accepted,
        "baseline_digest": _registry_set_digest(baseline_rows),
        "candidate_digest": _registry_set_digest(candidate_rows),
        "removed_registries": removed_registries,
        "added_registries": added_registries,
        "initial_champion_rewritten": initial_champion_rewritten,
        "removed_candidates": removed_candidates,
        "mutated_candidates": mutated_candidates,
        "added_candidates": added_candidates,
        "rewritten_transitions": rewritten_transitions,
        "appended_transitions": appended_transitions,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, default=REGISTRY_PATH)
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--print-summary", action="store_true")
    args = parser.parse_args(argv)
    try:
        report: dict[str, Any] = {
            "registry": validate_repository(
                ROOT,
                registry_path=args.registry,
            )
        }
        if args.baseline is not None:
            lineage = compare_registries(
                ROOT,
                baseline_path=args.baseline,
                candidate_path=args.registry,
            )
            report["lineage"] = lineage
            if lineage["accepted"] is not True:
                raise ChampionRegistryValidationError(
                    "candidate registry rewrites immutable champion history"
                )
        if args.out is not None:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(
                json.dumps(report, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        if args.print_summary:
            print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    except (
        ChampionRegistryValidationError,
        ChampionRegistryError,
        KeyError,
        TypeError,
        ValueError,
    ) as exc:
        print(
            f"P1 champion registry: rejected: {exc}",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
