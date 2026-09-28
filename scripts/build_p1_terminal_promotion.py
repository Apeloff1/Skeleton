#!/usr/bin/env python3
"""Build the exact-head P1-PROM-03 terminal promotion decision."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

from skeleton.contracts.canonical import EvidenceRef
from skeleton.contracts.p1_terminal_promotion import (
    IndependentPromotionAttestation,
    P1PromotionDecisionError,
    decide_p1_terminal_promotion,
)
from scripts.check_p1_terminal_promotion_policy import (
    POLICY_PATH,
    ROOT,
    validate_repository,
)


class TerminalPromotionBuildError(RuntimeError):
    pass


def _load(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise TerminalPromotionBuildError(f"cannot read {path}") from exc


def _evidence_refs(raw: object) -> tuple[EvidenceRef, ...]:
    if not isinstance(raw, list):
        raise TerminalPromotionBuildError(
            "attestation evidence_refs must be a list"
        )
    refs = []
    for row in raw:
        if not isinstance(row, dict):
            raise TerminalPromotionBuildError(
                "attestation evidence ref must be object"
            )
        refs.append(
            EvidenceRef(
                source=row["source"],
                digest=row["digest"],
                category=row["category"],
            )
        )
    return tuple(refs)


def _attestation(path: Path | None) -> IndependentPromotionAttestation | None:
    if path is None:
        return None
    raw = _load(path)
    if not isinstance(raw, dict):
        raise TerminalPromotionBuildError(
            "promotion attestation must be an object"
        )
    return IndependentPromotionAttestation(
        repository=raw["repository"],
        commit_sha=raw["commit_sha"],
        signer_id=raw["signer_id"],
        signer_type=raw["signer_type"],
        role=raw["role"],
        signature_method=raw["signature_method"],
        signature_ref=raw.get("signature_ref"),
        subject_digest=raw["subject_digest"],
        independent=raw["independent"],
        evidence_refs=_evidence_refs(raw["evidence_refs"]),
        task_id=raw.get("task_id", "P1-PROM-03"),
        accountability_id=raw.get(
            "accountability_id",
            "ACC-P1-PROM-03",
        ),
    )


def build_decision(
    *,
    repository: str,
    commit_sha: str,
    prom01_bundle_path: Path,
    prom02_bundle_path: Path,
    attestation_path: Path | None,
) -> tuple[dict[str, Any], list[dict[str, str]]]:
    validate_repository(ROOT)
    policy = _load(ROOT / POLICY_PATH)
    prom01 = _load(prom01_bundle_path)
    prom02 = _load(prom02_bundle_path)
    if not isinstance(policy, dict):
        raise TerminalPromotionBuildError("policy must be object")
    if not isinstance(prom01, dict):
        raise TerminalPromotionBuildError("PROM-01 bundle must be object")
    if not isinstance(prom02, dict):
        raise TerminalPromotionBuildError("PROM-02 bundle must be object")

    decision = decide_p1_terminal_promotion(
        prom01_bundle=prom01,
        prom02_bundle=prom02,
        expected_repository=repository,
        expected_head=commit_sha,
        implementation_signer_id=policy["implementation_signer_id"],
        attestation=_attestation(attestation_path),
    )
    if not decision.valid:
        raise TerminalPromotionBuildError(
            "terminal promotion decision is structurally invalid: "
            + ",".join(decision.reasons)
        )
    evidence = decision.decision_evidence_ref()
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
    return payload, refs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--commit-sha", required=True)
    parser.add_argument("--prom01-bundle", type=Path, required=True)
    parser.add_argument("--prom02-bundle", type=Path, required=True)
    parser.add_argument("--attestation", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--refs-out", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        payload, refs = build_decision(
            repository=args.repository,
            commit_sha=args.commit_sha,
            prom01_bundle_path=args.prom01_bundle,
            prom02_bundle_path=args.prom02_bundle,
            attestation_path=args.attestation,
        )
    except (
        TerminalPromotionBuildError,
        P1PromotionDecisionError,
        KeyError,
        TypeError,
        ValueError,
    ) as exc:
        print(
            f"P1 terminal promotion decision: rejected: {exc}",
            file=sys.stderr,
        )
        return 1

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
        "P1 terminal promotion decision:",
        f"outcome={payload['outcome']}",
        f"signed={payload['signed_promotion']}",
        f"digest={payload['decision_digest']}",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
