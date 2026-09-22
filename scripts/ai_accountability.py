#!/usr/bin/env python3
"""Safely update Skeleton AI build-accountability records.

Every mutating command records a signed-attribution history event with an
RFC3339 UTC timestamp and git revision, updates canonical mirrors, regenerates
the visible Markdown checklist, and runs the accountability validator.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / "machine" / "ai_build_accountability.json"
MASTER = ROOT / "machine" / "ai_master_plan.json"
QUEUE = ROOT / "machine" / "ai_build_queue.json"
CATALOG = ROOT / "machine" / "ai_edge_case_catalog.json"
PRIORITY = ROOT / "machine" / "ai_edge_case_priority_queue.json"
HUMAN = ROOT / "docs" / "plan" / "BUILD_ACCOUNTABILITY_LEDGER.md"
VALIDATOR = ROOT / "scripts" / "check_ai_build_accountability.py"

SIGNATURE_METHODS = {"github_identity", "git_gpg", "git_ssh", "sigstore", "ci_oidc"}
SIGNATURE_REF_REQUIRED = {"git_gpg", "git_ssh", "sigstore", "ci_oidc"}
ACTOR_TYPES = {"human", "agent", "ci", "service"}


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def git_sha(explicit: str | None) -> str:
    if explicit:
        value = explicit.strip().lower()
    else:
        value = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip().lower()
    if len(value) != 40 or any(ch not in "0123456789abcdef" for ch in value):
        raise SystemExit("git SHA must be a full 40-character hexadecimal revision")
    return value


def require_identity(args: argparse.Namespace) -> None:
    if args.actor_type not in ACTOR_TYPES:
        raise SystemExit(f"invalid actor type: {args.actor_type}")
    if args.signature_method not in SIGNATURE_METHODS:
        raise SystemExit(f"invalid signature method: {args.signature_method}")
    if args.signature_method in SIGNATURE_REF_REQUIRED and not args.signature_ref:
        raise SystemExit(f"{args.signature_method} requires --signature-ref")


def history_event(
    record: dict[str, Any],
    args: argparse.Namespace,
    event_type: str,
    from_status: str,
    to_status: str,
    at: str,
    sha: str,
) -> dict[str, Any]:
    return {
        "sequence": len(record["history"]) + 1,
        "event_type": event_type,
        "actor_id": args.actor_id,
        "actor_type": args.actor_type,
        "role": args.role,
        "at_utc": at,
        "git_sha": sha,
        "statement": args.statement,
        "signature_method": args.signature_method,
        "signature_ref": args.signature_ref,
        "from_status": from_status,
        "to_status": to_status,
        "evidence_refs": list(args.evidence or []),
    }


def signoff(args: argparse.Namespace, at: str, sha: str) -> dict[str, Any]:
    evidence = list(args.evidence or [])
    if not evidence:
        raise SystemExit("sign-off requires at least one --evidence reference")
    return {
        "signed": True,
        "signer_id": args.actor_id,
        "signer_type": args.actor_type,
        "role": args.role,
        "signed_at_utc": at,
        "git_sha": sha,
        "evidence_refs": evidence,
        "statement": args.statement,
        "signature_method": args.signature_method,
        "signature_ref": args.signature_ref,
    }


def type_status(record: dict[str, Any], phase: str) -> str:
    typ = record["type"]
    if phase == "start":
        return "in_progress"
    if phase == "implementation":
        return "evidence_pending" if typ in {"queue_task", "catalog_entry"} else "implemented"
    if phase == "verification":
        if typ == "catalog_entry":
            return "passing"
        if typ == "queue_task":
            return "evidence_pending"
        return "verified"
    if phase == "complete":
        if typ == "queue_task":
            return "done"
        if typ == "catalog_entry":
            return "closed"
        return "verified"
    if phase == "accepted_risk":
        if typ != "catalog_entry":
            raise SystemExit("accepted-risk is only valid for catalog entries")
        return "accepted_risk"
    raise SystemExit(f"unknown phase: {phase}")


def sync_mirrors(
    record: dict[str, Any],
    master: dict[str, Any],
    queue: dict[str, Any],
    catalog: dict[str, Any],
    priority: dict[str, Any],
) -> None:
    rid = record["id"]
    for task in queue["tasks"]:
        if task.get("accountability_id") == rid:
            task["status"] = record["status"]
            task["completion_checkbox"] = record["checkbox"]
            task["completion_checkbox_mark"] = record["checkbox_mark"]
            task["implementation_signed"] = record["implementation_signoff"]["signed"]
            task["verification_signed"] = record["verification_signoff"]["signed"]

    for volume in master["volumes"]:
        if volume.get("accountability_id") == rid:
            volume["implementation_status"] = record["status"]
            volume["completion_checkbox"] = record["checkbox"]
            volume["completion_checkbox_mark"] = record["checkbox_mark"]

    for entry in catalog["entries"]:
        if entry.get("accountability_id") == rid:
            entry["accountability_status"] = record["status"]
            entry["completion_checkbox"] = record["checkbox"]
            entry["completion_checkbox_mark"] = record["checkbox_mark"]

    for item in priority["items"]:
        if item.get("accountability_id") == rid:
            item["status"] = record["status"]
            item["accountability_status"] = record["status"]
            item["completion_checkbox"] = record["checkbox"]
            item["completion_checkbox_mark"] = record["checkbox_mark"]


def render(ledger: dict[str, Any]) -> str:
    lines = [
        "# Skeleton AI Build Accountability Ledger",
        "",
        "Architecture lane: `PR #1904 / integration/architecture-map-v1`",
        "",
        "Machine authority: [`machine/ai_build_accountability.json`](../../machine/ai_build_accountability.json)",
        "",
        "## Mandatory accountability protocol",
        "",
        "Checkboxes are derived from signed machine state. Do not hand-edit them.",
        "",
        "Identity-bound signature methods: GitHub identity, GPG, SSH signing, Sigstore, or CI OIDC.",
        "",
    ]

    def section(title: str, records: list[dict[str, Any]]) -> None:
        lines.extend([f"## {title}", ""])
        for record in records:
            impl = record["implementation_signoff"]
            verify = record["verification_signoff"]
            builder = impl["signer_id"] if impl["signed"] else "UNSIGNED"
            verifier = verify["signer_id"] if verify["signed"] else "UNSIGNED"
            completed = record["completed_at_utc"] or "—"
            lines.append(
                f"- {record['checkbox_mark']} `{record['id']}` — {record['title']} "
                f"— status: `{record['status']}` — builder: **{builder}** "
                f"— verifier: **{verifier}** — completed_at_utc: `{completed}`"
            )
        lines.append("")

    records = ledger["records"]
    section("Volumes 000–420", [r for r in records if r["type"] == "volume"])
    section("Work Packages W00–W30", [r for r in records if r["type"] == "work_package"])
    section("Atomic AI Build Queue", [r for r in records if r["type"] == "queue_task"])
    section("Vertical Slices", [r for r in records if r["type"] == "vertical_slice"])
    section("Historical / Edge / Obscure Catalogue", [r for r in records if r["type"] == "catalog_entry"])
    return "\n".join(lines) + "\n"


def persist(
    ledger: dict[str, Any],
    master: dict[str, Any],
    queue: dict[str, Any],
    catalog: dict[str, Any],
    priority: dict[str, Any],
) -> None:
    LEDGER.write_text(json.dumps(ledger, indent=2) + "\n", encoding="utf-8")
    MASTER.write_text(json.dumps(master, indent=2) + "\n", encoding="utf-8")
    QUEUE.write_text(json.dumps(queue, indent=2) + "\n", encoding="utf-8")
    CATALOG.write_text(json.dumps(catalog, indent=2) + "\n", encoding="utf-8")
    PRIORITY.write_text(json.dumps(priority, indent=2) + "\n", encoding="utf-8")
    HUMAN.write_text(render(ledger), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "action",
        choices=[
            "start",
            "sign-implementation",
            "sign-verification",
            "complete",
            "accept-risk",
            "set-status",
            "show",
        ],
    )
    parser.add_argument("record_id")
    parser.add_argument("--actor-id")
    parser.add_argument("--actor-type", choices=sorted(ACTOR_TYPES))
    parser.add_argument("--role")
    parser.add_argument("--statement")
    parser.add_argument("--signature-method", choices=sorted(SIGNATURE_METHODS))
    parser.add_argument("--signature-ref")
    parser.add_argument("--git-sha")
    parser.add_argument("--evidence", action="append", default=[])
    parser.add_argument("--to-status")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    ledger = load(LEDGER)
    master = load(MASTER)
    queue = load(QUEUE)
    catalog = load(CATALOG)
    priority = load(PRIORITY)
    records = {record["id"]: record for record in ledger["records"]}
    if args.record_id not in records:
        raise SystemExit(f"unknown accountability record: {args.record_id}")
    record = records[args.record_id]

    if args.action == "show":
        print(json.dumps(record, indent=2))
        return 0

    for field in ("actor_id", "actor_type", "role", "statement", "signature_method"):
        if not getattr(args, field):
            raise SystemExit(f"--{field.replace('_', '-')} is required")
    require_identity(args)
    at = now_utc()
    sha = git_sha(args.git_sha)
    previous = record["status"]

    if args.action == "start":
        if record["started_at_utc"] is not None:
            raise SystemExit("record already has a start timestamp")
        target = type_status(record, "start")
        record["started_at_utc"] = at
        record["status"] = target
        record["history"].append(history_event(record, args, "started", previous, target, at, sha))

    elif args.action == "sign-implementation":
        if record["started_at_utc"] is None:
            raise SystemExit("start the record before implementation sign-off")
        if record["implementation_signoff"]["signed"]:
            raise SystemExit("implementation already signed; supersede via a new governed change rather than rewriting")
        target = type_status(record, "implementation")
        record["implementation_signoff"] = signoff(args, at, sha)
        record["status"] = target
        record["history"].append(
            history_event(record, args, "implementation_signed", previous, target, at, sha)
        )
        record["evidence"] = sorted(set(record["evidence"] + list(args.evidence)))

    elif args.action == "sign-verification":
        if not record["implementation_signoff"]["signed"]:
            raise SystemExit("implementation sign-off is required before verification")
        if record["verification_signoff"]["signed"]:
            raise SystemExit("verification already signed")
        if record["implementation_signoff"]["signer_id"] == args.actor_id:
            raise SystemExit("verification signer must differ from implementation signer")
        target = type_status(record, "verification")
        record["verification_signoff"] = signoff(args, at, sha)
        record["status"] = target
        record["history"].append(
            history_event(record, args, "verification_signed", previous, target, at, sha)
        )
        record["evidence"] = sorted(set(record["evidence"] + list(args.evidence)))

    elif args.action in {"complete", "accept-risk"}:
        if not (
            record["implementation_signoff"]["signed"]
            and record["verification_signoff"]["signed"]
        ):
            raise SystemExit("both implementation and independent verification sign-offs are required")
        phase = "accepted_risk" if args.action == "accept-risk" else "complete"
        target = type_status(record, phase)
        record["status"] = target
        record["checkbox"] = True
        record["checkbox_mark"] = "[x]"
        record["completed_at_utc"] = at
        record["history"].append(
            history_event(record, args, "accepted_risk" if phase == "accepted_risk" else "completed", previous, target, at, sha)
        )
        record["evidence"] = sorted(set(record["evidence"] + list(args.evidence)))

    elif args.action == "set-status":
        if not args.to_status:
            raise SystemExit("--to-status is required")
        target = args.to_status.strip().lower()
        if target in {"done", "closed", "accepted_risk", "verified", "hardened", "production"}:
            raise SystemExit("terminal statuses must use complete/accept-risk after sign-offs")
        record["status"] = target
        record["history"].append(history_event(record, args, "status_changed", previous, target, at, sha))

    record["last_event_at_utc"] = at
    sync_mirrors(record, master, queue, catalog, priority)

    if args.dry_run:
        print(json.dumps(record, indent=2))
        return 0

    persist(ledger, master, queue, catalog, priority)
    result = subprocess.run([sys.executable, str(VALIDATOR)], cwd=ROOT)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
