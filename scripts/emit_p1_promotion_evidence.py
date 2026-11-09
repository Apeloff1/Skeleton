#!/usr/bin/env python3
"""Emit one canonical P1 promotion evidence receipt.

Input evidence is a JSON array of objects with source, digest and optional
category. The emitter never discovers evidence implicitly and never grants
promotion authority; it only serializes a validated exact-head receipt.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

from skeleton.contracts.canonical import EvidenceRef
from skeleton.contracts.promotion_evidence import (
    PromotionEvidenceError,
    PromotionEvidenceReceipt,
)


def _observed_at(value: str) -> datetime:
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("observed-at must be RFC3339") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise argparse.ArgumentTypeError("observed-at must include a timezone")
    return parsed


def _load_evidence(path: Path) -> tuple[EvidenceRef, ...]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PromotionEvidenceError(
            f"cannot load evidence file: {path}"
        ) from exc
    if not isinstance(payload, list):
        raise PromotionEvidenceError("evidence file must contain a JSON array")
    refs: list[EvidenceRef] = []
    for index, item in enumerate(payload):
        if not isinstance(item, dict):
            raise PromotionEvidenceError(
                f"evidence[{index}] must be an object"
            )
        allowed = {"source", "digest", "category"}
        unknown = set(item) - allowed
        if unknown:
            raise PromotionEvidenceError(
                f"evidence[{index}] has unknown fields: {sorted(unknown)}"
            )
        refs.append(
            EvidenceRef(
                source=item.get("source", ""),
                digest=item.get("digest", ""),
                category=item.get("category", "repository_state"),
            )
        )
    return tuple(refs)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Emit an exact-head P1 promotion evidence receipt."
    )
    parser.add_argument("--repository", required=True)
    parser.add_argument("--commit-sha", required=True)
    parser.add_argument("--expected-head")
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--accountability-id", required=True)
    parser.add_argument("--configuration-digest", required=True)
    parser.add_argument("--environment-digest", required=True)
    parser.add_argument("--verifier-id", required=True)
    parser.add_argument("--verifier-digest", required=True)
    parser.add_argument("--test-manifest-digest", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--run-attempt", type=int, required=True)
    parser.add_argument("--observed-at", type=_observed_at, required=True)
    parser.add_argument(
        "--evidence-file",
        type=Path,
        required=True,
        help="JSON array containing explicit evidence references.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        help="Optional output file. Canonical JSON is always printed to stdout.",
    )
    return parser


def emit(args: argparse.Namespace) -> dict[str, object]:
    receipt = PromotionEvidenceReceipt(
        repository=args.repository,
        commit_sha=args.commit_sha,
        task_id=args.task_id,
        accountability_id=args.accountability_id,
        configuration_digest=args.configuration_digest,
        environment_digest=args.environment_digest,
        verifier_id=args.verifier_id,
        verifier_digest=args.verifier_digest,
        test_manifest_digest=args.test_manifest_digest,
        run_id=args.run_id,
        run_attempt=args.run_attempt,
        observed_at=args.observed_at,
        evidence=_load_evidence(args.evidence_file),
    )
    if args.expected_head is not None and not receipt.matches_head(
        args.expected_head
    ):
        raise PromotionEvidenceError(
            "receipt commit does not match expected exact head"
        )
    return {
        **receipt.to_payload(),
        "receipt_digest": receipt.receipt_digest,
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
    except PromotionEvidenceError as exc:
        print(f"p1-promotion-evidence: rejected: {exc}")
        return 1

    rendered = canonical_json(payload)
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
