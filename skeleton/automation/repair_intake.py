"""Deterministic helpers for safe repair-intake identity and metadata."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Callable, Mapping
from typing import Final
from urllib.parse import quote

_FINGERPRINT_RE = re.compile(r"[0-9a-f]{64}\Z")
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")
COMMIT_OID_RE = re.compile(r"^[0-9a-f]{40}$")
_MAX_REF_LEN = 255

INTAKE_CREATE: Final = "create"
INTAKE_SKIP_DUPLICATE: Final = "skip_duplicate"
INTAKE_SKIP_SUPERSEDED: Final = "skip_superseded"
INTAKE_SKIP_FAMILY: Final = "skip_family"
INTAKE_SKIP_INVALID: Final = "skip_invalid"
INTAKE_SKIP_UNREADABLE: Final = "skip_unreadable"
INTAKE_SKIP_RECOVERED: Final = "skip_recovered"

FAMILY_DISCRIMINATOR: Final = "family"
RECOVERY_PAGE_SIZE: Final = 100
RECOVERY_MAX_PAGES: Final = 10

HttpOpener = Callable[[str], tuple[int, Mapping[str, object] | None]]


def _required_text(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be empty")
    return normalized


def _required_ref(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    if not value or value != value.strip():
        raise ValueError(f"{field_name} must be non-empty and canonical")
    if len(value) > _MAX_REF_LEN:
        raise ValueError(f"{field_name} exceeds maximum length")
    if _CONTROL_RE.search(value):
        raise ValueError(f"{field_name} must not contain control characters")
    return value


def canonical_commit_oid(value: object, field_name: str = "head_sha") -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    oid = value.casefold()
    if COMMIT_OID_RE.fullmatch(oid) is None:
        raise ValueError(f"{field_name} must be a 40-character hex commit OID")
    return oid


def intake_fingerprint(
    workflow: str,
    conclusion: str,
    head_sha: str,
) -> str:
    """Return a stable identity for one workflow/head failure observation.

    Run IDs are intentionally excluded so reruns of the same workflow at the
    same commit correlate to one durable intake record instead of creating a
    new issue for every attempt. The head SHA must be a full 40-hex commit OID
    so fingerprints cannot collapse abbreviated or padded event input.
    """

    values = (
        _required_text(workflow, "workflow").casefold(),
        _required_text(conclusion, "conclusion").casefold(),
        canonical_commit_oid(head_sha, "head_sha"),
    )
    return hashlib.sha256("\x1f".join(values).encode("utf-8")).hexdigest()


def family_fingerprint(workflow: str, branch: str) -> str:
    """Return a workflow + branch identity while preserving Git ref case."""

    values = (
        _required_text(workflow, "workflow").casefold(),
        FAMILY_DISCRIMINATOR,
        _required_ref(branch, "branch"),
    )
    return hashlib.sha256("\x1f".join(values).encode("utf-8")).hexdigest()


def issue_marker(fingerprint: str) -> str:
    """Return the exact machine-readable marker used for SHA deduplication."""

    return _marker("fingerprint", fingerprint)


def issue_family_marker(fingerprint: str) -> str:
    """Return the exact machine-readable marker used for branch-family dedupe."""

    return _marker("family", fingerprint)


def _marker(kind: str, fingerprint: str) -> str:
    if not isinstance(fingerprint, str):
        raise TypeError("fingerprint must be a string")
    if not _FINGERPRINT_RE.fullmatch(fingerprint):
        raise ValueError("fingerprint must be a lowercase sha256 digest")
    return f"<!-- repair-intake:{kind}={fingerprint} -->"


def encode_branch_path(branch: str) -> str:
    """URL-encode an exact, validated branch name for the GitHub branches API."""

    return quote(_required_ref(branch, "branch"), safe="")


def resolve_branch_tip(
    repo: str,
    branch: str,
    *,
    opener: HttpOpener,
) -> tuple[str, str | None]:
    """Return the state and SHA for a same-repository branch without checkout."""

    repository = _required_text(repo, "repo")
    if repository.count("/") != 1:
        raise ValueError("repo must be owner/name")
    path = f"/repos/{repository}/branches/{encode_branch_path(branch)}"
    try:
        status, payload = opener(path)
    except Exception:
        return "unreadable", None
    if status == 404:
        return "missing", None
    if status != 200 or not isinstance(payload, Mapping):
        return "unreadable", None
    commit = payload.get("commit")
    if not isinstance(commit, Mapping):
        return "unreadable", None
    try:
        sha = canonical_commit_oid(commit.get("sha"), "branch_tip")
    except (TypeError, ValueError):
        return "unreadable", None
    return "ok", sha


def _required_positive_int(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be an integer")
    if value < 1:
        raise ValueError(f"{field_name} must be positive")
    return value


def workflow_sha_recovered(
    repo: str,
    workflow: str,
    head_sha: str,
    *,
    workflow_id: int,
    failed_run_id: int,
    opener: HttpOpener,
    page_size: int = RECOVERY_PAGE_SIZE,
    max_pages: int = RECOVERY_MAX_PAGES,
) -> bool | None:
    """Return whether this exact workflow later succeeded on this exact SHA.

    None means the bounded evidence scan was unreadable or incomplete and
    callers must fail closed rather than create another repair record.
    """

    repository = _required_text(repo, "repo")
    if repository.count("/") != 1:
        raise ValueError("repo must be owner/name")
    workflow_name = _required_text(workflow, "workflow").casefold()
    oid = canonical_commit_oid(head_sha, "head_sha")
    wid = _required_positive_int(workflow_id, "workflow_id")
    failed_id = _required_positive_int(failed_run_id, "failed_run_id")
    if isinstance(page_size, bool) or not isinstance(page_size, int) or not 1 <= page_size <= 100:
        raise ValueError("page_size must be an integer from 1 to 100")
    if isinstance(max_pages, bool) or not isinstance(max_pages, int) or max_pages < 1:
        raise ValueError("max_pages must be a positive integer")

    scanned = 0
    total_count: int | None = None
    for page in range(1, max_pages + 1):
        path = (
            f"/repos/{repository}/actions/workflows/{wid}/runs"
            f"?head_sha={oid}&status=completed&per_page={page_size}&page={page}"
        )
        try:
            status, payload = opener(path)
        except Exception:
            return None
        if status != 200 or not isinstance(payload, Mapping):
            return None

        raw_total = payload.get("total_count")
        if isinstance(raw_total, bool) or not isinstance(raw_total, int) or raw_total < 0:
            return None
        if total_count is None:
            total_count = raw_total
        elif raw_total != total_count:
            return None

        runs = payload.get("workflow_runs")
        if not isinstance(runs, list):
            return None
        for run in runs:
            if not isinstance(run, Mapping):
                continue
            name = run.get("name")
            conclusion = run.get("conclusion")
            run_id = run.get("id")
            if (
                isinstance(name, str)
                and isinstance(conclusion, str)
                and name.strip().casefold() == workflow_name
                and conclusion.strip().casefold() == "success"
            ):
                if isinstance(run_id, bool) or not isinstance(run_id, int) or run_id < 1:
                    return None
                if run_id > failed_id:
                    return True

        scanned += len(runs)
        if len(runs) < page_size or scanned >= total_count:
            return False

    if total_count is not None and scanned < total_count:
        return None
    return False


def classify_intake(
    *,
    sha_record_exists: bool,
    family_open_exists: bool,
    branch_lookup: str,
    branch_tip: str | None,
    head_sha: str,
    recovered: bool = False,
    recovery_known: bool = True,
) -> str:
    """Return the fail-closed repair-intake action for one failure observation."""

    if not isinstance(sha_record_exists, bool):
        raise TypeError("sha_record_exists must be a bool")
    if not isinstance(family_open_exists, bool):
        raise TypeError("family_open_exists must be a bool")
    if not isinstance(recovered, bool):
        raise TypeError("recovered must be a bool")
    if not isinstance(recovery_known, bool):
        raise TypeError("recovery_known must be a bool")
    if branch_lookup not in {"ok", "missing", "unreadable"}:
        raise ValueError("branch_lookup must be ok, missing, or unreadable")

    try:
        current_sha = canonical_commit_oid(head_sha, "head_sha")
    except (TypeError, ValueError):
        return INTAKE_SKIP_INVALID

    if sha_record_exists:
        return INTAKE_SKIP_DUPLICATE
    if branch_lookup == "unreadable":
        return INTAKE_SKIP_UNREADABLE
    if branch_lookup == "missing":
        return INTAKE_SKIP_SUPERSEDED
    if branch_tip is None:
        return INTAKE_SKIP_UNREADABLE
    try:
        tip = canonical_commit_oid(branch_tip, "branch_tip")
    except (TypeError, ValueError):
        return INTAKE_SKIP_UNREADABLE
    if tip != current_sha:
        return INTAKE_SKIP_SUPERSEDED
    if not recovery_known:
        return INTAKE_SKIP_UNREADABLE
    if recovered:
        return INTAKE_SKIP_RECOVERED
    if family_open_exists:
        return INTAKE_SKIP_FAMILY
    return INTAKE_CREATE
