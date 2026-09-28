#!/usr/bin/env python3
"""Batch P1 accountability transitions through the canonical signer.

This wrapper creates no new signing authority. Every transition is delegated to
scripts/ai_accountability.py. A batch performs one explicit lifecycle phase,
preflights every requested P1 record with --dry-run, snapshots every canonical
accountability surface, then applies each transition sequentially. If any apply
or post-batch validation fails, the snapshot is restored.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
SIGNER = ROOT / "scripts" / "ai_accountability.py"
VALIDATOR = ROOT / "scripts" / "check_ai_build_accountability.py"

CANONICAL_PATHS = (
    ROOT / "machine" / "ai_build_accountability.json",
    ROOT / "machine" / "ai_master_plan.json",
    ROOT / "machine" / "ai_build_queue.json",
    ROOT / "machine" / "ai_p1_task_backlog.json",
    ROOT / "machine" / "ai_edge_case_catalog.json",
    ROOT / "machine" / "ai_edge_case_priority_queue.json",
    ROOT / "docs" / "plan" / "BUILD_ACCOUNTABILITY_LEDGER.md",
)

ACTIONS = {
    "start",
    "sign-implementation",
    "sign-verification",
    "complete",
}


def normalize_record_ids(values: Iterable[str]) -> tuple[str, ...]:
    result: list[str] = []
    seen: set[str] = set()
    for raw in values:
        value = raw.strip()
        if not value:
            raise SystemExit("record id must not be empty")
        if not value.startswith("ACC-P1-"):
            raise SystemExit(
                "P1 batch accepts only ACC-P1-* accountability records: "
                + value
            )
        if value in seen:
            raise SystemExit("duplicate accountability record: " + value)
        seen.add(value)
        result.append(value)
    if not result:
        raise SystemExit("at least one --record-id is required")
    return tuple(result)


def signer_command(
    *,
    action: str,
    record_id: str,
    actor_id: str,
    actor_type: str,
    role: str,
    statement: str,
    signature_method: str,
    signature_ref: str | None,
    git_sha: str,
    evidence: tuple[str, ...],
    dry_run: bool,
) -> list[str]:
    if action not in ACTIONS:
        raise SystemExit("unsupported P1 accountability action: " + action)

    command = [
        sys.executable,
        str(SIGNER),
        action,
        record_id,
        "--actor-id",
        actor_id,
        "--actor-type",
        actor_type,
        "--role",
        role,
        "--statement",
        statement,
        "--signature-method",
        signature_method,
        "--git-sha",
        git_sha,
    ]
    if signature_ref:
        command.extend(["--signature-ref", signature_ref])
    for reference in evidence:
        command.extend(["--evidence", reference])
    if dry_run:
        command.append("--dry-run")
    return command


def snapshot() -> dict[Path, bytes]:
    missing = [path for path in CANONICAL_PATHS if not path.is_file()]
    if missing:
        raise SystemExit(
            "canonical accountability surface is missing: "
            + ", ".join(str(path.relative_to(ROOT)) for path in missing)
        )
    return {path: path.read_bytes() for path in CANONICAL_PATHS}


def restore(state: dict[Path, bytes]) -> None:
    for path, payload in state.items():
        path.write_bytes(payload)


def run_checked(command: list[str]) -> None:
    result = subprocess.run(command, cwd=ROOT)
    if result.returncode:
        raise subprocess.CalledProcessError(result.returncode, command)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=sorted(ACTIONS))
    parser.add_argument("--record-id", action="append", default=[])
    parser.add_argument("--actor-id", required=True)
    parser.add_argument(
        "--actor-type",
        choices=("agent", "ci", "human", "service"),
        required=True,
    )
    parser.add_argument("--role", required=True)
    parser.add_argument("--statement", required=True)
    parser.add_argument(
        "--signature-method",
        choices=("ci_oidc", "git_gpg", "git_ssh", "github_identity", "sigstore"),
        required=True,
    )
    parser.add_argument("--signature-ref")
    parser.add_argument("--git-sha", required=True)
    parser.add_argument("--evidence", action="append", default=[])
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="preflight only; do not mutate canonical accountability surfaces",
    )
    args = parser.parse_args()

    record_ids = normalize_record_ids(args.record_id)
    evidence = tuple(dict.fromkeys(item.strip() for item in args.evidence if item.strip()))

    # Canonical signer owns all identity/evidence/state validation. Preflight
    # every record before a single persistent mutation can occur.
    for record_id in record_ids:
        run_checked(
            signer_command(
                action=args.action,
                record_id=record_id,
                actor_id=args.actor_id,
                actor_type=args.actor_type,
                role=args.role,
                statement=args.statement,
                signature_method=args.signature_method,
                signature_ref=args.signature_ref,
                git_sha=args.git_sha,
                evidence=evidence,
                dry_run=True,
            )
        )

    if args.dry_run:
        return 0

    before = snapshot()
    try:
        for record_id in record_ids:
            run_checked(
                signer_command(
                    action=args.action,
                    record_id=record_id,
                    actor_id=args.actor_id,
                    actor_type=args.actor_type,
                    role=args.role,
                    statement=args.statement,
                    signature_method=args.signature_method,
                    signature_ref=args.signature_ref,
                    git_sha=args.git_sha,
                    evidence=evidence,
                    dry_run=False,
                )
            )
        run_checked([sys.executable, str(VALIDATOR)])
    except (subprocess.CalledProcessError, OSError):
        restore(before)
        subprocess.run([sys.executable, str(VALIDATOR)], cwd=ROOT)
        raise

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
