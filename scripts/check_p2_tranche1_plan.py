#!/usr/bin/env python3
"""Validate the prepared, non-owning P2-T1 runtime-trust tranche plan."""

from __future__ import annotations

import argparse
import json
from pathlib import Path, PurePosixPath
import sys
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
PLAN_PATH = Path("machine/ai_p2_tranche1_plan.json")


class P2Tranche1Error(RuntimeError):
    pass


def _load(root: Path, relative: str | Path) -> dict[str, Any]:
    path = root / relative
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise P2Tranche1Error(f"missing required file: {relative}") from exc
    except json.JSONDecodeError as exc:
        raise P2Tranche1Error(f"invalid JSON in {relative}: {exc}") from exc
    if not isinstance(data, dict):
        raise P2Tranche1Error(f"{relative} must contain a JSON object")
    return data


def _duplicates(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    dupes: set[str] = set()
    for value in values:
        if value in seen:
            dupes.add(value)
        seen.add(value)
    return sorted(dupes)


def _repo_path(value: object) -> str:
    if not isinstance(value, str) or not value or "\x00" in value or "\\" in value:
        raise P2Tranche1Error(f"invalid repository path: {value!r}")
    pure = PurePosixPath(value)
    if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
        raise P2Tranche1Error(f"unsafe repository path: {value!r}")
    if pure.as_posix() != value:
        raise P2Tranche1Error(f"non-canonical repository path: {value!r}")
    return value


def _acyclic(nodes: set[str], edges: dict[str, list[str]]) -> None:
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str, path: list[str]) -> None:
        if node in visited:
            return
        if node in visiting:
            raise P2Tranche1Error(
                "tranche workstream dependency cycle: "
                + " -> ".join(path + [node])
            )
        visiting.add(node)
        for dep in edges.get(node, []):
            if dep not in nodes:
                raise P2Tranche1Error(
                    f"workstream {node} depends on unknown workstream {dep}"
                )
            visit(dep, path + [node])
        visiting.remove(node)
        visited.add(node)

    for node in sorted(nodes):
        visit(node, [])


def validate(root: Path = ROOT) -> dict[str, Any]:
    root = root.resolve()
    plan = _load(root, PLAN_PATH)
    master = _load(root, "machine/ai_master_plan.json")
    p2 = _load(root, "machine/ai_p2_execution_map.json")
    backlog = _load(root, "machine/ai_p2_task_backlog.json")

    if plan.get("schema_version") != "skeleton.p2.tranche_plan.v1":
        raise P2Tranche1Error("unexpected tranche-plan schema version")
    if plan.get("status") != "prepared_non_owning":
        raise P2Tranche1Error("T1 must remain prepared_non_owning before activation")
    if plan.get("tranche_id") != "P2-T1":
        raise P2Tranche1Error("tranche id must remain P2-T1")

    master_by_ref = {
        item["key"]: item
        for item in master.get("volumes", [])
        if isinstance(item, dict) and isinstance(item.get("key"), str)
    }
    source = set(p2.get("source_scope", {}).get("volume_refs", []))
    scheduled = set(p2.get("first_tranche", {}).get("scheduled_volume_refs", []))
    queued_list = p2.get("first_tranche", {}).get("queued_volume_refs", [])
    queued = set(queued_list)
    if len(source) != 314 or len(scheduled) != 42 or len(queued) != 272:
        raise P2Tranche1Error("canonical P2 source/first-tranche partition drift")
    if source != scheduled | queued or scheduled & queued:
        raise P2Tranche1Error("canonical P2 scheduled/queued partition is invalid")

    selection = plan.get("selection")
    if not isinstance(selection, dict):
        raise P2Tranche1Error("selection must be an object")
    selected = selection.get("selected_volume_refs")
    if not isinstance(selected, list) or not selected:
        raise P2Tranche1Error("selected_volume_refs must be non-empty")
    if any(not isinstance(ref, str) for ref in selected):
        raise P2Tranche1Error("selected_volume_refs must contain strings")
    dupes = _duplicates(selected)
    if dupes:
        raise P2Tranche1Error(f"duplicate selected volumes: {dupes}")
    selected_set = set(selected)
    if selection.get("selected_volume_count") != len(selected):
        raise P2Tranche1Error("selected_volume_count mismatch")
    if selection.get("source_queue_count") != len(queued):
        raise P2Tranche1Error("source_queue_count drift")
    outside = sorted(selected_set - queued)
    if outside:
        raise P2Tranche1Error(
            f"prepared T1 volume is not still queued: {outside}"
        )
    if selected_set & scheduled:
        raise P2Tranche1Error("prepared T1 overlaps already scheduled P2-T0 scope")

    existing_owned = {
        ref
        for task in backlog.get("tasks", [])
        if isinstance(task, dict)
        for ref in task.get("primary_volume_refs", [])
    }
    premature = sorted(selected_set & existing_owned)
    if premature:
        raise P2Tranche1Error(
            f"prepared T1 already has P2 task ownership before activation: {premature}"
        )

    activation = plan.get("activation")
    if not isinstance(activation, dict):
        raise P2Tranche1Error("activation must be an object")
    if activation.get("mode") != "explicit_followup_only":
        raise P2Tranche1Error("T1 activation must require an explicit follow-up")
    if activation.get("ownership_effect_before_activation") != "none":
        raise P2Tranche1Error("prepared T1 must have no ownership effect")
    required_status = activation.get("required_first_tranche_task_status")
    if required_status != "landed_unpromoted":
        raise P2Tranche1Error("T1 activation fence must require landed_unpromoted")

    tasks = [
        item for item in backlog.get("tasks", [])
        if isinstance(item, dict)
    ]
    task_ids = [item.get("task_id") for item in tasks]
    if any(not isinstance(task_id, str) or not task_id for task_id in task_ids):
        raise P2Tranche1Error("P2 backlog contains invalid task ids")
    required_ids = activation.get("required_first_tranche_task_ids")
    if not isinstance(required_ids, list) or set(required_ids) != set(task_ids):
        raise P2Tranche1Error(
            "T1 activation task set must exactly match canonical P2-T0 backlog"
        )
    if "P2-NATIVE-01" not in required_ids:
        raise P2Tranche1Error("T1 activation must remain fenced on P2-NATIVE-01")
    task_by_id = {item["task_id"]: item for item in tasks}
    status_by = {task_id: item.get("status") for task_id, item in task_by_id.items()}
    activation_blockers = sorted(
        task_id
        for task_id in required_ids
        if status_by.get(task_id) != required_status
    )

    hexdigits = set("0123456789abcdef")
    for task_id in required_ids:
        task = task_by_id[task_id]
        if task.get("status") != required_status:
            continue
        evidence_refs = task.get("evidence_refs")
        if (
            not isinstance(evidence_refs, list)
            or not evidence_refs
            or not all(isinstance(ref, str) and ref for ref in evidence_refs)
        ):
            raise P2Tranche1Error(
                f"{task_id} landed status requires non-empty evidence_refs"
            )
        if not any(ref.startswith("github:pr#") for ref in evidence_refs):
            raise P2Tranche1Error(
                f"{task_id} landed status requires a GitHub PR evidence ref"
            )
        merge_refs = [
            ref.removeprefix("git:merge:")
            for ref in evidence_refs
            if ref.startswith("git:merge:")
        ]
        if not any(
            len(sha) == 40 and set(sha) <= hexdigits
            for sha in merge_refs
        ):
            raise P2Tranche1Error(
                f"{task_id} landed status requires a full lowercase merge SHA"
            )
        if not any(
            ref.startswith("workflow:") and ref.endswith(":success")
            for ref in evidence_refs
        ):
            raise P2Tranche1Error(
                f"{task_id} landed status requires successful workflow evidence"
            )
        if task.get("completion_checkbox") is not False:
            raise P2Tranche1Error(
                f"{task_id} landed_unpromoted cannot assert completion"
            )
        if (
            task.get("implementation_signed") is not False
            or task.get("verification_signed") is not False
        ):
            raise P2Tranche1Error(
                f"{task_id} landed_unpromoted cannot assert sign-off"
            )

    workstreams = plan.get("workstreams")
    if not isinstance(workstreams, list) or not workstreams:
        raise P2Tranche1Error("workstreams must be non-empty")
    stream_ids = [item.get("id") for item in workstreams if isinstance(item, dict)]
    if len(stream_ids) != len(workstreams) or any(
        not isinstance(item, str) or not item for item in stream_ids
    ):
        raise P2Tranche1Error("every workstream requires an id")
    if _duplicates(stream_ids):
        raise P2Tranche1Error("duplicate workstream ids")
    stream_nodes = set(stream_ids)
    stream_edges = {
        item["id"]: list(item.get("depends_on", []))
        for item in workstreams
    }
    _acyclic(stream_nodes, stream_edges)
    stream_refs = [
        ref
        for item in workstreams
        for ref in item.get("volume_refs", [])
    ]
    if _duplicates(stream_refs):
        raise P2Tranche1Error(
            f"selected volume appears in multiple T1 workstreams: {_duplicates(stream_refs)}"
        )
    if set(stream_refs) != selected_set:
        raise P2Tranche1Error(
            "T1 workstream volume union must equal selected_volume_refs"
        )
    for item in workstreams:
        objective = item.get("objective")
        if not isinstance(objective, str) or not objective.strip():
            raise P2Tranche1Error(f"{item['id']} requires an objective")

    evidence = plan.get("volume_selection_evidence")
    if not isinstance(evidence, list) or len(evidence) != len(selected):
        raise P2Tranche1Error(
            "volume_selection_evidence must cover every selected volume"
        )
    by_ref: dict[str, dict[str, Any]] = {}
    obligation_fields = (
        "title",
        "depth_pass",
        "accountability_id",
        "implementation_status",
        "completion_checkbox",
        "signing_required",
        "contracts",
        "risks",
        "gaps",
        "implementation_paths",
        "tests",
        "evaluations",
    )
    for item in evidence:
        if not isinstance(item, dict):
            raise P2Tranche1Error("selection evidence item must be an object")
        ref = item.get("volume_ref")
        if not isinstance(ref, str) or ref in by_ref:
            raise P2Tranche1Error(f"invalid/duplicate selection evidence ref: {ref!r}")
        by_ref[ref] = item
    if set(by_ref) != selected_set:
        raise P2Tranche1Error("selection evidence refs must equal selected refs")

    tested_core_count = 0
    harness_gap_count = 0
    for ref in selected:
        canonical = master_by_ref.get(ref)
        if not isinstance(canonical, dict):
            raise P2Tranche1Error(f"selected volume missing from masterplan: {ref}")
        item = by_ref[ref]
        obligation = item.get("masterplan_obligation")
        if not isinstance(obligation, dict) or obligation.get("volume_ref") != ref:
            raise P2Tranche1Error(f"{ref} lacks exact masterplan obligation")
        for field in obligation_fields:
            if obligation.get(field) != canonical.get(field):
                raise P2Tranche1Error(
                    f"{ref} narrows/drifts masterplan field {field}"
                )
        if canonical.get("completion_checkbox") is not False:
            raise P2Tranche1Error(f"{ref} is already completion-checked")
        if canonical.get("signing_required") is not True:
            raise P2Tranche1Error(f"{ref} lost signing requirement")

        implementation_anchors = item.get("existing_implementation_anchors")
        test_anchors = item.get("existing_test_anchors")
        if not isinstance(implementation_anchors, list) or not implementation_anchors:
            raise P2Tranche1Error(f"{ref} requires existing implementation anchors")
        if not isinstance(test_anchors, list):
            raise P2Tranche1Error(f"{ref} existing_test_anchors must be a list")
        canonical_impl = set(canonical.get("implementation_paths", []))
        canonical_tests = set(canonical.get("tests", []))
        for raw in implementation_anchors:
            path = _repo_path(raw)
            if raw not in canonical_impl:
                raise P2Tranche1Error(
                    f"{ref} selection implementation anchor is not canonical: {raw}"
                )
            if raw.startswith("planned:") or not (root / path).exists():
                raise P2Tranche1Error(
                    f"{ref} implementation anchor does not exist: {raw}"
                )
        for raw in test_anchors:
            path = _repo_path(raw)
            if raw not in canonical_tests:
                raise P2Tranche1Error(
                    f"{ref} selection test anchor is not canonical: {raw}"
                )
            if raw.startswith("planned:") or not (root / path).exists():
                raise P2Tranche1Error(
                    f"{ref} test anchor does not exist: {raw}"
                )

        selection_class = item.get("selection_class")
        if selection_class == "existing_tested_core":
            tested_core_count += 1
            if len(test_anchors) < 2:
                raise P2Tranche1Error(
                    f"{ref} existing_tested_core requires at least two live tests"
                )
        else:
            harness_gap_count += 1
            if test_anchors:
                raise P2Tranche1Error(
                    f"{ref} non-core harness-gap class must not pretend live test anchors"
                )

    exclusions = selection.get("exclusions")
    if not isinstance(exclusions, list) or not exclusions:
        raise P2Tranche1Error("selection exclusions must remain explicit")
    excluded_refs: set[str] = set()
    for item in exclusions:
        if not isinstance(item, dict):
            raise P2Tranche1Error("selection exclusion must be an object")
        refs = item.get("volume_refs")
        reason = item.get("reason")
        if not isinstance(refs, list) or not refs:
            raise P2Tranche1Error("selection exclusion requires volume_refs")
        if not isinstance(reason, str) or not reason.strip():
            raise P2Tranche1Error("selection exclusion requires rationale")
        excluded_refs.update(refs)
    if excluded_refs & selected_set:
        raise P2Tranche1Error("selected and explicitly excluded volumes overlap")
    if not excluded_refs <= queued:
        raise P2Tranche1Error("exclusions must refer to currently queued volumes")

    rules = plan.get("non_authority_rules")
    if not isinstance(rules, list) or len(rules) < 4:
        raise P2Tranche1Error("T1 non-authority rules are incomplete")

    return {
        "status": "valid",
        "selected_volume_count": len(selected),
        "workstream_count": len(workstreams),
        "tested_core_count": tested_core_count,
        "harness_gap_count": harness_gap_count,
        "activation_ready": not activation_blockers,
        "activation_blockers": activation_blockers,
        "remaining_queue_after_activation": len(queued) - len(selected),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        result = validate(Path(args.repo_root))
    except P2Tranche1Error as exc:
        print(f"P2 tranche 1 plan: FAIL: {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(result, sort_keys=True))
    else:
        print(
            "P2 tranche 1 plan: OK "
            f"({result['selected_volume_count']} selected, "
            f"{result['workstream_count']} workstreams, "
            f"activation_ready={result['activation_ready']})"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
