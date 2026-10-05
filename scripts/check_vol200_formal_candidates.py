#!/usr/bin/env python3
"""Validate VOL-200 ranked formal candidates and proof-to-test handoff."""
from __future__ import annotations

import json
from pathlib import Path

from skeleton.contracts.formal_candidates import (
    FormalCandidate,
    FormalModelRef,
    ProofToTestHandoff,
    VerifiedProperty,
    rank_formal_candidates,
)
from skeleton.contracts.formal_targets import (
    p0_formal_specifications,
    run_p0_formal_models,
)

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "machine" / "formal_candidate_registry.json"


def _load() -> dict:
    data = json.loads(REGISTRY.read_text(encoding="utf-8"))
    if data.get("schema_version") != "skeleton.formal-candidate-registry.v1":
        raise SystemExit("unexpected formal candidate registry schema")
    if data.get("status") != "active" or data.get("volume_ref") != "VOL-200":
        raise SystemExit("formal candidate registry authority mismatch")
    authority = data.get("authority", {})
    if authority.get("completion_authority") is not False:
        raise SystemExit("registry must not grant completion authority")
    if authority.get("verification_authority") is not False:
        raise SystemExit("registry must not grant verification authority")
    return data


def _candidate(row: dict) -> FormalCandidate:
    return FormalCandidate(
        candidate_id=row["candidate_id"],
        spec_id=row["spec_id"],
        title=row["title"],
        consequence_rank=row["consequence_rank"],
        ambiguity_rank=row["ambiguity_rank"],
        concurrency_ambiguity=row["concurrency_ambiguity"],
        authority_ambiguity=row["authority_ambiguity"],
        recovery_ambiguity=row["recovery_ambiguity"],
        estimated_cost_rank=row["estimated_cost_rank"],
        implementation_test_targets=tuple(row["implementation_test_targets"]),
        assumption_ids=tuple(row["assumption_ids"]),
    )


def main() -> int:
    data = _load()
    policy = data["selection_policy"]
    candidates = tuple(_candidate(row) for row in data["candidates"])
    ranked = rank_formal_candidates(
        candidates,
        minimum_score=policy["minimum_score"],
        maximum_selected=policy["maximum_selected"],
    )
    ranked_ids = [item.candidate_id for item in ranked]
    if ranked_ids != data["expected_ranked_candidate_ids"]:
        raise SystemExit(
            f"formal candidate ranking drift: {ranked_ids!r}"
        )

    specs = {spec.spec_id: spec for spec in p0_formal_specifications()}
    reports = {report.spec_id: report for report in run_p0_formal_models()}
    if set(specs) != set(reports):
        raise SystemExit("formal specification/report inventory drift")

    handoff_digests: list[str] = []
    for candidate in ranked:
        spec = specs.get(candidate.spec_id)
        report = reports.get(candidate.spec_id)
        if spec is None or report is None:
            raise SystemExit(f"missing formal target {candidate.spec_id}")
        if report.spec_digest != spec.digest:
            raise SystemExit(f"formal report/spec digest drift: {candidate.spec_id}")
        if not report.all_obligations_proved_within_model:
            raise SystemExit(f"formal target is not fully proved within model: {candidate.spec_id}")

        actual_assumption_ids = tuple(
            sorted(item.assumption_id for item in spec.assumptions)
        )
        if candidate.assumption_ids != actual_assumption_ids:
            raise SystemExit(
                f"candidate assumption inventory drift: {candidate.candidate_id}"
            )

        model_ref = FormalModelRef(
            candidate_id=candidate.candidate_id,
            spec_id=spec.spec_id,
            specification_digest=spec.digest,
            implementation_binding_digests=tuple(
                item.digest for item in spec.implementation_bindings
            ),
            assumption_digests=tuple(item.digest for item in spec.assumptions),
        )
        properties = tuple(
            VerifiedProperty(
                property_id=f"{candidate.candidate_id}.{result.obligation_id}",
                candidate_id=candidate.candidate_id,
                model_ref_digest=model_ref.digest,
                proof_result_digest=result.digest,
                proof_status=result.status.value,
                assumption_digests=model_ref.assumption_digests,
                implementation_test_targets=candidate.implementation_test_targets,
            )
            for result in report.results
        )
        handoff = ProofToTestHandoff(model_ref, properties)
        handoff.verify_test_inventory(candidate.implementation_test_targets)
        for target in handoff.implementation_test_targets:
            path_text, _, test_name = target.partition("::")
            path = ROOT / path_text
            if not path.is_file():
                raise SystemExit(f"formal handoff test file missing: {path_text}")
            if not test_name:
                raise SystemExit(f"formal handoff test symbol missing: {target}")
            source = path.read_text(encoding="utf-8")
            if f"def {test_name}(" not in source:
                raise SystemExit(f"formal handoff test symbol drift: {target}")
        handoff_digests.append(handoff.digest)

    print(
        json.dumps(
            {
                "status": "valid",
                "volume_ref": "VOL-200",
                "ranked_candidates": ranked_ids,
                "handoff_digests": handoff_digests,
                "completion_authority": False,
                "verification_authority": False,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
