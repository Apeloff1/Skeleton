#!/usr/bin/env python3
"""Validate mandatory signed/timestamped accountability for Skeleton AI construction."""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / "machine" / "ai_build_accountability.json"
HUMAN = ROOT / "docs" / "plan" / "BUILD_ACCOUNTABILITY_LEDGER.md"
MASTER = ROOT / "machine" / "ai_master_plan.json"
QUEUE = ROOT / "machine" / "ai_build_queue.json"
CATALOG = ROOT / "machine" / "ai_edge_case_catalog.json"
PRIORITY = ROOT / "machine" / "ai_edge_case_priority_queue.json"

SHA_RE = re.compile(r"^[0-9a-f]{40}$")
CHECK_RE = re.compile(r"^- \\[( |x)\\] .(ACC-[^\x60]+).", re.MULTILINE)
ALLOWED_SIGNER_TYPES = {"human", "agent", "ci", "service"}
ALLOWED_SIGNATURE_METHODS = {
    "github_identity",
    "git_gpg",
    "git_ssh",
    "sigstore",
    "ci_oidc",
}
SIGNATURE_REF_REQUIRED = {"git_gpg", "git_ssh", "sigstore", "ci_oidc"}


def _utc(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.endswith("Z"):
        return None
    try:
        return datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        return None


def _signoff_errors(record_id: str, label: str, signoff: object) -> list[str]:
    errors: list[str] = []
    if not isinstance(signoff, dict):
        return [f"{record_id}: {label} must be an object"]
    signed = signoff.get("signed")
    if signed is not True:
        for field in (
            "signer_id",
            "signer_type",
            "role",
            "signed_at_utc",
            "git_sha",
            "statement",
            "signature_method",
            "signature_ref",
        ):
            if signoff.get(field) not in (None, ""):
                errors.append(f"{record_id}: unsigned {label} contains {field}")
        if signoff.get("evidence_refs") not in ([], None):
            errors.append(f"{record_id}: unsigned {label} contains evidence_refs")
        return errors

    for field in ("signer_id", "role", "statement"):
        if not isinstance(signoff.get(field), str) or not signoff[field].strip():
            errors.append(f"{record_id}: signed {label} missing {field}")
    if signoff.get("signer_type") not in ALLOWED_SIGNER_TYPES:
        errors.append(f"{record_id}: signed {label} has invalid signer_type")
    if signoff.get("signature_method") not in ALLOWED_SIGNATURE_METHODS:
        errors.append(f"{record_id}: signed {label} has invalid signature_method")
    if _utc(signoff.get("signed_at_utc")) is None:
        errors.append(f"{record_id}: signed {label} needs RFC3339 UTC signed_at_utc")
    if not isinstance(signoff.get("git_sha"), str) or not SHA_RE.fullmatch(signoff["git_sha"]):
        errors.append(f"{record_id}: signed {label} needs full 40-character git SHA")
    refs = signoff.get("evidence_refs")
    if not isinstance(refs, list) or not refs or not all(isinstance(x, str) and x.strip() for x in refs):
        errors.append(f"{record_id}: signed {label} needs non-empty evidence_refs")
    if signoff.get("signature_method") in SIGNATURE_REF_REQUIRED:
        if not isinstance(signoff.get("signature_ref"), str) or not signoff["signature_ref"].strip():
            errors.append(f"{record_id}: {label} signature method requires signature_ref")
    return errors


def _exception_errors(record_id: str, exc: object) -> list[str]:
    if not isinstance(exc, dict):
        return [f"{record_id}: same-signer verification requires independence_exception"]
    errors: list[str] = []
    for field in ("approved_by", "reason"):
        if not isinstance(exc.get(field), str) or not exc[field].strip():
            errors.append(f"{record_id}: independence_exception missing {field}")
    if _utc(exc.get("signed_at_utc")) is None:
        errors.append(f"{record_id}: independence_exception needs RFC3339 UTC timestamp")
    if not isinstance(exc.get("git_sha"), str) or not SHA_RE.fullmatch(exc["git_sha"]):
        errors.append(f"{record_id}: independence_exception needs full git SHA")
    refs = exc.get("evidence_refs")
    if not isinstance(refs, list) or not refs:
        errors.append(f"{record_id}: independence_exception needs evidence_refs")
    if exc.get("signature_method") not in ALLOWED_SIGNATURE_METHODS:
        errors.append(f"{record_id}: independence_exception invalid signature_method")
    if exc.get("signature_method") in SIGNATURE_REF_REQUIRED and not exc.get("signature_ref"):
        errors.append(f"{record_id}: independence_exception requires signature_ref")
    return errors


def validate() -> list[str]:
    errors: list[str] = []
    for path in (LEDGER, HUMAN, MASTER, QUEUE, CATALOG, PRIORITY):
        if not path.is_file():
            errors.append(f"missing {path.relative_to(ROOT)}")
    if errors:
        return errors

    ledger = json.loads(LEDGER.read_text(encoding="utf-8"))
    master = json.loads(MASTER.read_text(encoding="utf-8"))
    queue = json.loads(QUEUE.read_text(encoding="utf-8"))
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    priority = json.loads(PRIORITY.read_text(encoding="utf-8"))
    records = ledger.get("records")
    if not isinstance(records, list):
        return ["ledger.records must be a list"]

    expected_ids = (
        [f"ACC-{v['key']}" for v in master["volumes"]]
        + [f"ACC-WP-W{i:02d}" for i in range(31)]
        + [f"ACC-{task['task_id']}" for task in queue["tasks"]]
        + [f"ACC-{vs}" for vs in master["vertical_slices"]]
        + [f"ACC-{entry['id']}" for entry in catalog["entries"]]
    )
    ids = [record.get("id") for record in records if isinstance(record, dict)]
    if ids != expected_ids:
        errors.append("accountability records must exactly match canonical tracked items in order")
    if len(ids) != len(set(ids)):
        errors.append("accountability record ids must be unique")

    counts = ledger.get("tracked_counts", {})
    if counts.get("volumes") != len(master["volumes"]):
        errors.append("tracked_counts.volumes is stale")
    if counts.get("work_packages") != 31:
        errors.append("tracked_counts.work_packages must equal 31")
    if counts.get("queue_tasks") != len(queue["tasks"]):
        errors.append("tracked_counts.queue_tasks is stale")
    if counts.get("vertical_slices") != len(master["vertical_slices"]):
        errors.append("tracked_counts.vertical_slices is stale")
    if counts.get("catalog_entries") != len(catalog["entries"]):
        errors.append("tracked_counts.catalog_entries is stale")
    if counts.get("total") != len(records):
        errors.append("tracked_counts.total is stale")

    record_by_id = {record["id"]: record for record in records}
    for record in records:
        rid = record.get("id", "?")
        checkbox = record.get("checkbox")
        mark = record.get("checkbox_mark")
        if checkbox not in (True, False):
            errors.append(f"{rid}: checkbox must be boolean")
        expected_mark = "[x]" if checkbox else "[ ]"
        if mark != expected_mark:
            errors.append(f"{rid}: checkbox_mark must equal {expected_mark}")
        if record.get("signing_required") is not True:
            errors.append(f"{rid}: signing_required must be true")

        impl = record.get("implementation_signoff")
        verify = record.get("verification_signoff")
        errors.extend(_signoff_errors(rid, "implementation_signoff", impl))
        errors.extend(_signoff_errors(rid, "verification_signoff", verify))
        impl_signed = isinstance(impl, dict) and impl.get("signed") is True
        verify_signed = isinstance(verify, dict) and verify.get("signed") is True

        if impl_signed and verify_signed and impl.get("signer_id") == verify.get("signer_id"):
            errors.extend(_exception_errors(rid, record.get("independence_exception")))

        history = record.get("history")
        if not isinstance(history, list):
            errors.append(f"{rid}: history must be a list")
            history = []
        last_seq = 0
        last_at: datetime | None = None
        for event in history:
            if not isinstance(event, dict):
                errors.append(f"{rid}: history events must be objects")
                continue
            seq = event.get("sequence")
            if not isinstance(seq, int) or seq != last_seq + 1:
                errors.append(f"{rid}: history sequence must be contiguous starting at 1")
                break
            last_seq = seq
            at = _utc(event.get("at_utc"))
            if at is None:
                errors.append(f"{rid}: history event {seq} missing RFC3339 UTC at_utc")
            elif last_at is not None and at < last_at:
                errors.append(f"{rid}: history timestamps must be monotonic")
            if at is not None:
                last_at = at
            if not isinstance(event.get("actor_id"), str) or not event["actor_id"].strip():
                errors.append(f"{rid}: history event {seq} missing actor_id")
            if not isinstance(event.get("git_sha"), str) or not SHA_RE.fullmatch(event["git_sha"]):
                errors.append(f"{rid}: history event {seq} needs full git SHA")
            if not isinstance(event.get("event_type"), str) or not event["event_type"].strip():
                errors.append(f"{rid}: history event {seq} missing event_type")
            if event.get("actor_type") not in ALLOWED_SIGNER_TYPES:
                errors.append(f"{rid}: history event {seq} invalid actor_type")
            if not isinstance(event.get("role"), str) or not event["role"].strip():
                errors.append(f"{rid}: history event {seq} missing role")
            if not isinstance(event.get("statement"), str) or not event["statement"].strip():
                errors.append(f"{rid}: history event {seq} missing statement")
            if event.get("signature_method") not in ALLOWED_SIGNATURE_METHODS:
                errors.append(f"{rid}: history event {seq} invalid signature_method")
            if event.get("signature_method") in SIGNATURE_REF_REQUIRED and not event.get("signature_ref"):
                errors.append(f"{rid}: history event {seq} requires signature_ref")
            if "from_status" not in event or "to_status" not in event:
                errors.append(f"{rid}: history event {seq} requires from_status/to_status")

        started = record.get("started_at_utc")
        if started is not None and _utc(started) is None:
            errors.append(f"{rid}: started_at_utc must be RFC3339 UTC")
        if started is not None and not any(e.get("event_type") == "started" for e in history if isinstance(e, dict)):
            errors.append(f"{rid}: started_at_utc requires a started history event")

        status = str(record.get("status", "")).lower()
        baseline_status = str(record.get("baseline_status", "")).lower()
        if not baseline_status:
            errors.append(f"{rid}: baseline_status is required")
        if status != baseline_status:
            if not history:
                errors.append(f"{rid}: changed status requires signed history")
            elif str(history[-1].get("to_status", "")).lower() != status:
                errors.append(f"{rid}: latest history to_status must match current status")
        if status in {"in_progress", "evidence_pending", "implemented", "integrated", "verified", "hardened", "production", "done", "closed", "accepted_risk"}:
            if _utc(started) is None:
                errors.append(f"{rid}: status {status} requires started_at_utc")
        if status in {"evidence_pending", "implemented", "integrated", "verified", "hardened", "production", "done", "closed", "accepted_risk"}:
            if not impl_signed:
                errors.append(f"{rid}: status {status} requires implementation signoff")
        if status in {"verified", "hardened", "production", "done", "closed", "accepted_risk"}:
            if not verify_signed:
                errors.append(f"{rid}: status {status} requires verification signoff")

        if checkbox:
            if not (impl_signed and verify_signed):
                errors.append(f"{rid}: checked item requires both signoffs")
            if _utc(record.get("completed_at_utc")) is None:
                errors.append(f"{rid}: checked item requires completed_at_utc")
            evidence = record.get("evidence")
            if not isinstance(evidence, list) or not evidence:
                errors.append(f"{rid}: checked item requires ledger evidence")
            if status not in {"verified", "hardened", "production", "done", "closed", "accepted_risk"}:
                errors.append(f"{rid}: checked item has non-terminal status {status}")
        elif record.get("completed_at_utc") is not None:
            errors.append(f"{rid}: unchecked item cannot have completed_at_utc")

    for task in queue["tasks"]:
        rid = task.get("accountability_id")
        rec = record_by_id.get(rid)
        if rec is None:
            errors.append(f"{task['task_id']}: missing accountability record")
            continue
        if task.get("accountability_required") is not True:
            errors.append(f"{task['task_id']}: accountability_required must be true")
        if str(task.get("status", "")).lower() != str(rec.get("status", "")).lower():
            errors.append(f"{task['task_id']}: queue status disagrees with accountability ledger")
        if task.get("completion_checkbox") != rec.get("checkbox"):
            errors.append(f"{task['task_id']}: queue checkbox disagrees with ledger")
        if task.get("completion_checkbox_mark") != rec.get("checkbox_mark"):
            errors.append(f"{task['task_id']}: queue checkbox mark disagrees with ledger")
        if task.get("implementation_signed") != bool(rec["implementation_signoff"].get("signed")):
            errors.append(f"{task['task_id']}: queue implementation_signed disagrees with ledger")
        if task.get("verification_signed") != bool(rec["verification_signoff"].get("signed")):
            errors.append(f"{task['task_id']}: queue verification_signed disagrees with ledger")

    for volume in master["volumes"]:
        rec = record_by_id.get(volume.get("accountability_id"))
        if rec is None:
            errors.append(f"{volume['key']}: missing accountability record")
            continue
        if volume.get("signing_required") is not True:
            errors.append(f"{volume['key']}: signing_required must be true")
        if str(volume.get("implementation_status", "")).lower() != str(rec.get("status", "")).lower():
            errors.append(f"{volume['key']}: volume implementation_status disagrees with accountability ledger")
        if volume.get("completion_checkbox") != rec.get("checkbox"):
            errors.append(f"{volume['key']}: volume checkbox disagrees with ledger")

    for entry in catalog["entries"]:
        rec = record_by_id.get(entry.get("accountability_id"))
        if rec is None:
            errors.append(f"{entry['id']}: missing accountability record")
            continue
        if entry.get("signing_required") is not True:
            errors.append(f"{entry['id']}: signing_required must be true")
        if entry.get("completion_checkbox") != rec.get("checkbox"):
            errors.append(f"{entry['id']}: catalog checkbox disagrees with ledger")
        if entry.get("completion_checkbox_mark") != rec.get("checkbox_mark"):
            errors.append(f"{entry['id']}: catalog checkbox mark disagrees with ledger")
        if str(entry.get("accountability_status", "")).lower() != str(rec.get("status", "")).lower():
            errors.append(f"{entry['id']}: catalog accountability_status disagrees with ledger")

    for item in priority["items"]:
        rec = record_by_id.get(item.get("accountability_id"))
        if rec is None:
            errors.append(f"{item['id']}: priority item missing accountability record")
            continue
        if item.get("signing_required") is not True:
            errors.append(f"{item['id']}: priority signing_required must be true")
        if item.get("completion_checkbox") != rec.get("checkbox"):
            errors.append(f"{item['id']}: priority checkbox disagrees with ledger")
        if item.get("completion_checkbox_mark") != rec.get("checkbox_mark"):
            errors.append(f"{item['id']}: priority checkbox mark disagrees with ledger")
        if str(item.get("accountability_status", item.get("status", ""))).lower() != str(rec.get("status", "")).lower():
            errors.append(f"{item['id']}: priority accountability status disagrees with ledger")

    human = HUMAN.read_text(encoding="utf-8")
    visible = {rid: mark for mark, rid in CHECK_RE.findall(human)}
    if len(visible) != len(records):
        errors.append(f"human ledger should expose {len(records)} checkboxes; found {len(visible)}")
    for record in records:
        rid = record["id"]
        expected = "x" if record["checkbox"] else " "
        if visible.get(rid) != expected:
            errors.append(f"{rid}: human checkbox disagrees with machine ledger")

    return errors


def main() -> int:
    errors = validate()
    if errors:
        print("AI build accountability: FAIL")
        for error in errors:
            print(f" - {error}")
        return 1
    ledger = json.loads(LEDGER.read_text(encoding="utf-8"))
    checked = sum(record["checkbox"] for record in ledger["records"])
    signed_impl = sum(record["implementation_signoff"]["signed"] for record in ledger["records"])
    signed_verify = sum(record["verification_signoff"]["signed"] for record in ledger["records"])
    print(
        "AI build accountability: OK "
        f"({ledger['tracked_counts']['total']} tracked; "
        f"{checked} checked; {signed_impl} implementation signoffs; "
        f"{signed_verify} verification signoffs)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
