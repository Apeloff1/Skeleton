"""Dragon adversarial probes against all 50 added game-production contracts."""
from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from typing import Any

from .production_quality import QualityGateError, _digest
from .production_expanded_gates import SPECS, audit_expanded_studio, verify_expanded_studio
from .production_expanded_assurance import verify_84_structure


def challenge_84_verifiers(bundle: Mapping[str, Any]) -> dict[str, Any]:
    """Mutate source-bound domain observations and verify rejection, never persist."""
    baseline = audit_expanded_studio(bundle)
    verify_expanded_studio(bundle, baseline)
    verify_84_structure(baseline)
    if not baseline["candidate_passed"]:
        raise QualityGateError("Dragon requires a passing source candidate baseline")
    observations = []
    for spec in SPECS:
        altered = deepcopy(dict(bundle))
        evidence = altered["studio"]["expanded"][spec.name]
        if spec.mode == "timing":
            evidence["samples"][0]["target_end_ms"] = 10000
        elif spec.mode == "physics":
            evidence["samples"][0]["measured"] = 1000
        elif spec.mode == "graph":
            evidence["nodes"][0]["next"] = ["missing_canon_node"]
        elif spec.mode == "asset":
            evidence["assets"][0]["deviation"] = spec.threshold + 100
        else:
            evidence["attempts"][0]["replay_sha256"] = "f" * 64
        report = audit_expanded_studio(altered)
        gate = next(g for g in report["gates"] if g["name"] == spec.name)
        if gate["passed"]:
            raise QualityGateError("Dragon challenge not detected: " + spec.name)
        observations.append({
            "gate": spec.name,
            "rejected": True,
            "finding_codes": sorted({f["code"] for f in gate["findings"]}),
            "mutated_evidence_sha256": gate["evidence_digest"],
        })
    forged = deepcopy(baseline)
    forged["candidate_passed"] = False
    try:
        verify_84_structure(forged)
    except QualityGateError:
        rejected_summary = True
    else:
        raise QualityGateError("structural verifier accepted fabricated summary")
    forged = deepcopy(baseline)
    forged["gates"][-1]["passed"] = False
    try:
        verify_expanded_studio(bundle, forged)
    except QualityGateError:
        rejected_source = True
    else:
        raise QualityGateError("source verifier accepted fabricated component")
    result = {
        "schema": "game.studio.production_84_dragon.v1",
        "source_sha256": baseline["source_digest"],
        "evidence_sha256": baseline["evidence_digest"],
        "rejected_count": len(observations),
        "probes": observations,
        "summary_forgery_rejected": rejected_summary,
        "source_forgery_rejected": rejected_source,
        "weights_updated": False,
        "production_certified": False,
    }
    return {**result, "receipt_digest": _digest(result)}
