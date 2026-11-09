#!/usr/bin/env python3
"""Merge independently uploaded E2E shard receipts into one fail-closed ledger."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import sys

from e2e_evidence import DEFAULT_MANIFEST, load_manifest

EXPECTED = tuple(suite["id"] for suite in load_manifest(DEFAULT_MANIFEST) if suite["tier"] == "offline")
MAX_BYTES = 2_000_000


def read_json(path: Path) -> dict:
    if path.stat().st_size > MAX_BYTES:
        raise ValueError("oversize receipt")
    obj = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(obj, dict):
        raise ValueError("receipt is not a mapping")
    return obj


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifacts", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    issue_map: dict[str, dict] = {}
    receipts: dict[str, dict] = {}
    errors = []

    def issue(kind, suite, detail):
        identity = f"{kind}|{suite}"
        uid = "E2E-AGG-" + hashlib.sha256(identity.encode()).hexdigest()[:16].upper()
        issue_map[uid] = {
            "id": uid, "severity": "high", "status": "open",
            "suite": suite, "kind": kind, "summary": detail,
            "phase": "aggregation", "evidence": "aggregate.json",
        }

    root = args.artifacts.resolve()
    if not root.is_dir():
        issue("missing-artifact-root", "aggregate", "No downloaded shard artifacts directory")
    else:
        for folder in sorted(root.iterdir()):
            if not folder.is_dir() or not folder.name.startswith("e2e-"):
                continue
            report_path = folder / "report.json"
            issues_path = folder / "issues.json"
            if not report_path.exists() or not issues_path.exists():
                continue
            try:
                report = read_json(report_path)
                issue_payload = read_json(issues_path)
                if report.get("schema") != "skeleton.e2e.evidence.v1":
                    raise ValueError("unknown report schema")
                if report.get("mode") != "offline-e2e":
                    continue
                suites = report.get("suites")
                if not isinstance(suites, list) or len(suites) != 1 or not isinstance(suites[0], dict):
                    raise ValueError("one shard must carry exactly one suite receipt")
                suite = suites[0].get("id")
                if suite not in EXPECTED:
                    raise ValueError("unknown suite receipt")
                if suite in receipts:
                    issue("duplicate-shard", suite, "Multiple receipts for same suite")
                    continue
                if issue_payload.get("schema") != "skeleton.e2e.issues.v1":
                    raise ValueError("unknown issues schema")
                items = issue_payload.get("issues")
                if not isinstance(items, list):
                    raise ValueError("missing issue list")
                if not re.fullmatch(r"[0-9a-f]{40}", str(report.get("head_sha", ""))):
                    raise ValueError("shard must identify an exact commit")
                receipt = suites[0]
                duration = receipt.get("duration_seconds")
                if isinstance(duration, bool) or not isinstance(duration, (int, float)) or not math.isfinite(duration) or duration < 0:
                    raise ValueError("invalid duration")
                if report.get("issues_count") != len(items) or report.get("executed_suites") != 1:
                    raise ValueError("report counts disagree with shard evidence")
                if receipt.get("status") not in ("passed", "failed"):
                    raise ValueError("shard did not execute")
                if receipt["status"] == "passed" and (
                    report.get("status") != "passed" or items or type(receipt.get("exit_code")) is not int
                    or receipt["exit_code"] != 0 or receipt.get("timed_out") is not False
                ):
                    raise ValueError("passing shard contradicts its execution evidence")
                if any(not isinstance(item, dict) or not isinstance(item.get("id"), str) for item in items):
                    raise ValueError("invalid issue item")
                receipts[suite] = {
                    "artifact": folder.name, "status": suites[0].get("status"),
                    "duration_seconds": suites[0].get("duration_seconds"),
                    "head_sha": report.get("head_sha"),
                    "run_id": report.get("run_id"),
                    "issues": len(items),
                }
                for item in items:
                    key = item["id"]
                    # Retain normalized metadata only: no arbitrary exception
                    # payloads are re-read from raw console logs.
                    issue_map[key] = {
                        field: item.get(field, "") for field in
                        ("id", "severity", "status", "suite", "phase", "kind",
                         "testcase", "summary", "evidence", "head_sha")
                    }
            except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
                errors.append(folder.name)
                issue("invalid-shard", folder.name,
                      "Unreadable or invalid receipt (" + type(exc).__name__ + ")")
    for expected in EXPECTED:
        if expected not in receipts:
            issue("missing-shard", expected, "No complete execution receipt for expected suite")
        elif receipts[expected]["status"] != "passed":
            issue("failed-shard", expected, "Suite is not recorded as passed")
    heads = {value["head_sha"] for value in receipts.values() if value.get("head_sha")}
    if len(heads) != 1 or "local" in heads or "unbound" in heads:
        issue("head-mismatch", "aggregate", "Shard head identities are absent or inconsistent")
    all_issues = sorted(issue_map.values(), key=lambda i: i["id"])
    aggregate = {
        "schema": "skeleton.e2e.aggregate.v1",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "expected_suites": list(EXPECTED),
        "received_suites": receipts,
        "exact_head": next(iter(heads)) if len(heads) == 1 else None,
        "issue_count": len(all_issues),
        "issues": all_issues,
        "passed": not all_issues and len(receipts) == len(EXPECTED),
    }
    (output / "aggregate.json").write_text(json.dumps(aggregate, indent=2, sort_keys=True) + "\n")
    lines = ["# Massive E2E aggregate evidence", "", "Passed: " + str(aggregate["passed"]),
             "Exact head: " + str(aggregate["exact_head"]),
             "Shards received: " + str(len(receipts)) + " / " + str(len(EXPECTED)),
             "Open issues: " + str(len(all_issues)), "",
             "## Shard results", "", "| Shard | Status | Seconds | Artifact |",
             "| --- | --- | ---: | --- |"]
    for suite in EXPECTED:
        data = receipts.get(suite, {})
        lines.append("| " + suite + " | " + str(data.get("status", "MISSING")) +
                     " | " + str(data.get("duration_seconds", "-")) +
                     " | " + str(data.get("artifact", "-")) + " |")
    lines.extend(["", "## Recorded issues", "",
                  "| Issue | Severity | Kind | Suite |",
                  "| --- | --- | --- | --- |"])
    lines.extend("| " + x["id"] + " | " + x["severity"] +
                 " | " + x["kind"] + " | " + x["suite"] + " |" for x in all_issues)
    lines.append("")
    (output / "aggregate.md").write_text("\n".join(lines))
    print("E2E aggregation: " + str(len(receipts)) + " shards, " +
          str(len(all_issues)) + " issues, passed=" + str(aggregate["passed"]))
    return 0 if aggregate["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
