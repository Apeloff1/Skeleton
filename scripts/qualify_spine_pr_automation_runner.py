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
from urllib.parse import quote
from urllib.request import Request, urlopen

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


def _fetch_workflow_run(repository: str, run_id: int) -> dict[str, Any]:
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if not token:
        raise RuntimeError(
            "GITHUB_TOKEN is required to verify the source workflow run"
        )
    owner_repo = quote(repository, safe="/")
    url = (
        f"https://api.github.com/repos/{owner_repo}/actions/runs/{run_id}"
    )
    request = Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "skeleton-p2-pr-automation-qualification",
        },
    )
    with urlopen(request, timeout=30) as response:
        payload = json.load(response)
    if not isinstance(payload, dict):
        raise RuntimeError("source workflow run response is not an object")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--source-run-id", required=True, type=int)
    parser.add_argument("--source-run-attempt", required=True, type=int)
    parser.add_argument("--pr-number", type=int)
    parser.add_argument("--run-id", required=True, type=int)
    parser.add_argument("--run-attempt", required=True, type=int)
    parser.add_argument("--mode", required=True, choices=("observe", "apply"))
    parser.add_argument("--evidence-out", required=True)
    args = parser.parse_args()

    report = json.loads(Path(args.report).read_text(encoding="utf-8"))
    pr_number = args.pr_number
    if pr_number is None:
        targets = report.get("targets") if isinstance(report, dict) else None
        target_rows = targets.get("targets") if isinstance(targets, dict) else None
        if (
            not isinstance(target_rows, list)
            or len(target_rows) != 1
            or not isinstance(target_rows[0], dict)
            or isinstance(target_rows[0].get("number"), bool)
            or not isinstance(target_rows[0].get("number"), int)
            or target_rows[0]["number"] < 1
        ):
            raise RuntimeError(
                "runner report must contain exactly one positive target PR when --pr-number is omitted"
            )
        pr_number = target_rows[0]["number"]
    source_run = _fetch_workflow_run(
        args.repository,
        args.source_run_id,
    )
    automation_run = _fetch_workflow_run(
        args.repository,
        args.run_id,
    )
    if source_run.get("run_attempt") != args.source_run_attempt:
        raise RuntimeError(
            "source workflow run attempt changed before qualification"
        )
    if automation_run.get("run_attempt") != args.run_attempt:
        raise RuntimeError(
            "PR Automation producer run attempt changed before qualification"
        )
    key = _key()
    receipt = SpinePrAutomationReceiptBuilder().build(
        report=report,
        expected_repository=args.repository,
        source_run=source_run,
        automation_run=automation_run,
        expected_source_run_attempt=args.source_run_attempt,
        expected_head_sha=args.expected_head,
        expected_pr_number=pr_number,
        run_id=args.run_id,
        run_attempt=args.run_attempt,
        mode=args.mode,
        attest=lambda candidate: _attest(candidate, key),
    )
    qualification = SpinePrAutomationQualification().qualify(
        receipt=receipt,
        expected_head_sha=args.expected_head,
        expected_pr_number=pr_number,
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
        pr_number,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
