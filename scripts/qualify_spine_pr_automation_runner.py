#!/usr/bin/env python3
"""Convert one trusted PR Automation runner report into authenticated P2 evidence."""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
from pathlib import Path
from typing import Any

from skeleton.persistence.spine_pr_automation_qualification import (
    SpinePrAutomationQualification,
)
from skeleton.persistence.spine_pr_automation_qualification_verify import (
    SpinePrAutomationQualificationVerify,
)
from skeleton.persistence.spine_pr_automation_receipt import (
    SpinePrAutomationReceiptBuilder,
)


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _key() -> bytes:
    raw = os.environ.get("P2_PR_AUTOMATION_ATTESTATION_KEY", "").strip()
    if not raw:
        raise RuntimeError("P2_PR_AUTOMATION_ATTESTATION_KEY is required")
    return hashlib.sha256(
        b"p2-pr-automation-attestation\0" + raw.encode("utf-8")
    ).digest()


def _attest(receipt: dict[str, Any], key: bytes) -> str:
    payload = {name: value for name, value in receipt.items() if name != "attestation_digest"}
    return hmac.new(key, _canonical(payload), hashlib.sha256).hexdigest()


def _authenticate(receipt: dict[str, Any], key: bytes) -> bool:
    supplied = receipt.get("attestation_digest")
    return (
        isinstance(supplied, str)
        and len(supplied) == 64
        and hmac.compare_digest(supplied, _attest(receipt, key))
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", required=True)
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--pr-number", required=True, type=int)
    parser.add_argument("--run-id", required=True, type=int)
    parser.add_argument("--run-attempt", required=True, type=int)
    parser.add_argument("--mode", required=True, choices=("observe", "apply"))
    parser.add_argument("--evidence-out", required=True)
    args = parser.parse_args()

    report = json.loads(Path(args.report).read_text(encoding="utf-8"))
    key = _key()
    receipt = SpinePrAutomationReceiptBuilder().build(
        report=report,
        expected_head_sha=args.expected_head,
        expected_pr_number=args.pr_number,
        run_id=args.run_id,
        run_attempt=args.run_attempt,
        mode=args.mode,
        attest=lambda candidate: _attest(candidate, key),
    )
    qualification = SpinePrAutomationQualification().qualify(
        receipt=receipt,
        expected_head_sha=args.expected_head,
        expected_pr_number=args.pr_number,
        authenticate=lambda candidate: _authenticate(candidate, key),
    )
    verification = SpinePrAutomationQualificationVerify().verify(qualification)
    if verification.get("pr_automation_operational_green") is not True:
        raise RuntimeError("PR Automation qualification did not become green")
    if verification.get("merge_authority") is not False:
        raise RuntimeError("PR Automation qualification overclaimed merge authority")

    output = {
        "receipt": receipt,
        "qualification": qualification,
        "verification": verification,
    }
    Path(args.evidence_out).write_text(
        json.dumps(output, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        "p2-pr-automation qualified:",
        args.expected_head,
        "pr=",
        args.pr_number,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
