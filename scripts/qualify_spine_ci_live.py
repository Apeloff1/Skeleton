#!/usr/bin/env python3
"""Collect exact-head required workflow runs and emit authenticated P2 CI evidence."""

from __future__ import annotations

import argparse
import base64
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
from skeleton.persistence.spine_ci_receipt import (
    SpineCiReceiptBuilder,
    SpineCiReceiptIncompleteError,
)
from skeleton.persistence.spine_ci_policy import (
    REQUIRED_CHECKS,
    REQUIRED_CHECK_WORKFLOWS,
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


def _fetch_run(repository: str, run_id: int) -> dict[str, Any]:
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if not token:
        raise RuntimeError("GITHUB_TOKEN is required to verify CI producer run")
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
            "User-Agent": "skeleton-p2-ci-qualification",
        },
    )
    with urlopen(request, timeout=30) as response:
        payload = json.load(response)
    if not isinstance(payload, dict):
        raise RuntimeError("CI producer workflow response is not an object")
    return payload


def _fetch_workflow_definition_digest(
    repository: str,
    *,
    path: str,
    ref: str,
) -> str:
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if not token:
        raise RuntimeError(
            "GITHUB_TOKEN is required to verify workflow definitions"
        )
    owner_repo = quote(repository, safe="/")
    encoded_path = quote(path, safe="/")
    encoded_ref = quote(ref, safe="")
    url = (
        f"https://api.github.com/repos/{owner_repo}/contents/"
        f"{encoded_path}?ref={encoded_ref}"
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
    if (
        not isinstance(payload, dict)
        or payload.get("encoding") != "base64"
        or not isinstance(payload.get("content"), str)
    ):
        raise RuntimeError("workflow definition response is not base64 content")
    try:
        content = base64.b64decode(payload["content"])
    except Exception as exc:
        raise RuntimeError("workflow definition base64 is invalid") from exc
    return hashlib.sha256(content).hexdigest()


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
    parser.add_argument("--producer-run-id", required=True, type=int)
    parser.add_argument("--producer-run-attempt", required=True, type=int)
    parser.add_argument("--producer-branch", required=True)
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--evidence-out", required=True)
    parser.add_argument("--runs-json", default="")
    parser.add_argument(
        "--allow-incomplete",
        action="store_true",
        help="return exit code 3 instead of failing while the exact-head catalog is incomplete",
    )
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

    producer_run = _fetch_run(
        args.repository,
        args.producer_run_id,
    )
    if producer_run.get("run_attempt") != args.producer_run_attempt:
        raise RuntimeError(
            "CI producer run attempt changed before qualification"
        )
    trusted_head = producer_run.get("head_sha")
    if not isinstance(trusted_head, str) or len(trusted_head) != 40:
        raise RuntimeError("CI producer head SHA is invalid")
    workflow_definitions: dict[str, dict[str, str]] = {}
    for name in REQUIRED_CHECKS:
        path = REQUIRED_CHECK_WORKFLOWS[name]
        workflow_definitions[name] = {
            "head_digest": _fetch_workflow_definition_digest(
                args.repository,
                path=path,
                ref=args.expected_head,
            ),
            "trusted_digest": _fetch_workflow_definition_digest(
                args.repository,
                path=path,
                ref=trusted_head,
            ),
        }

    key = _key()
    try:
        receipt = SpineCiReceiptBuilder().build(
            workflow_runs=runs,
            workflow_definitions=workflow_definitions,
            expected_repository=args.repository,
            producer_run=producer_run,
            expected_producer_run_id=args.producer_run_id,
            expected_producer_run_attempt=args.producer_run_attempt,
            expected_producer_branch=args.producer_branch,
            expected_head_sha=args.expected_head,
            attest=lambda candidate: _attest(candidate, key),
        )
    except SpineCiReceiptIncompleteError as exc:
        if args.allow_incomplete:
            print(f"p2-ci evidence not emitted: {exc}")
            return 3
        raise
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
