#!/usr/bin/env python3
"""Build the exact-head P1-PROM-03 signed promotion decision."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

from skeleton.contracts.p1_failure_journeys import (
    P1FailureJourneyDecision,
    P1FailureJourneyError,
)
from skeleton.contracts.p1_promotion_decision import (
    P1PromotionAttestation,
    P1PromotionDecisionError,
    decide_p1_promotion,
    p1_promotion_subject_payload,
)
from scripts.check_p1_promotion_decision import (
    EXECUTION_MAP_PATH,
    ROOT,
    validate_repository,
)


class PromotionDecisionBuildError(RuntimeError):
    """PROM-03 decision input cannot be safely reconstructed."""


def _load(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PromotionDecisionBuildError(f"cannot read {path}") from exc


def _prom02(payload: object) -> P1FailureJourneyDecision:
    if not isinstance(payload, dict):
        raise PromotionDecisionBuildError("PROM-02 bundle must be an object")
    try:
        decision = P1FailureJourneyDecision(
            accepted=payload.get("accepted"),
            reasons=tuple(payload.get("reasons") or ()),
            repository=payload.get("repository"),
            commit_sha=payload.get("commit_sha"),
            prom01_bundle_digest=payload.get("prom01_bundle_digest"),
            prom01_promotion_ready=payload.get("prom01_promotion_ready"),
            required_families=tuple(payload.get("required_families") or ()),
            required_journey_classes=tuple(
                payload.get("required_journey_classes") or ()
            ),
            observation_digests=tuple(
                payload.get("observation_digests") or ()
            ),
        )
    except (P1FailureJourneyError, TypeError) as exc:
        raise PromotionDecisionBuildError(
            "PROM-02 bundle violates contract"
        ) from exc
    claimed = payload.get("decision_digest")
    if claimed != decision.decision_digest:
        raise PromotionDecisionBuildError("PROM-02 decision digest mismatch")
    return decision


def _attestation(path: Path | None) -> P1PromotionAttestation | None:
    if path is None:
        return None
    payload = _load(path)
    if not isinstance(payload, dict):
        raise PromotionDecisionBuildError(
            f"attestation {path} must be an object"
        )
    try:
        attestation = P1PromotionAttestation(
            phase=payload.get("phase"),
            repository=payload.get("repository"),
            commit_sha=payload.get("commit_sha"),
            subject_digest=payload.get("subject_digest"),
            signer_id=payload.get("signer_id"),
            signer_type=payload.get("signer_type"),
            role=payload.get("role"),
            signed_at_utc=payload.get("signed_at_utc"),
            signature_method=payload.get("signature_method"),
            signature_ref=payload.get("signature_ref"),
            verifier_digest=payload.get("verifier_digest"),
            evidence_digest=payload.get("evidence_digest"),
        )
    except (P1PromotionDecisionError, TypeError) as exc:
        raise PromotionDecisionBuildError(
            f"attestation {path} violates contract"
        ) from exc
    claimed = payload.get("attestation_digest")
    if claimed != attestation.attestation_digest:
        raise PromotionDecisionBuildError(
            f"attestation {path} digest mismatch"
        )
    return attestation


def build(
    *,
    repository: str,
    commit_sha: str,
    prom02_bundle_path: Path,
    implementation_attestation_path: Path | None = None,
    verification_attestation_path: Path | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    summary = validate_repository(ROOT)
    execution_map = _load(ROOT / EXECUTION_MAP_PATH)
    scope = execution_map["scope_summary"]
    prom02 = _prom02(_load(prom02_bundle_path))

    deferred = tuple(scope["deferred_volume_refs"])
    subject = p1_promotion_subject_payload(
        repository=repository,
        commit_sha=commit_sha,
        prom02_decision_digest=prom02.decision_digest,
        primary_volume_count=scope["primary_p1_frontier_volume_count"],
        masterplan_volume_count=scope["masterplan_volume_count"],
        deferred_volume_refs=deferred,
    )
    implementation = _attestation(implementation_attestation_path)
    verification = _attestation(verification_attestation_path)
    decision = decide_p1_promotion(
        prom02_bundle=prom02,
        expected_repository=repository,
        expected_head=commit_sha,
        primary_volume_count=scope["primary_p1_frontier_volume_count"],
        masterplan_volume_count=scope["masterplan_volume_count"],
        deferred_volume_refs=deferred,
        implementation_attestation=implementation,
        verification_attestation=verification,
    )
    if decision.deferred_volume_count != summary["deferred_volume_count"]:
        raise PromotionDecisionBuildError(
            "PROM-03 deferred scope summary mismatch"
        )
    payload = {
        **decision.payload(),
        "decision_digest": decision.decision_digest,
    }
    return subject, payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--commit-sha", required=True)
    parser.add_argument("--prom02-bundle", type=Path, required=True)
    parser.add_argument("--implementation-attestation", type=Path)
    parser.add_argument("--verification-attestation", type=Path)
    parser.add_argument("--subject-out", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument(
        "--require-promotion",
        action="store_true",
        help="Exit non-zero when the structurally valid decision is rejection.",
    )
    return parser


def _write(path: Path | None, payload: dict[str, Any]) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        subject, decision = build(
            repository=args.repository,
            commit_sha=args.commit_sha,
            prom02_bundle_path=args.prom02_bundle,
            implementation_attestation_path=args.implementation_attestation,
            verification_attestation_path=args.verification_attestation,
        )
    except (
        PromotionDecisionBuildError,
        P1PromotionDecisionError,
        KeyError,
        TypeError,
    ) as exc:
        print(f"P1 signed promotion decision: rejected: {exc}", file=sys.stderr)
        return 1

    _write(args.subject_out, subject)
    _write(args.out, decision)
    print(json.dumps(decision, indent=2, sort_keys=True))
    if args.require_promotion and decision["promoted"] is not True:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
