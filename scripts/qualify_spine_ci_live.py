#!/usr/bin/env python3
"""Collect exact-head required workflow runs and emit authenticated P2 CI evidence."""

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

from skeleton.persistence.spine_ci_qualification import SpineCiQualification
from skeleton.persistence.spine_ci_qualification_verify import (
    SpineCiQualificationVerify,
)
from skeleton.persistence.spine_ci_receipt import SpineCiReceiptBuilder


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _key() -> bytes:
    raw = os.environ.get("P2_CI_ATTESTATION_KEY", "").strip()
    if not raw:
        raise RuntimeError("P2_CI_ATTESTATION_KEY is required")
    return hashlib.sha256(b"p2-ci-attestation\0" + raw.encode("utf-8")).digest()


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


def _fetch_runs(repository: str, head_sha: str) -> list[dict[str, Any]]:
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if not token:
        raise RuntimeError("GITHUB_TOKEN is required to collect CI workflow runs")
    owner_repo = quote(repository, safe="/")
    all_runs: list[dict[str, Any]] = []
    for page in range(1, 11):
        url = (
            f"https://api.github.com/repos/{owner_repo}/actions/runs"
            f"?head_sha={quote(head_sha)}&per_page=100&page={page}"
        )
        request = Request(
            url,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {token}",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "skeleton-p2-ci-qualification",
            },
        )
        with urlopen(request, timeout=30) as response:
            payload = json.load(response)
        rows = payload.get("workflow_runs")
        if not isinstance(rows, list):
            raise RuntimeError("GitHub Actions response is missing workflow_runs")
        all_runs.extend(row for row in rows if isinstance(row, dict))
        if len(rows) < 100:
            break
    return all_runs


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", required=True)
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--evidence-out", required=True)
    parser.add_argument("--runs-json", default="")
    args = parser.parse_args()

    if args.runs_json:
        payload = json.loads(Path(args.runs_json).read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            runs = payload.get("workflow_runs")
        else:
            runs = payload
        if not isinstance(runs, list):
            raise RuntimeError("runs JSON must be a list or contain workflow_runs")
    else:
        runs = _fetch_runs(args.repository, args.expected_head)

    key = _key()
    receipt = SpineCiReceiptBuilder().build(
        workflow_runs=runs,
        expected_head_sha=args.expected_head,
        attest=lambda candidate: _attest(candidate, key),
    )
    qualification = SpineCiQualification().qualify(
        receipt=receipt,
        expected_head_sha=args.expected_head,
        authenticate=lambda candidate: _authenticate(candidate, key),
    )
    verification = SpineCiQualificationVerify().verify(qualification)
    if verification.get("ci_green") is not True:
        raise RuntimeError("CI qualification did not become green")
    if verification.get("merge_authority") is not False:
        raise RuntimeError("CI qualification overclaimed merge authority")

    output = {
        "receipt": receipt,
        "qualification": qualification,
        "verification": verification,
    }
    Path(args.evidence_out).write_text(
        json.dumps(output, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print("p2-ci qualified:", args.expected_head)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
