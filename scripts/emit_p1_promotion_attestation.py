#!/usr/bin/env python3
"""Emit one identity-bound P1-PROM-03 promotion attestation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from skeleton.contracts.p1_promotion_decision import (
    P1PromotionAttestation,
    P1PromotionDecisionError,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=("implementation", "verification"), required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--commit-sha", required=True)
    parser.add_argument("--subject-digest", required=True)
    parser.add_argument("--signer-id", required=True)
    parser.add_argument("--signer-type", choices=("human", "agent", "ci", "service"), required=True)
    parser.add_argument("--role", required=True)
    parser.add_argument("--signed-at-utc", required=True)
    parser.add_argument(
        "--signature-method",
        choices=("github_identity", "git_gpg", "git_ssh", "sigstore", "ci_oidc"),
        required=True,
    )
    parser.add_argument("--signature-ref", required=True)
    parser.add_argument("--verifier-digest", required=True)
    parser.add_argument("--evidence-digest", required=True)
    parser.add_argument("--out", type=Path)
    return parser


def emit(args: argparse.Namespace) -> dict[str, object]:
    attestation = P1PromotionAttestation(
        phase=args.phase,
        repository=args.repository,
        commit_sha=args.commit_sha,
        subject_digest=args.subject_digest,
        signer_id=args.signer_id,
        signer_type=args.signer_type,
        role=args.role,
        signed_at_utc=args.signed_at_utc,
        signature_method=args.signature_method,
        signature_ref=args.signature_ref,
        verifier_digest=args.verifier_digest,
        evidence_digest=args.evidence_digest,
    )
    return {
        **attestation.payload(),
        "attestation_digest": attestation.attestation_digest,
    }


def canonical_json(payload: dict[str, object]) -> str:
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        payload = emit(args)
    except P1PromotionDecisionError as exc:
        print(f"p1-promotion-attestation: rejected: {exc}")
        return 1

    rendered = canonical_json(payload)
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
