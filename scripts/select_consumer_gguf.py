"""Select advisory specialist profiles from exact matched GGUF diagnostics.

A hash pin proves byte identity, not independent benchmark authenticity.
No model is activated, downloaded, promoted, or added to a provider catalog.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import statistics
from typing import Sequence

from scripts import compare_consumer_gguf as diagnostic

_MAX_REPORT = 2 * 1024**2
_COMPLETED = frozenset({"exact", "different"})
_STATUSES = _COMPLETED | {"execution_failed", "identity_rejected", "held_identity", "not_started_deadline"}
_CATEGORIES = tuple(sorted({task.category for task in diagnostic._TASKS}))


def _object(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise ValueError("duplicate diagnostic JSON key")
        out[key] = value
    return out


def _reject_constant(_):
    raise ValueError("non-finite diagnostic JSON")


def _digest(value):
    return diagnostic._digest(value)


def read_report(path: Path, expected_sha256: str) -> dict:
    if not isinstance(expected_sha256, str) or not diagnostic._HEX.fullmatch(expected_sha256):
        raise ValueError("explicit diagnostic file SHA-256 required")
    if not path.is_file() or path.is_symlink():
        raise ValueError("diagnostic must be a regular local file")
    with path.open("rb") as handle:
        raw = handle.read(_MAX_REPORT + 1)
    if not 1 <= len(raw) <= _MAX_REPORT or hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise ValueError("diagnostic bytes do not match their pin")
    parsed = json.loads(raw, object_pairs_hook=_object, parse_constant=_reject_constant)
    if not isinstance(parsed, dict):
        raise ValueError("diagnostic report must be an object")
    return parsed


def _profiles(report):
    profiles = report.get("profiles")
    if not isinstance(profiles, list) or not 2 <= len(profiles) <= 4:
        raise ValueError("diagnostic requires 2–4 profiles")
    fields = {"label", "manifest_sha256", "model_sha256", "executable_sha256",
              "model_id_sha256", "manifest_file_sha256"}
    result = {}
    for row in profiles:
        if not isinstance(row, dict) or set(row) != fields:
            raise ValueError("malformed profile identity")
        label = row["label"]
        if not isinstance(label, str) or not diagnostic._LABEL.fullmatch(label) or label in result:
            raise ValueError("duplicate or invalid profile")
        if any(not isinstance(row[key], str) or not diagnostic._HEX.fullmatch(row[key])
               for key in fields - {"label"}):
            raise ValueError("profile digest required")
        result[label] = row
    if len({p["manifest_sha256"] for p in result.values()}) != len(result):
        raise ValueError("duplicate profile manifests")
    return result


def _validate(report):
    if not isinstance(report, dict):
        raise ValueError("diagnostic report required")
    payload = {k: v for k, v in report.items() if k != "report_sha256"}
    if report.get("report_sha256") != _digest(payload):
        raise ValueError("diagnostic receipt digest mismatch")
    if (report.get("schema") != "skeleton.gguf.matched-diagnostic.v1"
            or report.get("status") != "advisory_only"
            or report.get("scorer") != "exact_utf8_sha256_v1"
            or report.get("corpus_sha256") != _digest([vars(task) for task in diagnostic._TASKS])
            or report.get("scorer_source_sha256") != hashlib.sha256(Path(diagnostic.__file__).read_bytes()).hexdigest()):
        raise ValueError("diagnostic corpus or scorer has changed")
    profiles = _profiles(report)
    repeats = report.get("repeats")
    if type(repeats) is not int or not 2 <= repeats <= 3:
        raise ValueError("specialist selection requires 2–3 matched repeats")
    tasks = {task.name: task.category for task in diagnostic._TASKS}
    expected = {(label, task, repeat) for label in profiles for task in tasks for repeat in range(repeats)}
    rows = report.get("rows")
    if not isinstance(rows, list) or len(rows) != len(expected) or report.get("planned_attempts") != len(expected):
        raise ValueError("incomplete diagnostic matrix")
    indexed = {}
    receipt_ids = set()
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("invalid task result")
        fields = {"profile", "task", "repeat", "category", "elapsed_seconds", "receipt_sha256", "status"}
        if set(row) != fields or type(row["repeat"]) is not int:
            raise ValueError("invalid task result shape")
        label, task, repeat = row["profile"], row["task"], row["repeat"]
        if not isinstance(label, str) or not isinstance(task, str):
            raise ValueError("invalid task identity")
        key = (label, task, repeat)
        if key not in expected or key in indexed or row["category"] != tasks[task]:
            raise ValueError("duplicate or foreign matched task")
        status = row["status"]
        if not isinstance(status, str) or status not in _STATUSES:
            raise ValueError("unknown diagnostic status")
        elapsed = row["elapsed_seconds"]
        if elapsed is not None and (type(elapsed) not in {int, float} or not math.isfinite(elapsed) or elapsed < 0):
            raise ValueError("invalid diagnostic latency")
        receipt = row["receipt_sha256"]
        if status in _COMPLETED:
            if elapsed is None or not isinstance(receipt, str) or not diagnostic._HEX.fullmatch(receipt):
                raise ValueError("completed task lacks receipt or elapsed time")
            # Exact native receipt digests can repeat on deterministic replay;
            # do not count repetition as independent benchmark evidence.
            receipt_ids.add(receipt)
        elif receipt is not None:
            raise ValueError("incomplete native task cannot carry success receipt")
        indexed[key] = row
    holds = report.get("identity_holds")
    if not isinstance(holds, list) or any(not isinstance(label, str) or label not in profiles for label in holds):
        raise ValueError("invalid identity holds")
    observed_holds = {key[0] for key, row in indexed.items()
                      if row["status"] in {"identity_rejected", "held_identity"}}
    if set(holds) != observed_holds:
        raise ValueError("inconsistent identity holds")
    return profiles, repeats, indexed, observed_holds


def select(report: dict, *, minimum_exact_percent: int = 75) -> dict:
    if type(minimum_exact_percent) is not int or not 1 <= minimum_exact_percent <= 100:
        raise ValueError("quality floor must be an integer percentage")
    profiles, repeats, rows, holds = _validate(report)
    candidates = {}
    for category in _CATEGORIES:
        tasks = [task.name for task in diagnostic._TASKS if task.category == category]
        eligible = []
        excluded = []
        for label, identity in profiles.items():
            cells = [rows[label, task, repeat] for task in tasks for repeat in range(repeats)]
            all_cells = [row for key, row in rows.items() if key[0] == label]
            if label in holds or any(row["status"] not in _COMPLETED for row in all_cells):
                excluded.append({"profile": label, "reason": "incomplete_or_held_diagnostic"})
                continue
            per_repeat = [sum(rows[label, task, repeat]["status"] == "exact" for task in tasks)
                          for repeat in range(repeats)]
            worst = min(per_repeat)
            if worst * 100 < minimum_exact_percent * len(tasks):
                excluded.append({"profile": label, "reason": "worst_repeat_below_floor"})
                continue
            times = [r["elapsed_seconds"] for r in cells if r["status"] == "exact"]
            eligible.append({
                "profile": label, "model_sha256": identity["model_sha256"],
                "manifest_file_sha256": identity["manifest_file_sha256"],
                "worst_repeat_exact": worst, "tasks_per_repeat": len(tasks),
                "exact": sum(per_repeat), "attempts": len(cells),
                "median_exact_wall_seconds": statistics.median(times),
            })
        eligible.sort(key=lambda x: (-x["worst_repeat_exact"], -x["exact"],
                                    x["median_exact_wall_seconds"], x["profile"]))
        primary = eligible[0] if eligible else None
        # Different configurations of identical base weights are not independent
        # semantic verification authorities, even if their speed differs.
        alternative = next((x for x in eligible[1:] if x["model_sha256"] != primary["model_sha256"]), None) if primary else None
        candidates[category] = {"preferred": primary, "distinct_weight_alternative": alternative,
                                "eligible": eligible, "excluded": excluded}
    result = {
        "schema": "skeleton.gguf.specialist-recommendation.v1",
        "status": "advisory_only", "diagnostic_sha256": report["report_sha256"],
        "minimum_worst_repeat_exact_percent": minimum_exact_percent,
        "categories": candidates, "activation_authorized": False,
        "limitations": ["public correlated diagnostic", "no current hardware fit or latency guarantee",
                        "distinct weights do not prove independent verifier calibration",
                        "operator must approve any separate catalog change"],
    }
    result["recommendation_sha256"] = _digest(result)
    return result


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--report-sha256", required=True)
    parser.add_argument("--minimum-exact-percent", type=int, default=75)
    args = parser.parse_args(argv)
    try:
        selected = select(read_report(args.report, args.report_sha256),
                          minimum_exact_percent=args.minimum_exact_percent)
    except (ValueError, TypeError, OSError, RecursionError):
        parser.exit(2, "specialist recommendation rejected: incomplete or invalid evidence\n")
    print(json.dumps(selected, indent=2, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
