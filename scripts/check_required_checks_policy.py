#!/usr/bin/env python3
"""Fail closed when the required-check policy drifts from its enforcement points (#127).

``.github/ci/required-checks.json`` is the single machine-readable source of
truth for which status check ``main`` must require and which lanes feed it.
This guard ties every place that restates that policy back to the file:

* the canonical aggregate workflow (workflow name, job name, ``needs`` list,
  per-lane job names, and explicit result bindings);
* every other workflow, so no second job can publish a check run with the
  same required name (an ambiguous required context could be satisfied by
  the wrong job);
* the owner-side ``configure_main_protection.sh`` payload and constants;
* ``check_merge_readiness_contract.REQUIRED_NEEDS``;
* the human documentation, including stale required-check names.

Standard library only so it runs in the bare ``Quarantine Policy`` job. It
reads files; it has no GitHub, network, or write authority.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_POLICY = Path(".github/ci/required-checks.json")
SCHEMA_VERSION = 1
PROTECTION_KEYS = (
    "strict",
    "enforce_admins",
    "required_approving_review_count",
    "dismiss_stale_reviews",
    "required_conversation_resolution",
    "allow_force_pushes",
    "allow_deletions",
)
_JOB_HEADER = re.compile(r"^  (?P<id>[A-Za-z0-9_-]+):\s*(?:#.*)?$")
_JOB_NAME = re.compile(r"^    name:\s*(?P<name>.+?)\s*(?:#.*)?$")
_TOP_NAME = re.compile(r"^name:\s*(?P<name>.+?)\s*(?:#.*)?$", re.MULTILINE)


class PolicyError(ValueError):
    """Raised when the policy document itself is malformed."""


def _unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
        return value[1:-1]
    return value


def _require_str(obj: dict[str, Any], key: str, where: str) -> str:
    value = obj.get(key)
    if not isinstance(value, str) or not value.strip():
        raise PolicyError(f"{where}.{key} must be a non-empty string")
    return value


def load_policy(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PolicyError(f"cannot read policy {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise PolicyError("policy root must be an object")
    if data.get("schema_version") != SCHEMA_VERSION:
        raise PolicyError(f"schema_version must be {SCHEMA_VERSION}")
    _require_str(data, "branch", "policy")
    checks = data.get("required_status_checks")
    if not isinstance(checks, list) or len(checks) != 1:
        raise PolicyError(
            "required_status_checks must contain exactly one deterministic aggregate check"
        )
    for index, check in enumerate(checks):
        where = f"required_status_checks[{index}]"
        if not isinstance(check, dict):
            raise PolicyError(f"{where} must be an object")
        for key in ("context", "workflow_file", "workflow_name", "job_id"):
            _require_str(check, key, where)
        if not isinstance(check.get("app_id"), int) or check["app_id"] <= 0:
            raise PolicyError(f"{where}.app_id must be a positive integer")
    lanes = data.get("aggregate_lanes")
    if not isinstance(lanes, list) or not lanes:
        raise PolicyError("aggregate_lanes must be a non-empty list")
    seen: set[str] = set()
    for index, lane in enumerate(lanes):
        where = f"aggregate_lanes[{index}]"
        if not isinstance(lane, dict):
            raise PolicyError(f"{where} must be an object")
        for key in ("job_id", "name", "result_env"):
            _require_str(lane, key, where)
        if lane["job_id"] in seen:
            raise PolicyError(f"{where}.job_id {lane['job_id']!r} is duplicated")
        seen.add(lane["job_id"])
    protection = data.get("protection")
    if not isinstance(protection, dict):
        raise PolicyError("protection must be an object")
    for key in PROTECTION_KEYS:
        if key not in protection:
            raise PolicyError(f"protection.{key} is required")
    if (
        protection.get("allow_force_pushes") is not False
        or protection.get("allow_deletions") is not False
    ):
        raise PolicyError(
            "protection must forbid force-pushes and deletions on the protected branch"
        )
    for key in ("documentation", "name_references", "stale_check_names"):
        value = data.get(key, [])
        if not isinstance(value, list) or not all(
            isinstance(item, str) and item for item in value
        ):
            raise PolicyError(f"{key} must be a list of non-empty strings")
    _require_str(data, "protection_script", "policy")
    _require_str(data, "contract_checker", "policy")
    return data


def parse_jobs(text: str) -> dict[str, dict[str, str | None]]:
    """Return top-level workflow jobs as ``{job_id: {"name": ..., "block": ...}}``."""

    lines = text.splitlines()
    try:
        start = next(
            i for i, line in enumerate(lines) if re.match(r"^jobs:\s*(?:#.*)?$", line)
        )
    except StopIteration:
        return {}
    jobs: dict[str, dict[str, str | None]] = {}
    current: str | None = None
    block: list[str] = []

    def flush() -> None:
        if current is None:
            return
        name = None
        for line in block:
            match = _JOB_NAME.match(line)
            if match:
                name = _unquote(match.group("name"))
                break
        jobs[current] = {"name": name, "block": "\n".join(block)}

    for line in lines[start + 1 :]:
        if line and not line[0].isspace() and not line.startswith("#"):
            break
        header = _JOB_HEADER.match(line)
        if header:
            flush()
            current = header.group("id")
            block = [line]
        elif current is not None:
            block.append(line)
    flush()
    return jobs


def workflow_name(text: str) -> str | None:
    match = _TOP_NAME.search(text)
    return _unquote(match.group("name")) if match else None


def _read(root: Path, relative: str, failures: list[str]) -> str | None:
    try:
        return (root / relative).read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        failures.append(f"{relative}: cannot read ({exc})")
        return None


def check_workflow(policy: dict[str, Any], root: Path) -> list[str]:
    failures: list[str] = []
    check = policy["required_status_checks"][0]
    text = _read(root, check["workflow_file"], failures)
    if text is None:
        return failures
    where = check["workflow_file"]
    if workflow_name(text) != check["workflow_name"]:
        failures.append(f"{where}: workflow name must be {check['workflow_name']!r}")
    for trigger in ("pull_request:", "push:"):
        if re.search(rf"^  {trigger}", text, re.MULTILINE) is None:
            failures.append(
                f"{where}: required aggregate must run on {trigger.rstrip(':')}"
            )
    jobs = parse_jobs(text)
    aggregate = jobs.get(check["job_id"])
    if aggregate is None:
        failures.append(f"{where}: aggregate job {check['job_id']!r} missing")
        return failures
    if aggregate["name"] != check["context"]:
        failures.append(
            f"{where}: job {check['job_id']!r} must be named {check['context']!r} (found {aggregate['name']!r})"
        )
    block = aggregate["block"] or ""
    needs_match = re.search(
        r"^    needs:\s*\n((?:      - .+\n?)+)", block, re.MULTILINE
    )
    declared = (
        [
            item.strip()[2:].strip()
            for item in needs_match.group(1).splitlines()
            if item.strip()
        ]
        if needs_match
        else []
    )
    expected = [lane["job_id"] for lane in policy["aggregate_lanes"]]
    if sorted(declared) != sorted(expected):
        failures.append(
            f"{where}: aggregate needs {sorted(declared)} must equal policy lanes {sorted(expected)}"
        )
    for lane in policy["aggregate_lanes"]:
        job = jobs.get(lane["job_id"])
        if job is None:
            failures.append(f"{where}: lane job {lane['job_id']!r} missing")
            continue
        if job["name"] != lane["name"]:
            failures.append(
                f"{where}: lane {lane['job_id']!r} must be named {lane['name']!r} (found {job['name']!r})"
            )
        binding = f"{lane['result_env']}: ${{{{ needs.{lane['job_id']}.result }}}}"
        if binding not in block:
            failures.append(f"{where}: aggregate missing result binding {binding!r}")
        if f'os.environ["{lane["result_env"]}"]' not in block:
            failures.append(
                f"{where}: aggregate summary never evaluates {lane['result_env']}"
            )
        if "continue-on-error: true" in (job["block"] or ""):
            failures.append(
                f"{where}: lane {lane['job_id']!r} must not hide failures with continue-on-error"
            )
    return failures


def check_unique_context(policy: dict[str, Any], root: Path) -> list[str]:
    failures: list[str] = []
    check = policy["required_status_checks"][0]
    canonical = (Path(check["workflow_file"]).as_posix(), check["job_id"])
    workflows = root / ".github" / "workflows"
    for path in sorted([*workflows.glob("*.yml"), *workflows.glob("*.yaml")]):
        relative = path.relative_to(root).as_posix()
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            failures.append(f"{relative}: cannot read ({exc})")
            continue
        for job_id, job in parse_jobs(text).items():
            published = job["name"] if job["name"] is not None else job_id
            if published == check["context"] and (relative, job_id) != canonical:
                failures.append(
                    f"{relative}: job {job_id!r} also publishes required check name {check['context']!r}; "
                    "a duplicate context lets an unrelated job satisfy branch protection"
                )
    return failures


def check_protection_script(policy: dict[str, Any], root: Path) -> list[str]:
    failures: list[str] = []
    relative = policy["protection_script"]
    text = _read(root, relative, failures)
    if text is None:
        return failures
    check = policy["required_status_checks"][0]
    constant = re.search(r'^required_check="([^"]*)"', text, re.MULTILINE)
    if constant is None or constant.group(1) != check["context"]:
        failures.append(f"{relative}: required_check must be {check['context']!r}")
    app = re.search(r'^required_app_id="([^"]*)"', text, re.MULTILINE)
    if app is None or app.group(1) != str(check["app_id"]):
        failures.append(f"{relative}: required_app_id must be {check['app_id']}")
    if f'.context == "{check["context"]}" and .app_id == {check["app_id"]}' not in text:
        failures.append(f"{relative}: --verify must match the exact context and app id")
    if (
        re.search(
            rf'^branch="\$\{{BRANCH:-{re.escape(policy["branch"])}\}}"',
            text,
            re.MULTILINE,
        )
        is None
    ):
        failures.append(f"{relative}: default branch must be {policy['branch']!r}")
    payload_match = re.search(r"^payload='(\{.*?\})'$", text, re.MULTILINE | re.DOTALL)
    if payload_match is None:
        failures.append(f"{relative}: protection payload block missing")
        return failures
    try:
        payload = json.loads(payload_match.group(1))
    except json.JSONDecodeError as exc:
        failures.append(f"{relative}: protection payload is not valid JSON ({exc})")
        return failures
    protection = policy["protection"]
    status = payload.get("required_status_checks") or {}
    reviews = payload.get("required_pull_request_reviews") or {}
    expected_checks = [{"context": check["context"], "app_id": check["app_id"]}]
    observed = {
        "checks": status.get("checks"),
        "contexts": status.get("contexts"),
        "strict": status.get("strict"),
        "enforce_admins": payload.get("enforce_admins"),
        "required_approving_review_count": reviews.get(
            "required_approving_review_count"
        ),
        "dismiss_stale_reviews": reviews.get("dismiss_stale_reviews"),
        "required_conversation_resolution": payload.get(
            "required_conversation_resolution"
        ),
        "allow_force_pushes": payload.get("allow_force_pushes"),
        "allow_deletions": payload.get("allow_deletions"),
    }
    wanted = {
        "checks": expected_checks,
        "contexts": [],
        **{k: protection[k] for k in PROTECTION_KEYS},
    }
    for key, value in wanted.items():
        if observed[key] != value:
            failures.append(
                f"{relative}: payload {key} is {observed[key]!r}, policy requires {value!r}"
            )
    return failures


def check_contract_checker(policy: dict[str, Any], root: Path) -> list[str]:
    relative = policy["contract_checker"]
    path = root / relative
    spec = importlib.util.spec_from_file_location(
        "_merge_readiness_contract_for_policy", path
    )
    if spec is None or spec.loader is None:
        return [f"{relative}: cannot load"]
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception as exc:  # pragma: no cover - surfaced as a policy failure
        return [f"{relative}: import failed ({exc})"]
    declared = tuple(getattr(module, "REQUIRED_NEEDS", ()))
    expected = tuple(lane["job_id"] for lane in policy["aggregate_lanes"])
    if sorted(declared) != sorted(expected):
        return [
            f"{relative}: REQUIRED_NEEDS {declared} must equal policy lanes {expected}"
        ]
    return []


def check_docs(policy: dict[str, Any], root: Path) -> list[str]:
    failures: list[str] = []
    context = policy["required_status_checks"][0]["context"]
    for relative in policy["documentation"]:
        text = _read(root, relative, failures)
        if text is None:
            continue
        if f"**{context}**" not in text and f"**`{context}`**" not in text:
            failures.append(
                f"{relative}: must name the required check as **{context}**"
            )
        for lane in policy["aggregate_lanes"]:
            if lane["name"] not in text:
                failures.append(
                    f"{relative}: must document required lane {lane['name']!r}"
                )
        if ".github/ci/required-checks.json" not in text:
            failures.append(
                f"{relative}: must point at .github/ci/required-checks.json as the source of truth"
            )
    for relative in sorted({*policy["documentation"], *policy["name_references"]}):
        text = _read(root, relative, failures)
        if text is None:
            continue
        for stale in policy["stale_check_names"]:
            if stale in text:
                failures.append(
                    f"{relative}: references stale required check name {stale!r}; use {context!r}"
                )
    return failures


def run(root: Path, policy_path: Path) -> tuple[list[str], dict[str, Any] | None]:
    try:
        policy = load_policy(
            policy_path if policy_path.is_absolute() else root / policy_path
        )
    except PolicyError as exc:
        return [f"policy: {exc}"], None
    failures: list[str] = []
    for checker in (
        check_workflow,
        check_unique_context,
        check_protection_script,
        check_contract_checker,
        check_docs,
    ):
        failures.extend(checker(policy, root))
    return failures, policy


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--root",
        type=Path,
        default=ROOT,
        help="repository root (default: this checkout)",
    )
    parser.add_argument(
        "--policy",
        type=Path,
        default=DEFAULT_POLICY,
        help="policy path relative to --root",
    )
    args = parser.parse_args(argv)
    failures, policy = run(args.root.resolve(), args.policy)
    if failures:
        print("Required-check policy violations:")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    assert policy is not None
    check = policy["required_status_checks"][0]
    lanes = ", ".join(lane["name"] for lane in policy["aggregate_lanes"])
    print(
        f"Required-check policy passed: {policy['branch']} requires {check['context']!r} "
        f"(app {check['app_id']}) from {check['workflow_file']}; lanes: {lanes}."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
