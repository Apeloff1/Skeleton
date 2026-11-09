#!/usr/bin/env python3
"""Derive P2 project metrics from canonical trace and task authorities."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

from skeleton.quality.project_metrics import MetricObservation, ratio_observation

ROOT = Path(__file__).resolve().parents[1]


class ProjectMetricCheckError(RuntimeError):
    pass


def _load(root: Path, rel: str) -> dict[str, Any]:
    try:
        data = json.loads((root / rel).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProjectMetricCheckError(f"cannot load {rel}: {exc}") from exc
    if not isinstance(data, dict):
        raise ProjectMetricCheckError(f"{rel} must contain an object")
    return data


def derive(root: Path = ROOT) -> tuple[MetricObservation, ...]:
    root = root.resolve()
    control = _load(root, "machine/p2_quality_control.json")
    p2map = _load(root, "machine/ai_p2_execution_map.json")
    backlog = _load(root, "machine/ai_p2_task_backlog.json")
    trace = _load(root, "machine/master_traceability.json")

    definitions = control.get("project_metrics", {}).get("definitions")
    if not isinstance(definitions, list) or len(definitions) != 5:
        raise ProjectMetricCheckError("project metric definition coverage drift")
    by_id = {item.get("metric_id"): item for item in definitions if isinstance(item, dict)}
    if len(by_id) != len(definitions):
        raise ProjectMetricCheckError("duplicate/invalid metric ID")

    expected_categories = {"activity", "throughput", "quality", "risk", "outcome"}
    if {item.get("category") for item in definitions} != expected_categories:
        raise ProjectMetricCheckError("metric category coverage drift")

    for item in definitions:
        for source in item.get("sources", []):
            if not isinstance(source, str) or not (root / source).is_file():
                raise ProjectMetricCheckError(
                    f"{item.get('metric_id')} source missing: {source!r}"
                )

    scheduled = p2map.get("first_tranche", {}).get("scheduled_volume_count")
    if not isinstance(scheduled, int) or isinstance(scheduled, bool) or scheduled < 0:
        raise ProjectMetricCheckError("scheduled volume count is invalid")

    tasks = backlog.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        raise ProjectMetricCheckError("P2 task backlog missing")
    verified = sum(
        1
        for task in tasks
        if task.get("implementation_signed") is True
        and task.get("verification_signed") is True
        and task.get("completion_checkbox") is True
    )

    summary = trace.get("summary", {})
    requirement_count = summary.get("requirement_count")
    without_evidence = summary.get("requirements_without_evidence")
    if (
        not isinstance(requirement_count, int)
        or isinstance(requirement_count, bool)
        or requirement_count <= 0
        or not isinstance(without_evidence, int)
        or isinstance(without_evidence, bool)
        or without_evidence < 0
        or without_evidence > requirement_count
    ):
        raise ProjectMetricCheckError("trace summary requirement counts are invalid")
    with_evidence = requirement_count - without_evidence

    observations = (
        MetricObservation(
            "PM-P2-SCHEDULED-VOLUMES",
            "activity",
            scheduled,
            ("machine/ai_p2_execution_map.json",),
        ),
        MetricObservation(
            "PM-P2-VERIFIED-TASKS",
            "throughput",
            verified,
            ("machine/ai_p2_task_backlog.json",),
        ),
        ratio_observation(
            "PM-TRACE-EVIDENCE-COVERAGE",
            "quality",
            with_evidence,
            requirement_count,
            ("machine/master_traceability.json",),
        ),
        MetricObservation(
            "PM-TRACE-EVIDENCE-DEBT",
            "risk",
            without_evidence,
            ("machine/master_traceability.json",),
        ),
        ratio_observation(
            "PM-P2-VERIFIED-COMPLETION",
            "outcome",
            verified,
            len(tasks),
            ("machine/ai_p2_task_backlog.json",),
        ),
    )
    if {item.metric_id for item in observations} != set(by_id):
        raise ProjectMetricCheckError("derived metric IDs drift from registry")
    for item in observations:
        definition = by_id[item.metric_id]
        if item.category != definition.get("category"):
            raise ProjectMetricCheckError(f"{item.metric_id} category drift")
        if set(item.source_refs) != set(definition.get("sources", [])):
            raise ProjectMetricCheckError(f"{item.metric_id} source drift")
        if item.completion_authority is not False:
            raise ProjectMetricCheckError("metric gained completion authority")
    return observations


def validate(root: Path = ROOT) -> dict[str, Any]:
    observations = derive(root)
    return {
        "status": "valid",
        "metric_count": len(observations),
        "observations": [
            {
                "metric_id": item.metric_id,
                "category": item.category,
                "value": item.value,
                "numerator": item.numerator,
                "denominator": item.denominator,
                "source_refs": list(item.source_refs),
                "completion_authority": item.completion_authority,
            }
            for item in observations
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        result = validate(Path(args.repo_root))
    except ProjectMetricCheckError as exc:
        print(f"p2 project metrics: FAIL: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True) if args.json else result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
