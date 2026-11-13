#!/usr/bin/env python3
"""Fail-closed, trusted-base check for explicit GitHub PR merge prohibitions.

Run only from a trusted base checkout in pull_request_target. This script never
executes or checks out the pull request head. A successful check is not itself
merge approval: repository rules must separately require this named check.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import sys
import unicodedata
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from skeleton.pr_automation.automerge_model import has_explicit_merge_hold

MAX_EVENT_BYTES = 4 * 1024 * 1024
MAX_API_BYTES = 2 * 1024 * 1024
REPOSITORY_RE = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\Z")
SHA_RE = re.compile(r"[0-9a-f]{40}\Z")
# A merge restriction is not advisory. Both the trusted-target gate and
# the separate auto-merge policy must enforce the current live labels.
EXPLICIT_HOLD_LABELS = frozenset({
    "do-not-merge",
    "no-merge",
    "security-hold",
    "release-hold",
    "automerge:off",
    "do-not-auto-merge",
})


class MergeHoldGateError(ValueError):
    """Invalid, stale or explicitly held pull-request authority."""


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise MergeHoldGateError("duplicate JSON key")
        result[key] = value
    return result


def _decode_json(raw: bytes, *, maximum: int) -> dict[str, object]:
    if len(raw) > maximum:
        raise MergeHoldGateError("metadata exceeds bounded size")
    try:
        value = json.loads(raw.decode("utf-8", errors="strict"), object_pairs_hook=_unique_object)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise MergeHoldGateError("malformed JSON metadata") from exc
    if not isinstance(value, dict):
        raise MergeHoldGateError("metadata must be an object")
    return value


def _object(value: object, field: str) -> dict:
    if not isinstance(value, dict):
        raise MergeHoldGateError(f"{field} must be an object")
    return value


def _text(value: object, field: str, *, optional: bool = False) -> str | None:
    if value is None and optional:
        return None
    if type(value) is not str:
        raise MergeHoldGateError(f"{field} must be text")
    return value


def _pr_fields(payload: object, repository: str, number: int) -> tuple[str, str | None, str, str, tuple[str, ...]]:
    pr = _object(payload, "pull_request")
    if type(pr.get("number")) is not int or pr["number"] != number:
        raise MergeHoldGateError("PR number mismatch")
    if pr.get("state") != "open":
        raise MergeHoldGateError("PR is not open")
    title = _text(pr.get("title"), "title")
    body = _text(pr.get("body"), "body", optional=True)
    head = _object(pr.get("head"), "head")
    base = _object(pr.get("base"), "base")
    base_repo = _object(base.get("repo"), "base.repo")
    if base_repo.get("full_name") != repository or base.get("ref") != "main":
        raise MergeHoldGateError("unexpected PR base repository or branch")
    head_sha = head.get("sha")
    base_sha = base.get("sha")
    if not isinstance(head_sha, str) or not SHA_RE.fullmatch(head_sha):
        raise MergeHoldGateError("invalid PR head SHA")
    if not isinstance(base_sha, str) or not SHA_RE.fullmatch(base_sha):
        raise MergeHoldGateError("invalid PR base SHA")
    # GitHub's live pull-request API always provides a label array. Reject
    # absent, malformed or oversized labels instead of quietly treating them
    # as an empty allowlist (which would make a hold fail open).
    labels = pr.get("labels")
    if not isinstance(labels, list) or len(labels) > 100:
        raise MergeHoldGateError("PR labels are absent or malformed")
    label_names: set[str] = set()
    for label in labels:
        item = _object(label, "label")
        name = _text(item.get("name"), "label name")
        if not isinstance(name, str) or not 1 <= len(name) <= 100:
            raise MergeHoldGateError("invalid PR label name")
        if any(ord(ch) < 32 or ord(ch) == 127 for ch in name):
            raise MergeHoldGateError("PR label contains control characters")
        label_names.add(unicodedata.normalize("NFKC", name).casefold().strip())
    return title, body, head_sha, base_sha, tuple(sorted(label_names))


def validate_current_pr(event: dict, current_pr: dict, repository: str) -> None:
    """Reject a hold or any event/live PR authority mismatch."""
    if not REPOSITORY_RE.fullmatch(repository):
        raise MergeHoldGateError("invalid repository identifier")
    event_repo = _object(event.get("repository"), "repository")
    if event_repo.get("full_name") != repository:
        raise MergeHoldGateError("event repository mismatch")
    number = event.get("number")
    if type(number) is not int or number <= 0:
        raise MergeHoldGateError("invalid event PR number")
    event_pr = _object(event.get("pull_request"), "event.pull_request")
    old_title, old_body, old_head, old_base, old_labels = _pr_fields(event_pr, repository, number)
    title, body, head, base, labels = _pr_fields(current_pr, repository, number)
    if (old_title, old_body, old_head, old_base, old_labels) != (
        title, body, head, base, labels
    ):
        raise MergeHoldGateError("PR metadata changed since workflow event")
    if labels and EXPLICIT_HOLD_LABELS.intersection(labels):
        raise MergeHoldGateError("explicit PR label merge hold")
    if has_explicit_merge_hold(title, body):
        raise MergeHoldGateError("explicit PR title/body merge hold")
    print(f"PR #{number}: no explicit title, body or label merge hold at current head {head}")


def fetch_current_pr(repository: str, number: int, token: str) -> dict:
    if not REPOSITORY_RE.fullmatch(repository) or type(number) is not int or number <= 0:
        raise MergeHoldGateError("invalid PR identity")
    if not token:
        raise MergeHoldGateError("missing read-only GitHub token")
    url = f"https://api.github.com/repos/{repository}/pulls/{number}"
    request = Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "skeleton-pr-merge-hold-gate",
        },
    )
    with urlopen(request, timeout=15) as response:
        raw = response.read(MAX_API_BYTES + 1)
    return _decode_json(raw, maximum=MAX_API_BYTES)


def main() -> int:
    try:
        if os.environ.get("GITHUB_EVENT_NAME") != "pull_request_target":
            raise MergeHoldGateError("trusted pull_request_target event required")
        repository = os.environ.get("GITHUB_REPOSITORY", "")
        if not REPOSITORY_RE.fullmatch(repository):
            raise MergeHoldGateError("invalid GitHub repository")
        path = Path(os.environ["GITHUB_EVENT_PATH"])
        if path.stat().st_size > MAX_EVENT_BYTES:
            raise MergeHoldGateError("event metadata exceeds bounded size")
        event = _decode_json(path.read_bytes(), maximum=MAX_EVENT_BYTES)
        number = event.get("number")
        if type(number) is not int or number <= 0:
            raise MergeHoldGateError("invalid event PR number")
        current = fetch_current_pr(repository, number, os.environ.get("GITHUB_TOKEN", ""))
        validate_current_pr(event, current, repository)
        return 0
    except (MergeHoldGateError, OSError, HTTPError, URLError, KeyError) as exc:
        # Never print PR text, token, headers or untrusted HTTP response bodies.
        reason = str(exc) if isinstance(exc, MergeHoldGateError) else type(exc).__name__
        print(f"PR merge hold gate: DENIED ({reason})", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
