"""Deterministic helpers for safe repair-intake identity and metadata."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Callable, Mapping
from typing import Final
from urllib.parse import quote

_FINGERPRINT_RE = re.compile(r"[0-9a-f]{64}\Z")
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")
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
    text = _required_text(value, field_name)
    if len(text) > _MAX_REF_LEN:
        raise ValueError(f"{field_name} exceeds maximum length")
    if _CONTROL_RE.search(text):
        raise ValueError(f"{field_name} must not contain control characters")
    return text


def intake_fingerprint(
    workflow: str,
    conclusion: str,
    head_sha: str,
) -> str:
    """Return a stable identity for one workflow/head failure observation.

    Run IDs are intentionally excluded so reruns of the same workflow at the
    same commit correlate to one durable intake record instead of creating a
    new issue for every attempt.
    """

    values = (
        _required_text(workflow, "workflow").lower(),
        _required_text(conclusion, "conclusion").lower(),
        _required_ref(head_sha, "head_sha").lower(),
    )
    return hashlib.sha256("\x1f".join(values).encode("utf-8")).hexdigest()


def family_fingerprint(workflow: str, branch: str) -> str:
    """Return a durable identity for one workflow + branch failure family.

    Merge storms rewrite branch tips faster than repair automation can drain
    them. Family identity lets intake keep one open record per live branch
    instead of opening a new issue for every superseded SHA.
    """

    values = (
        _required_text(workflow, "workflow").lower(),
        FAMILY_DISCRIMINATOR,
        _required_ref(branch, "branch").lower(),
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
    """URL-encode an untrusted branch name for the GitHub branches API."""

    return quote(_required_ref(branch, "branch"), safe="")


def resolve_branch_tip(
    repo: str,
    branch: str,
    *,
    opener: HttpOpener,
) -> tuple[str, str | None]:
    """Return ``(state, sha)`` for a same-repo branch without checking out code.

    States:
    - ``current`` is unused here; callers compare the SHA themselves
    - ``ok`` with a SHA when the branch exists and is readable
    - ``missing`` when GitHub reports 404
    - ``unreadable`` when the lookup is ambiguous or failed
    """

    repository = _required_text(repo, "repo")
    if repository.count("/") != 1:
        raise ValueError("repo must be owner/name")
    encoded = encode_branch_path(branch)
    path = f"/repos/{repository}/branches/{encoded}"
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
    sha = commit.get("sha")
    if not isinstance(sha, str) or not sha.strip():
        return "unreadable", None
    try:
        return "ok", _required_ref(sha, "sha")
    except (TypeError, ValueError):
        return "unreadable", None


def _required_workflow_id(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        if isinstance(value, str) and value.strip().isdigit():
            parsed = int(value.strip())
        else:
            raise TypeError("workflow_id must be a positive integer")
    else:
        parsed = value
    if parsed < 1:
        raise ValueError("workflow_id must be a positive integer")
    return parsed


def workflow_sha_recovered(
    repo: str,
    workflow: str,
    head_sha: str,
    *,
    workflow_id: int,
    opener: HttpOpener,
    page_size: int = RECOVERY_PAGE_SIZE,
    max_pages: int = RECOVERY_MAX_PAGES,
) -> bool | None:
    """Return whether the same workflow later succeeded on this SHA.

    Looks up runs for the numeric workflow identity rather than scanning every
    completed run on the SHA. Pages through results with a strict cap. ``True``
    means a completed success exists. ``False`` means the workflow-specific
    history was fully scanned with no success. ``None`` means the lookup was
    unreadable or the page bound was exhausted while more results remained.
    """

    repository = _required_text(repo, "repo")
    if repository.count("/") != 1:
        raise ValueError("repo must be owner/name")
    name = _required_text(workflow, "workflow").lower()
    sha = _required_ref(head_sha, "head_sha")
    identity = _required_workflow_id(workflow_id)
    if isinstance(page_size, bool) or not isinstance(page_size, int) or page_size < 1:
        raise ValueError("page_size must be a positive integer")
    if isinstance(max_pages, bool) or not isinstance(max_pages, int) or max_pages < 1:
        raise ValueError("max_pages must be a positive integer")

    scanned = 0
    total_count: int | None = None
    for page in range(1, max_pages + 1):
        path = (
            f"/repos/{repository}/actions/workflows/{identity}/runs"
            f"?head_sha={quote(sha, safe='')}"
            "&status=completed"
            f"&per_page={page_size}"
            f"&page={page}"
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
            run_name = run.get("name")
            conclusion = run.get("conclusion")
            if isinstance(run_name, str) and run_name.strip().lower() != name:
                continue
            if isinstance(conclusion, str) and conclusion.strip().lower() == "success":
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
    """Return the pre-emptive intake action for one failure observation.

    Creating issues is the privileged mutation. Ambiguous branch state therefore
    skips intake rather than opening another record during a merge storm.
    """

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
        current_sha = _required_ref(head_sha, "head_sha").lower()
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
        tip = _required_ref(branch_tip, "branch_tip").lower()
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
