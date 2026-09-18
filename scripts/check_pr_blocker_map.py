#!/usr/bin/env python3
"""Fail-closed current-PR blocker map (#969 Seed 01).

Classifies a PR-check JSON fixture: exact required checks roll up to the
first of ``blocking``, ``queued``, ``stale``, or ``success``. Queued and
cancelled never count as success. Unknown conclusions fail closed.

This module classifies fixture JSON only. It has no GitHub mutation,
rerun, cancel, or ``gh`` authority. Finding prefix: ``pr-blocker-map``.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Mapping, Sequence


SCHEMA_VERSION = 1
TASK_ID = "reserve-S001-current-pr-blocker-map"
CONFLICT_DOMAIN = "ci.readonly.blocker_map"
ROLLUP_PRIORITY: tuple[str, ...] = ("blocking", "queued", "stale", "success")
CLASSES: tuple[str, ...] = (*ROLLUP_PRIORITY, "unknown")
CLASS_SET = frozenset(CLASSES)
_FINDING_PREFIX = "pr-blocker-map"

DOCUMENT_FIELDS = frozenset(
    {
        "schema_version",
        "task_id",
        "conflict_domain",
        "pull_request",
        "required_checks",
        "checks",
    }
)
PR_FIELDS = frozenset(
    {
        "number",
        "state",
        "head_sha",
        "owning_issue",
        "repair",
        "html_url",
    }
)
PR_REQUIRED_FIELDS = frozenset({"number", "state", "head_sha", "owning_issue", "repair"})
CHECK_FIELDS = frozenset({"name", "status", "conclusion", "head_sha"})
CHECK_REQUIRED_FIELDS = frozenset({"name", "status", "head_sha"})

KNOWN_STATUSES = frozenset(
    {
        "queued",
        "in_progress",
        "completed",
        "waiting",
        "requested",
        "pending",
        "waiting_for_review",
    }
)
QUEUED_STATUSES = frozenset(
    {
        "queued",
        "in_progress",
        "waiting",
        "requested",
        "pending",
        "waiting_for_review",
    }
)
KNOWN_CONCLUSIONS = frozenset(
    {
        "success",
        "failure",
        "cancelled",
        "canceled",
        "timed_out",
        "skipped",
        "startup_failure",
        "action_required",
        "stale",
        "neutral",
        "error",
    }
)
BLOCKING_CONCLUSIONS = frozenset(
    {
        "failure",
        "cancelled",
        "timed_out",
        "skipped",
        "startup_failure",
        "action_required",
        "neutral",
        "error",
    }
)


def _error(code: str, message: str) -> str:
    return f"{_FINDING_PREFIX} {code}: {message}"


def _norm(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip().lower().replace("-", "_")
    return text or None


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def first_rollup(classes: Sequence[str]) -> str:
    """Return the first blocking/queued/stale/success class. Unknown wins."""

    normalized: list[str] = []
    for item in classes:
        if item not in CLASS_SET:
            return "unknown"
        normalized.append(item)
    if any(item == "unknown" for item in normalized):
        return "unknown"
    if not normalized:
        return "unknown"
    for candidate in ROLLUP_PRIORITY:
        if any(item == candidate for item in normalized):
            return candidate
    return "unknown"


def classify_check(check: object, *, current_sha: str) -> str:
    """Classify one required-check row. Unknown conclusions fail closed."""

    if not isinstance(check, Mapping):
        return "unknown"
    unknown_fields = set(check) - CHECK_FIELDS
    if unknown_fields:
        return "unknown"
    missing = CHECK_REQUIRED_FIELDS - set(check)
    if missing:
        return "unknown"

    name = check.get("name")
    if not isinstance(name, str) or not name.strip():
        return "unknown"

    status = _norm(check.get("status"))
    if status is None or status not in KNOWN_STATUSES:
        return "unknown"

    conclusion = check.get("conclusion")
    conc = _norm(conclusion) if conclusion is not None else None
    if conc == "canceled":
        conc = "cancelled"
    if conclusion is not None and conc not in KNOWN_CONCLUSIONS:
        return "unknown"

    head_sha = check.get("head_sha")
    if not isinstance(head_sha, str) or not head_sha.strip():
        return "unknown"
    current = current_sha.strip()
    if not current:
        return "unknown"

    if head_sha.strip() != current:
        return "stale"

    if status in QUEUED_STATUSES:
        return "queued"

    if status != "completed":
        return "unknown"
    if conc is None:
        return "unknown"
    if conc == "success":
        return "success"
    if conc == "stale":
        return "stale"
    if conc in BLOCKING_CONCLUSIONS:
        return "blocking"
    return "unknown"


def _select_current_check(
    name: str, checks: Sequence[object], *, current_sha: str
) -> object | None:
    matches: list[object] = []
    current_matches: list[object] = []
    for check in checks:
        if not isinstance(check, Mapping):
            return None
        check_name = check.get("name")
        if not isinstance(check_name, str) or check_name.strip() != name:
            continue
        matches.append(check)
        head_sha = check.get("head_sha")
        if isinstance(head_sha, str) and head_sha.strip() == current_sha.strip():
            current_matches.append(check)
    if len(current_matches) == 1:
        return current_matches[0]
    if len(current_matches) > 1:
        return None
    if len(matches) == 1:
        return matches[0]
    return None


def classify_document(document: object) -> tuple[dict[str, object], list[str]]:
    """Classify one PR-check fixture. Unknown/invalid evidence fails closed."""

    errors: list[str] = []
    empty: dict[str, object] = {
        "task_id": TASK_ID,
        "conflict_domain": CONFLICT_DOMAIN,
        "schema_version": SCHEMA_VERSION,
        "pr_number": None,
        "pr_state": None,
        "head_sha": None,
        "owning_issue": None,
        "repair": None,
        "rollup": "unknown",
        "required_checks": [],
        "check_states": [],
    }
    if not isinstance(document, Mapping):
        return empty, [_error("unknown root_type", "document must be an object")]

    unknown_fields = set(document) - DOCUMENT_FIELDS
    if unknown_fields:
        errors.append(
            _error(
                "unknown field",
                "document has unknown fields: " + ", ".join(sorted(str(item) for item in unknown_fields)),
            )
        )
    missing_fields = DOCUMENT_FIELDS - set(document)
    if missing_fields:
        errors.append(
            _error(
                "missing_value field",
                "document missing fields: " + ", ".join(sorted(missing_fields)),
            )
        )

    version = document.get("schema_version")
    if not _is_int(version) or version != SCHEMA_VERSION:
        errors.append(_error("unknown schema_version", f"schema_version must be exactly {SCHEMA_VERSION}"))

    task_id = document.get("task_id")
    if task_id != TASK_ID:
        errors.append(_error("unknown task_id", f"task_id must be exactly {TASK_ID}"))

    conflict_domain = document.get("conflict_domain")
    if conflict_domain != CONFLICT_DOMAIN:
        errors.append(
            _error(
                "unknown conflict_domain",
                f"conflict_domain must be exactly {CONFLICT_DOMAIN}",
            )
        )

    pull_request = document.get("pull_request")
    current_sha = ""
    pr_number: object = None
    pr_state: object = None
    owning_issue: object = None
    repair: object = None
    if not isinstance(pull_request, Mapping):
        errors.append(_error("unknown pull_request", "pull_request must be an object"))
    else:
        unknown_pr = set(pull_request) - PR_FIELDS
        if unknown_pr:
            errors.append(
                _error(
                    "unknown field",
                    "pull_request has unknown fields: " + ", ".join(sorted(str(item) for item in unknown_pr)),
                )
            )
        missing_pr = PR_REQUIRED_FIELDS - set(pull_request)
        if missing_pr:
            errors.append(
                _error(
                    "missing_value field",
                    "pull_request missing fields: " + ", ".join(sorted(missing_pr)),
                )
            )
        pr_number = pull_request.get("number")
        if not _is_int(pr_number) or pr_number <= 0:
            errors.append(_error("unknown pr_number", "pull_request.number must be an integer >= 1"))
            pr_number = None
        pr_state = pull_request.get("state")
        state_norm = _norm(pr_state)
        if state_norm != "open":
            errors.append(_error("unknown pr_state", "pull_request.state must be open"))
        else:
            pr_state = "open"
        head_sha = pull_request.get("head_sha")
        if not isinstance(head_sha, str) or not head_sha.strip():
            errors.append(_error("missing_value head_sha", "pull_request.head_sha must be a non-empty string"))
        else:
            current_sha = head_sha.strip()
        owning_issue = pull_request.get("owning_issue")
        if not isinstance(owning_issue, str) or not owning_issue.strip():
            errors.append(
                _error("missing_value owning_issue", "pull_request.owning_issue must be a non-empty string")
            )
            owning_issue = None
        else:
            owning_issue = owning_issue.strip()
        repair = pull_request.get("repair")
        if repair is not None and (not isinstance(repair, str) or not repair.strip()):
            errors.append(_error("unknown repair", "pull_request.repair must be a non-empty string or null"))
            repair = None
        elif isinstance(repair, str):
            repair = repair.strip()
        html_url = pull_request.get("html_url")
        if html_url is not None and (not isinstance(html_url, str) or not html_url.strip()):
            errors.append(_error("unknown html_url", "pull_request.html_url must be a non-empty string when set"))

    required_checks = document.get("required_checks")
    names: list[str] = []
    if not isinstance(required_checks, list) or not required_checks:
        errors.append(_error("missing_value required_checks", "required_checks must be a non-empty list of names"))
    else:
        seen: set[str] = set()
        for index, name in enumerate(required_checks):
            if not isinstance(name, str) or not name.strip():
                errors.append(
                    _error("unknown required_check", f"required_checks[{index}] must be a non-empty string")
                )
                continue
            trimmed = name.strip()
            if trimmed in seen:
                errors.append(_error("unknown required_check", f"required_checks duplicate name {trimmed!r}"))
                continue
            seen.add(trimmed)
            names.append(trimmed)

    checks = document.get("checks")
    if not isinstance(checks, list):
        errors.append(_error("unknown checks_type", "checks must be a list"))
        report = dict(empty)
        report["pr_number"] = pr_number
        report["pr_state"] = pr_state
        report["head_sha"] = current_sha or None
        report["owning_issue"] = owning_issue
        report["repair"] = repair
        report["required_checks"] = list(names)
        return report, errors

    check_states: list[dict[str, object]] = []
    classes: list[str] = []
    if current_sha:
        for name in names:
            selected = _select_current_check(name, checks, current_sha=current_sha)
            if selected is None:
                klass = "unknown"
                errors.append(_error("unknown unclassified", f"required check {name!r} has no unique current evidence"))
            else:
                klass = classify_check(selected, current_sha=current_sha)
                if klass == "unknown":
                    errors.append(_error("unknown unclassified", f"required check {name!r} is unclassified"))
            check_states.append({"name": name, "class": klass})
            classes.append(klass)
    else:
        for name in names:
            check_states.append({"name": name, "class": "unknown"})
            classes.append("unknown")
            errors.append(_error("unknown unclassified", f"required check {name!r} lacks current head SHA evidence"))

    rollup = first_rollup(classes)
    if errors:
        rollup = "unknown"
    report: dict[str, object] = {
        "task_id": TASK_ID,
        "conflict_domain": CONFLICT_DOMAIN,
        "schema_version": SCHEMA_VERSION,
        "pr_number": pr_number,
        "pr_state": pr_state,
        "head_sha": current_sha or None,
        "owning_issue": owning_issue,
        "repair": repair,
        "rollup": rollup,
        "required_checks": list(names),
        "check_states": check_states,
    }
    return report, errors


def load_document(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SystemExit(_error("unreadable missing_doc", f"{path} is missing")) from exc
    except OSError as exc:
        raise SystemExit(
            _error("unreadable io_error", f"cannot read {path}: {type(exc).__name__}")
        ) from exc
    except json.JSONDecodeError as exc:
        raise SystemExit(
            _error("unreadable json", f"invalid JSON in {path} at line {exc.lineno}")
        ) from exc


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path, help="PR-check JSON fixture")
    args = parser.parse_args(argv)
    report, errors = classify_document(load_document(args.path))
    counts = {name: 0 for name in CLASSES}
    for row in report["check_states"]:
        counts[str(row["class"])] += 1
    print(
        "PR-blocker map: "
        f"pr={report['pr_number']} rollup={report['rollup']} "
        f"owning_issue={report['owning_issue']} repair={report['repair']} "
        + ", ".join(f"{name}={counts[name]}" for name in CLASSES)
    )
    if errors:
        print("PR-blocker map failed:", file=sys.stderr)
        for item in errors:
            print(f"  {item}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
