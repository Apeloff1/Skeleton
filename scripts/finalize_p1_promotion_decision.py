#!/usr/bin/env python3
"""Finalize an exact-head PROM-03 signed promotion or explicit rejection."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

from skeleton.contracts.p1_failure_journeys import P1FailureJourneyDecision
from skeleton.contracts.p1_promotion_decision import (
    IndependentSignatureObservation,
    P1PromotionDecisionError,
    P1PromotionIntent,
    finalize_p1_promotion_decision,
)


ROOT = Path(__file__).resolve().parents[1]
MAP_PATH = Path("machine/ai_p1_execution_map.json")


class PromotionDecisionBuildError(RuntimeError):
    pass


def _load(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PromotionDecisionBuildError(
            f"cannot read {path}"
        ) from exc


def _prom02(raw: Any) -> P1FailureJourneyDecision:
    if not isinstance(raw, dict):
        raise PromotionDecisionBuildError(
            "PROM-02 bundle must be an object"
        )
    return P1FailureJourneyDecision(
        accepted=raw.get("accepted"),
        reasons=tuple(raw.get("reasons") or ()),
        repository=raw.get("repository"),
        commit_sha=raw.get("commit_sha"),
        prom01_bundle_digest=raw.get("prom01_bundle_digest"),
        prom01_promotion_ready=raw.get(
            "prom01_promotion_ready"
        ),
        required_families=tuple(
            raw.get("required_families") or ()
        ),
        required_journey_classes=tuple(
            raw.get("required_journey_classes") or ()
        ),
        observation_digests=tuple(
            raw.get("observation_digests") or ()
        ),
    )


def _deferred_refs(raw: Any) -> tuple[str, ...]:
    if not isinstance(raw, dict):
        raise PromotionDecisionBuildError(
            "execution map must be an object"
        )
    scope = raw.get("scope_summary")
    if not isinstance(scope, dict):
        raise PromotionDecisionBuildError(
            "execution map scope_summary missing"
        )
    refs = scope.get("deferred_volume_refs")
    count = scope.get("deferred_volume_count")
    if not isinstance(refs, list) or count != len(refs):
        raise PromotionDecisionBuildError(
            "deferred scope malformed"
        )
    return tuple(str(item) for item in refs)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--intent", type=Path, required=True)
    parser.add_argument(
        "--prom02-bundle",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--signature-observation",
        type=Path,
    )
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--refs-out", type=Path, required=True)
    args = parser.parse_args(argv)

    try:
        intent = P1PromotionIntent.from_mapping(
            _load(args.intent)
        )
        prom02 = _prom02(_load(args.prom02_bundle))
        signature = (
            None
            if args.signature_observation is None
            else IndependentSignatureObservation.from_mapping(
                _load(args.signature_observation)
            )
        )
        decision = finalize_p1_promotion_decision(
            intent=intent,
            prom02=prom02,
            expected_deferred_volume_refs=_deferred_refs(
                _load(ROOT / MAP_PATH)
            ),
            signature=signature,
        )
    except (
        PromotionDecisionBuildError,
        P1PromotionDecisionError,
        KeyError,
        TypeError,
        ValueError,
    ) as exc:
        print(
            f"P1 promotion decision: rejected: {exc}",
            file=sys.stderr,
        )
        return 1

    if not decision.accepted:
        print(
            "P1 promotion decision: invalid: "
            + ",".join(decision.reasons),
            file=sys.stderr,
        )
        return 1

    evidence = decision.accepted_evidence_ref()
    payload = {
        **decision.payload(),
        "decision_digest": decision.decision_digest,
    }
    refs = [
        {
            "source": evidence.source,
            "digest": evidence.digest,
            "category": evidence.category,
        }
    ]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.refs_out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    args.refs_out.write_text(
        json.dumps(refs, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        "P1 promotion decision:",
        decision.disposition.value,
        f"signed={decision.signed}",
        f"granted={decision.promotion_granted}",
        decision.decision_digest,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
