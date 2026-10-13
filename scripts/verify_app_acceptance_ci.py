#!/usr/bin/env python3
"""Verify product-regression evidence directly against GitHub Actions.

This executable uses a read-only GitHub API token via GITHUB_TOKEN and fetches
the CI run, its jobs and both exact-run artifacts. It cannot be used as a
model-invoked Jeeves write tool. It makes no merges and promotes no weights.
"""
from __future__ import annotations

import argparse
import io
import json
import os
from pathlib import Path
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import zipfile

from skeleton.ai.game_builder.jeeves_acceptance_matrix import JeevesAcceptanceTestMatrix
from skeleton.ai.game_builder.jeeves_appwide_fabric import AppwideInventory, JeevesAppwideError
from skeleton.ai.game_builder.jeeves_acceptance_run_verifier import (
    REPOSITORY, WORKFLOW, JOB_NAMES, verify,
)

API = "https://api.github.com"
MAX_JSON_BYTES = 4 * 1024 * 1024
MAX_ZIP_BYTES = 8 * 1024 * 1024
MAX_JSON_ENTRIES = 1000


def _unique_pairs(pairs):
    value = {}
    for name, item in pairs:
        if name in value:
            raise JeevesAppwideError("duplicate keys in external CI JSON")
        value[name] = item
    return value


def _reject_float_constants(value):
    raise JeevesAppwideError("non-finite external CI JSON: " + str(value))


def _read_json(blob: bytes):
    if not isinstance(blob, bytes) or len(blob) > MAX_JSON_BYTES:
        raise JeevesAppwideError("oversized external CI metadata")
    try:
        return json.loads(blob.decode("utf-8"), object_pairs_hook=_unique_pairs,
                          parse_constant=_reject_float_constants)
    except (UnicodeError, ValueError, TypeError, RecursionError) as exc:
        raise JeevesAppwideError("malformed external CI JSON") from exc


class _DropTokenOnRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        result = super().redirect_request(req, fp, code, msg, headers, newurl)
        if result is None:
            return None
        original = urllib.parse.urlsplit(req.full_url)
        redirected = urllib.parse.urlsplit(result.full_url)
        if redirected.scheme != "https":
            raise JeevesAppwideError("CI artifact redirect requires HTTPS")
        if original.netloc != redirected.netloc:
            result.remove_header("Authorization")
            result.remove_unredirected_header("Authorization")
        return result


class GitHubEvidenceSource:
    """Read-only GitHub REST transport, bounded before any model consumption."""

    def __init__(self, token: str):
        if type(token) is not str or not token.strip() or len(token) > 8192:
            raise JeevesAppwideError("read-only GitHub bearer token required")
        self.token = token
        self.opener = urllib.request.build_opener(_DropTokenOnRedirect())

    def _request(self, path: str, *, limit=MAX_JSON_BYTES):
        if (type(path) is not str or not path.startswith(
                "/repos/" + REPOSITORY + "/actions/") or
            "//" in path or ".." in path or "://" in path or
            type(limit) is not int or limit < 1 or limit > MAX_ZIP_BYTES):
            raise JeevesAppwideError("unapproved GitHub Actions REST path")
        request = urllib.request.Request(
            API + path,
            headers={
                "Authorization": "Bearer " + self.token,
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "Skeleton-Independent-Acceptance-Verifier",
            },
            method="GET",
        )
        try:
            with self.opener.open(request, timeout=30) as response:
                if response.status != 200:
                    raise JeevesAppwideError("GitHub evidence endpoint not successful")
                blob = response.read(limit + 1)
        except (urllib.error.HTTPError, urllib.error.URLError) as exc:
            raise JeevesAppwideError(
                "GitHub independent evidence could not be obtained") from exc
        if len(blob) > limit:
            raise JeevesAppwideError("GitHub CI response exceeds bounded length")
        return blob

    def json(self, path: str):
        return _read_json(self._request(path))

    def artifact(self, artifact_id: int):
        if type(artifact_id) is not int or artifact_id <= 0:
            raise JeevesAppwideError("invalid signed artifact identifier")
        binary = self._request(
            f"/repos/{REPOSITORY}/actions/artifacts/{artifact_id}/zip",
            limit=MAX_ZIP_BYTES,
        )
        try:
            with zipfile.ZipFile(io.BytesIO(binary)) as archive:
                rows = archive.infolist()
                if (len(rows) != 1 or rows[0].is_dir() or
                    rows[0].filename != "app_acceptance_run_evidence.json" or
                    rows[0].file_size > MAX_JSON_BYTES or
                    rows[0].compress_size > MAX_ZIP_BYTES):
                    raise JeevesAppwideError("untrusted CI artifact ZIP structure")
                with archive.open(rows[0], "r") as member:
                    raw = member.read(MAX_JSON_BYTES + 1)
                return _read_json(raw)
        except (zipfile.BadZipFile, RuntimeError, OSError, EOFError) as exc:
            raise JeevesAppwideError("invalid GitHub acceptance artifact ZIP") from exc

    def _page(self, route: str, key: str):
        result = []
        for n in range(1, 4):
            response = self.json(
                route + f"?per_page=100&page={n}")
            if type(response) is not dict or type(response.get(key)) is not list:
                raise JeevesAppwideError("malformed GitHub Actions collection")
            batch = response[key]
            if len(batch) > 100:
                raise JeevesAppwideError("unbounded GitHub Actions pagination")
            result.extend(batch)
            if len(batch) < 100:
                return result
        raise JeevesAppwideError("GitHub Actions pagination exceeds safety budget")

    def load(self, run_id: int):
        if type(run_id) is not int or not 0 < run_id < 2**63:
            raise JeevesAppwideError("valid exact-head CI run ID required")
        prefix = f"/repos/{REPOSITORY}/actions/runs/{run_id}"
        run = self.json(prefix)
        jobs = self._page(prefix + "/jobs", "jobs")
        artifacts = self._page(prefix + "/artifacts", "artifacts")
        data = {}
        for os_label, job in JOB_NAMES.items():
            name = ("app-acceptance-candidates-" +
                    ("ubuntu-24.04" if os_label == "Linux"
                     else "windows-2022") + "-" + str(run_id))
            matched = [a for a in artifacts
                       if type(a) is dict and a.get("name") == name and
                       a.get("expired") is False]
            if len(matched) != 1:
                raise JeevesAppwideError(
                    "required exact-run OS artifact missing or duplicate")
            item = matched[0]
            origin = item.get("workflow_run")
            if origin is not None and (
                type(origin) is not dict or origin.get("id") != run_id
            ):
                raise JeevesAppwideError("artifact belongs to different CI run")
            artifact_id = item.get("id")
            if type(artifact_id) is not int or artifact_id <= 0:
                raise JeevesAppwideError("invalid exact-run artifact identity")
            data[os_label] = self.artifact(artifact_id)
        return run, jobs, data


def measure(repo_root: Path, *, run_id: int, attempt: int, head: str,
            github_token: str):
    repo_root = repo_root.resolve()
    inventory = AppwideInventory(repo_root)
    inventory.scan()
    matrix = JeevesAcceptanceTestMatrix(inventory).overview()
    family_rows = JeevesAcceptanceTestMatrix(inventory).page(limit=42)["families"]
    verified_candidates = [
        {"family_id": row["family_id"], "modules": row["modules"]}
        for row in family_rows if row["execution_tier"] == "ci_smoke"
    ]
    expected = {
        "smoke_families": verified_candidates,
        "family_denominator": matrix["family_denominator"],
        "selected_modules": matrix["selected_modules"],
        "module_source_receipts": matrix["module_source_receipts"],
        "scheduled_test_module_count": matrix["scheduled_test_module_count"],
        "matrix_digest": matrix["digest"],
        "matrix_sha256": matrix["matrix_sha256"],
        "scope_sha256": matrix["scope_sha256"],
    }
    source = GitHubEvidenceSource(github_token)
    run, jobs, by_os = source.load(run_id)
    return verify(head=head, run=run, jobs=jobs, evidence_by_os=by_os,
                  expected_matrix=expected, expected_run_id=run_id,
                  expected_attempt=attempt)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Independently verify source-bound product test candidate CI")
    parser.add_argument("--run-id", type=int, required=True)
    parser.add_argument("--attempt", type=int, default=1)
    parser.add_argument("--head", required=True)
    parser.add_argument("--output", default="build/verified_acceptance_ci.json")
    args = parser.parse_args(argv)
    token = os.environ.get("GITHUB_TOKEN", "")
    if not re.fullmatch("[0-9a-f]{40}", args.head):
        parser.error("--head must be an exact lowercase Git commit SHA")
    root = Path(__file__).resolve().parent.parent
    result = measure(root, run_id=args.run_id, attempt=args.attempt,
                     head=args.head, github_token=token)
    destination = (root / args.output).resolve()
    if not destination.is_relative_to(root):
        raise JeevesAppwideError("verified result must remain within workspace")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n",
                           encoding="utf-8")
    print("Verified independently:", result["independent_ci_execution_verified"])
    print("Exact head:", result["verified_git_head"])
    print("Passed selected modules per OS:",
          result["scheduled_test_modules_independently_confirmed"])
    print("Full app completion still:", result["full_app_completion_percent"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
