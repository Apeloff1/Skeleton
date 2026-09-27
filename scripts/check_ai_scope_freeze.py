#!/usr/bin/env python3
"""Validate the P1 architecture scope freeze and ADR exception register."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
MASTER_PLAN_PATH = Path("machine/ai_master_plan.json")
REGISTER_PATH = Path("machine/ai_scope_freeze_adrs.json")
EXPECTED_LAST = 420
EXPECTED_COUNT = 421
EXPECTED_TASK_ID = "P1-EVID-06"
EXPECTED_ACCOUNTABILITY = "ACC-P1-EVID-06"
EXPECTED_STATUSES = {
    "proposed",
    "approved_future",
    "rejected",
    "withdrawn",
    "applied",
}
EXPECTED_ROLES = {"architecture_owner", "independent_verifier"}
ALLOWED_SIGNATURE_METHODS = {
    "github_identity",
    "gpg",
    "ssh_signing",
    "sigstore",
    "ci_oidc",
}
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_ADR_RE = re.compile(r"^ADR-SCOPE-[0-9]{4,}$")
_VOLUME_RE = re.compile(r"^VOL-([0-9]+)$")


class ScopeFreezeValidationError(RuntimeError):
    """Scope-freeze authority could not be read or validated."""


def _load(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ScopeFreezeValidationError(f"cannot read {path}") from exc


def _canonical_digest(value: object) -> str:
    raw = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _nonempty_text(value: object) -> bool:
    return isinstance(value, str) and bool(value) and value == value.strip()


def _utc_text(value: object) -> bool:
    if not _nonempty_text(value):
        return False
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None and parsed.utcoffset() is not None


def _materialized_refs(value: object) -> bool:
    return (
        isinstance(value, list)
        and bool(value)
        and all(
            _nonempty_text(item) and not str(item).startswith("planned:")
            for item in value
        )
    )


def _approval_errors(
    entry_id: str,
    approvals: object,
) -> list[str]:
    errors: list[str] = []
    if not isinstance(approvals, list):
        return [f"{entry_id}: approvals must be a list"]
    roles: set[str] = set()
    signers: set[str] = set()
    for index, approval in enumerate(approvals):
        label = f"{entry_id}: approval[{index}]"
        if not isinstance(approval, dict):
            errors.append(f"{label} must be an object")
            continue
        role = approval.get("role")
        signer = approval.get("signer")
        method = approval.get("method")
        timestamp = approval.get("timestamp")
        commit_sha = approval.get("commit_sha")
        evidence_refs = approval.get("evidence_refs")
        if role not in EXPECTED_ROLES:
            errors.append(f"{label} has invalid role")
        else:
            roles.add(str(role))
        if not _nonempty_text(signer):
            errors.append(f"{label} signer must be non-empty")
        else:
            signers.add(str(signer))
        if method not in ALLOWED_SIGNATURE_METHODS:
            errors.append(f"{label} signature method is not identity-bound")
        if not _utc_text(timestamp):
            errors.append(f"{label} timestamp must be timezone-aware ISO-8601")
        if not isinstance(commit_sha, str) or not _SHA_RE.fullmatch(commit_sha):
            errors.append(f"{label} commit_sha must be a full lowercase git SHA")
        if not _materialized_refs(evidence_refs):
            errors.append(f"{label} evidence_refs must be materialized")
    if roles != EXPECTED_ROLES:
        errors.append(f"{entry_id}: approvals must cover both required roles")
    if len(signers) < 2:
        errors.append(f"{entry_id}: approvals require distinct signers")
    return errors


def _entry_errors(
    entry: object,
    *,
    existing_volume_keys: set[str],
    seen_ids: set[str],
    seen_requested_ids: set[int],
    active_p1_forbids_application: bool,
) -> list[str]:
    errors: list[str] = []
    if not isinstance(entry, dict):
        return ["scope-freeze ADR entries must be objects"]

    entry_id = entry.get("id")
    if not isinstance(entry_id, str) or not _ADR_RE.fullmatch(entry_id):
        errors.append("scope-freeze ADR id must match ADR-SCOPE-NNNN")
        entry_id = str(entry_id or "?")
    elif entry_id in seen_ids:
        errors.append(f"duplicate scope-freeze ADR id: {entry_id}")
    else:
        seen_ids.add(entry_id)

    status = entry.get("status")
    if status not in EXPECTED_STATUSES:
        errors.append(f"{entry_id}: invalid status {status!r}")

    requested_id = entry.get("requested_volume_id")
    if (
        isinstance(requested_id, bool)
        or not isinstance(requested_id, int)
        or requested_id <= EXPECTED_LAST
    ):
        errors.append(
            f"{entry_id}: requested_volume_id must be greater than {EXPECTED_LAST}"
        )
    else:
        if requested_id in seen_requested_ids:
            errors.append(
                f"{entry_id}: duplicate requested_volume_id {requested_id}"
            )
        seen_requested_ids.add(requested_id)
        expected_key = f"VOL-{requested_id:03d}"
        if entry.get("requested_key") != expected_key:
            errors.append(
                f"{entry_id}: requested_key must equal {expected_key}"
            )

    for field in (
        "title",
        "requirement",
        "requested_by",
        "rationale",
    ):
        if not _nonempty_text(entry.get(field)):
            errors.append(f"{entry_id}: {field} must be non-empty")

    if not _utc_text(entry.get("created_at")):
        errors.append(f"{entry_id}: created_at must be timezone-aware ISO-8601")

    analysis = entry.get("existing_volume_analysis")
    if not isinstance(analysis, list) or len(analysis) < 2:
        errors.append(
            f"{entry_id}: existing_volume_analysis must cover at least two volumes"
        )
    else:
        refs: set[str] = set()
        for index, row in enumerate(analysis):
            label = f"{entry_id}: existing_volume_analysis[{index}]"
            if not isinstance(row, dict):
                errors.append(f"{label} must be an object")
                continue
            ref = row.get("volume_ref")
            insufficiency = row.get("insufficiency")
            if ref not in existing_volume_keys:
                errors.append(f"{label} references unknown existing volume")
            elif ref in refs:
                errors.append(f"{label} duplicates existing volume analysis")
            else:
                refs.add(str(ref))
            if not _nonempty_text(insufficiency):
                errors.append(f"{label} insufficiency must be non-empty")

    alternatives = entry.get("alternatives_considered")
    if not isinstance(alternatives, list) or not alternatives:
        errors.append(f"{entry_id}: alternatives_considered must be non-empty")
    elif not all(_nonempty_text(item) for item in alternatives):
        errors.append(
            f"{entry_id}: alternatives_considered must contain normalized text"
        )

    approvals = entry.get("approvals", [])
    if status in {"approved_future", "applied"}:
        errors.extend(_approval_errors(entry_id, approvals))
        if not _nonempty_text(entry.get("decision_summary")):
            errors.append(f"{entry_id}: approved ADR requires decision_summary")
        if not _utc_text(entry.get("reviewed_at")):
            errors.append(
                f"{entry_id}: approved ADR requires timezone-aware reviewed_at"
            )
    elif approvals not in ([], None):
        errors.append(
            f"{entry_id}: non-approved ADR must not carry approval signatures"
        )

    if status == "applied":
        if active_p1_forbids_application:
            errors.append(
                f"{entry_id}: applied scope expansion is forbidden during active P1"
            )
        if not _nonempty_text(entry.get("applied_plan_version")):
            errors.append(f"{entry_id}: applied ADR requires applied_plan_version")
        applied_sha = entry.get("applied_commit_sha")
        if not isinstance(applied_sha, str) or not _SHA_RE.fullmatch(applied_sha):
            errors.append(f"{entry_id}: applied ADR requires full applied_commit_sha")

    return errors


def validate_repository(root: Path = ROOT) -> tuple[list[str], dict[str, Any]]:
    errors: list[str] = []
    master = _load(root / MASTER_PLAN_PATH)
    register = _load(root / REGISTER_PATH)
    if not isinstance(master, dict):
        raise ScopeFreezeValidationError("master plan must be an object")
    if not isinstance(register, dict):
        raise ScopeFreezeValidationError("scope-freeze register must be an object")

    authority = master.get("authority")
    if not isinstance(authority, dict):
        errors.append("master plan authority must be an object")
    elif authority.get("p1_scope_freeze_adr_register") != str(REGISTER_PATH):
        errors.append("master plan scope-freeze ADR authority pointer drift")

    freeze = master.get("breadth_freeze")
    if not isinstance(freeze, dict):
        errors.append("master plan breadth_freeze must be an object")
        freeze = {}
    if freeze.get("enabled") is not True:
        errors.append("breadth freeze must remain enabled")
    if freeze.get("last_top_level_volume") != EXPECTED_LAST:
        errors.append(f"active P1 breadth boundary must remain VOL-{EXPECTED_LAST:03d}")
    if freeze.get("exception_register") != str(REGISTER_PATH):
        errors.append("breadth freeze exception_register pointer drift")
    if freeze.get("p1_application_policy") != "forbid":
        errors.append("breadth freeze p1_application_policy must equal forbid")

    volumes = master.get("volumes")
    if not isinstance(volumes, list):
        errors.append("master plan volumes must be a list")
        volumes = []
    ids = [
        row.get("id")
        for row in volumes
        if isinstance(row, dict)
    ]
    keys = {
        str(row.get("key"))
        for row in volumes
        if isinstance(row, dict) and isinstance(row.get("key"), str)
    }
    if len(volumes) != EXPECTED_COUNT:
        errors.append(
            f"active P1 scope requires exactly {EXPECTED_COUNT} top-level volumes"
        )
    if ids != list(range(EXPECTED_COUNT)):
        errors.append(
            f"active P1 volume ids must remain contiguous 0..{EXPECTED_LAST}"
        )
    if any(
        isinstance(row, dict)
        and isinstance(row.get("id"), int)
        and row["id"] > EXPECTED_LAST
        for row in volumes
    ):
        errors.append("unapproved top-level volume exceeds active P1 breadth freeze")

    if register.get("schema_version") != 1:
        errors.append("scope-freeze register schema_version must equal 1")
    if register.get("task_id") != EXPECTED_TASK_ID:
        errors.append("scope-freeze register task_id drift")
    if register.get("accountability_ref") != EXPECTED_ACCOUNTABILITY:
        errors.append("scope-freeze register accountability_ref drift")
    if register.get("authority") != str(REGISTER_PATH):
        errors.append("scope-freeze register self-authority path drift")

    baseline = register.get("baseline")
    if not isinstance(baseline, dict):
        errors.append("scope-freeze baseline must be an object")
        baseline = {}
    if baseline.get("frozen_last_top_level_volume") != EXPECTED_LAST:
        errors.append("scope-freeze baseline last volume drift")
    if baseline.get("frozen_volume_count") != EXPECTED_COUNT:
        errors.append("scope-freeze baseline count drift")
    active_p1_forbids_application = (
        baseline.get("active_p1_forbids_application") is True
    )
    if not active_p1_forbids_application:
        errors.append("active P1 must forbid applied scope expansion")

    statuses = register.get("statuses")
    if not isinstance(statuses, list) or set(statuses) != EXPECTED_STATUSES:
        errors.append("scope-freeze ADR status inventory drift")

    approval_policy = register.get("approval_policy")
    if not isinstance(approval_policy, dict):
        errors.append("scope-freeze approval_policy must be an object")
    else:
        if set(approval_policy.get("required_roles", [])) != EXPECTED_ROLES:
            errors.append("scope-freeze required approval roles drift")
        if set(
            approval_policy.get("allowed_signature_methods", [])
        ) != ALLOWED_SIGNATURE_METHODS:
            errors.append("scope-freeze allowed signature methods drift")
        for field in (
            "full_git_sha_required",
            "materialized_evidence_required",
            "distinct_signers_required",
        ):
            if approval_policy.get(field) is not True:
                errors.append(f"scope-freeze approval policy {field} must be true")

    application = register.get("application_policy")
    if not isinstance(application, dict):
        errors.append("scope-freeze application_policy must be an object")
    else:
        if application.get("p1_mode") != "forbid":
            errors.append("scope-freeze application policy p1_mode must be forbid")
        for field in (
            "requires_plan_version_change",
            "requires_master_index_update",
            "requires_depth_pass_update",
            "requires_execution_map_amendment_or_terminal_p1",
            "contiguous_volume_ids_only",
        ):
            if application.get(field) is not True:
                errors.append(f"scope-freeze application policy {field} must be true")

    entries = register.get("entries")
    if not isinstance(entries, list):
        errors.append("scope-freeze entries must be a list")
        entries = []

    seen_ids: set[str] = set()
    seen_requested_ids: set[int] = set()
    for entry in entries:
        errors.extend(
            _entry_errors(
                entry,
                existing_volume_keys=keys,
                seen_ids=seen_ids,
                seen_requested_ids=seen_requested_ids,
                active_p1_forbids_application=active_p1_forbids_application,
            )
        )

    applied = [
        entry
        for entry in entries
        if isinstance(entry, dict) and entry.get("status") == "applied"
    ]
    if applied:
        errors.append("active P1 scope-freeze register must contain zero applied ADRs")

    summary = {
        "schema_version": 1,
        "task_id": EXPECTED_TASK_ID,
        "accountability_ref": EXPECTED_ACCOUNTABILITY,
        "frozen_last_top_level_volume": EXPECTED_LAST,
        "frozen_volume_count": EXPECTED_COUNT,
        "adr_count": len(entries),
        "approved_future_count": sum(
            1
            for entry in entries
            if isinstance(entry, dict)
            and entry.get("status") == "approved_future"
        ),
        "applied_count": len(applied),
        "master_plan_digest": _canonical_digest(master),
        "adr_register_digest": _canonical_digest(register),
        "valid": not errors,
        "errors": errors,
    }
    return errors, summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--print-summary", action="store_true")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)

    try:
        errors, summary = validate_repository(ROOT)
    except ScopeFreezeValidationError as exc:
        print(f"P1 scope freeze: rejected: {exc}", file=sys.stderr)
        return 2

    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(
            json.dumps(summary, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    if args.print_summary:
        print(json.dumps(summary, indent=2, sort_keys=True))
    if errors:
        for error in errors:
            print(f"P1 scope freeze: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
