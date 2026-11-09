#!/usr/bin/env python3
"""Fail-closed validation for the P2 repository-engineering control plane."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import sys
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
REPO_REFS = (
    "VOL-021",
    "VOL-022",
    "VOL-092",
    "VOL-093",
    "VOL-094",
    "VOL-095",
    "VOL-108",
    "VOL-109",
    "VOL-110",
    "VOL-115",
    "VOL-118",
    "VOL-119",
)
AUTHORITY_BY_REF = {
    "VOL-021": "machine/repository_graph_contract.json",
    "VOL-022": "machine/repository_engineering_policy.json",
    "VOL-092": "machine/maintenance_ownership.json",
    "VOL-093": "machine/backlog_registry.json",
    "VOL-094": "machine/priority_policy.json",
    "VOL-095": "machine/work_package_control.json",
    "VOL-108": "machine/anti_pattern_registry.json",
    "VOL-109": "machine/build_order_control.json",
    "VOL-110": "machine/definition_of_done.json",
    "VOL-115": "machine/technical_debt_ledger.json",
    "VOL-118": "machine/roadmap_control.json",
    "VOL-119": "machine/completion_model.json",
}


class RepositoryControlError(RuntimeError):
    pass


def _load(root: Path, relative: str) -> dict[str, Any]:
    path = root / relative
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RepositoryControlError(f"missing required file: {relative}") from exc
    except json.JSONDecodeError as exc:
        raise RepositoryControlError(f"invalid JSON in {relative}: {exc}") from exc
    if not isinstance(payload, dict):
        raise RepositoryControlError(f"{relative} must contain a JSON object")
    return payload


def _git_blob_sha(path: Path) -> str:
    data = path.read_bytes()
    return hashlib.sha1(f"blob {len(data)}\0".encode("ascii") + data).hexdigest()


def _repo_path(value: object) -> str:
    if not isinstance(value, str) or not value or "\x00" in value or "\\" in value:
        raise RepositoryControlError(f"invalid repository path: {value!r}")
    pure = PurePosixPath(value)
    if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
        raise RepositoryControlError(f"invalid repository path: {value!r}")
    if pure.as_posix() != value:
        raise RepositoryControlError(f"non-canonical repository path: {value!r}")
    return value


def _assert_binding(
    payload: dict[str, Any],
    master_by_ref: dict[str, dict[str, Any]],
    ref: str,
    relative: str,
) -> None:
    binding = payload.get("masterplan_binding")
    if not isinstance(binding, dict):
        raise RepositoryControlError(f"{relative} lacks masterplan_binding")
    volume = master_by_ref.get(ref)
    if not isinstance(volume, dict):
        raise RepositoryControlError(f"masterplan missing {ref}")
    if binding.get("volume_ref") != ref:
        raise RepositoryControlError(f"{relative} must bind {ref}")
    if binding.get("title") != volume.get("title"):
        raise RepositoryControlError(f"{relative} title drift for {ref}")
    if binding.get("required_gap_texts") != volume.get("gaps", []):
        raise RepositoryControlError(
            f"{relative} narrows/drifts masterplan gaps for {ref}"
        )


def _assert_acyclic(
    nodes: Iterable[str],
    dependencies: dict[str, list[str]],
    label: str,
) -> None:
    node_set = set(nodes)
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str, stack: list[str]) -> None:
        if node in visited:
            return
        if node in visiting:
            raise RepositoryControlError(
                f"{label} dependency cycle: {' -> '.join(stack + [node])}"
            )
        visiting.add(node)
        for dep in dependencies.get(node, []):
            if dep not in node_set:
                raise RepositoryControlError(
                    f"{label} {node} depends on unknown node {dep}"
                )
            visit(dep, stack + [node])
        visiting.remove(node)
        visited.add(node)

    for node in sorted(node_set):
        visit(node, [])


def _validate_graph_contract(root: Path, payload: dict[str, Any]) -> None:
    sources = payload.get("sources")
    if not isinstance(sources, list) or len(sources) < 4:
        raise RepositoryControlError("repository graph sources are incomplete")
    seen: set[str] = set()
    for source in sources:
        if not isinstance(source, dict):
            raise RepositoryControlError("repository graph source must be an object")
        relative = _repo_path(source.get("path"))
        if relative in seen:
            raise RepositoryControlError(f"duplicate repository graph source {relative}")
        seen.add(relative)
        target = root / relative
        if not target.is_file():
            raise RepositoryControlError(f"repository graph source missing: {relative}")
        if source.get("git_blob_sha") != _git_blob_sha(target):
            raise RepositoryControlError(f"repository graph source stale: {relative}")
        if not isinstance(source.get("role"), str) or not source["role"].strip():
            raise RepositoryControlError(f"repository graph source lacks role: {relative}")
    required_nodes = {
        "file",
        "symbol",
        "dependency",
        "reference",
        "workflow",
        "test",
        "owner",
        "trace_authority",
    }
    if not required_nodes <= set(payload.get("node_kinds", [])):
        raise RepositoryControlError("repository graph node kinds are incomplete")
    freshness = payload.get("freshness_policy", {})
    if not freshness.get("stale_when") or "heuristic" not in str(
        freshness.get("heuristic_rule", "")
    ).lower():
        raise RepositoryControlError("repository graph freshness/confidence policy incomplete")


def _validate_engineering_policy(root: Path, payload: dict[str, Any]) -> None:
    phases = payload.get("phases")
    expected_ids = [
        "inspect",
        "plan",
        "lease",
        "edit",
        "build",
        "test",
        "review",
        "verify",
    ]
    if not isinstance(phases, list) or [p.get("id") for p in phases] != expected_ids:
        raise RepositoryControlError("repository engineering phase order drift")
    if [p.get("order") for p in phases] != list(range(1, 9)):
        raise RepositoryControlError("repository engineering phase numbers drift")
    for phase in phases:
        authorities = phase.get("authority")
        if not isinstance(authorities, list) or not authorities:
            raise RepositoryControlError(f"{phase.get('id')} lacks authority")
        for relative in authorities:
            path = _repo_path(relative)
            if not (root / path).exists():
                raise RepositoryControlError(
                    f"{phase.get('id')} authority missing: {path}"
                )
    transaction = payload.get("transaction_policy", {})
    required_true = (
        "isolated_workspace_required",
        "edit_lease_required",
        "journal_required",
        "rollback_path_required",
        "patch_provenance_required",
        "focused_regression_required",
    )
    for field in required_true:
        if transaction.get(field) is not True:
            raise RepositoryControlError(f"transaction policy must require {field}")
    independence = payload.get("independence_policy", {})
    if independence.get("implementation_and_verification_signers_must_differ") is not True:
        raise RepositoryControlError("independent verification must remain required")
    if independence.get("self_review_never_counts_as_independent_verification") is not True:
        raise RepositoryControlError("self-review cannot count as verification")


def _validate_maintenance(
    architecture: dict[str, Any],
    payload: dict[str, Any],
) -> None:
    expected = {
        item["id"]: {
            "path": item["path"],
            "owner": item["owner"],
            "class": item["class"],
            "change_lane": item["change_lane"],
        }
        for item in architecture.get("canonical_roots", [])
    }
    roots = payload.get("roots")
    if not isinstance(roots, list):
        raise RepositoryControlError("maintenance roots must be a list")
    actual = {item.get("root_id"): item for item in roots if isinstance(item, dict)}
    if set(actual) != set(expected) or len(actual) != len(roots):
        raise RepositoryControlError("maintenance ownership root coverage drift")
    for root_id, fields in expected.items():
        item = actual[root_id]
        for field, value in fields.items():
            if item.get(field) != value:
                raise RepositoryControlError(
                    f"maintenance root {root_id} {field} drift"
                )
        if item.get("automated_delete_allowed") is not False:
            raise RepositoryControlError(
                f"generic automated deletion must remain disabled for {root_id}"
            )
    preconditions = payload.get("deletion_preconditions")
    if not isinstance(preconditions, list):
        raise RepositoryControlError("deletion preconditions must be a list")
    joined = " ".join(preconditions).lower()
    for required in ("owner", "reachability", "retention", "rollback", "receipt"):
        if required not in joined:
            raise RepositoryControlError(
                f"deletion preconditions lack {required} evidence"
            )
    protected = payload.get("protected_artifact_classes")
    if not isinstance(protected, list) or len(protected) < 4:
        raise RepositoryControlError("protected maintenance classes incomplete")


def _expected_backlog(
    p2: dict[str, Any],
    edge_queue: dict[str, Any],
    master_by_ref: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    expected: dict[str, dict[str, Any]] = {}
    for task in p2.get("tasks", []):
        expected[f"BL-P2-{task['task_id']}"] = {
            "source_type": "p2_task",
            "source_ref": task["task_id"],
            "status": task["status"],
            "dependency_refs": [
                f"BL-P2-{dep}" for dep in task.get("depends_on", [])
            ],
        }
    for item in edge_queue.get("items", []):
        expected[f"BL-EDGE-{item['id']}"] = {
            "source_type": "edge_case",
            "source_ref": item["id"],
            "status": item["status"],
            "dependency_refs": [],
        }
    for ref in REPO_REFS:
        volume = master_by_ref[ref]
        for index, _ in enumerate(volume.get("gaps", []), start=1):
            expected[f"BL-GAP-{ref}-G{index:02d}"] = {
                "source_type": "masterplan_gap",
                "source_ref": f"{ref}#gap-{index}",
                "status": "open",
                "dependency_refs": [],
            }
    return expected


def _validate_backlog(
    payload: dict[str, Any],
    p2: dict[str, Any],
    edge_queue: dict[str, Any],
    master_by_ref: dict[str, dict[str, Any]],
) -> set[str]:
    expected = _expected_backlog(p2, edge_queue, master_by_ref)
    items = payload.get("items")
    if not isinstance(items, list):
        raise RepositoryControlError("backlog items must be a list")
    actual: dict[str, dict[str, Any]] = {}
    dedupe: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            raise RepositoryControlError("backlog item must be an object")
        item_id = item.get("id")
        if not isinstance(item_id, str) or item_id in actual:
            raise RepositoryControlError(f"duplicate/invalid backlog id: {item_id!r}")
        actual[item_id] = item
        key = item.get("dedupe_key")
        if not isinstance(key, str) or not key or key in dedupe:
            raise RepositoryControlError(
                f"duplicate/invalid backlog dedupe key: {key!r}"
            )
        dedupe.add(key)
        if not isinstance(item.get("closure_rule"), str) or not item["closure_rule"].strip():
            raise RepositoryControlError(f"{item_id} lacks closure rule")
        provenance = item.get("provenance")
        if not isinstance(provenance, list) or not provenance:
            raise RepositoryControlError(f"{item_id} lacks provenance")
    if set(actual) != set(expected):
        missing = sorted(set(expected) - set(actual))
        extra = sorted(set(actual) - set(expected))
        raise RepositoryControlError(
            f"backlog coverage drift; missing={missing}, extra={extra}"
        )
    for item_id, fields in expected.items():
        item = actual[item_id]
        for field, value in fields.items():
            if item.get(field) != value:
                raise RepositoryControlError(
                    f"{item_id} {field} drift: {item.get(field)!r} != {value!r}"
                )
        for dep in item.get("dependency_refs", []):
            if dep not in actual:
                raise RepositoryControlError(f"{item_id} dependency missing: {dep}")
    return set(actual)


def _validate_priority(payload: dict[str, Any]) -> None:
    partitions = payload.get("partitions")
    if not isinstance(partitions, list) or [p.get("id") for p in partitions] != [
        "hard_blocker",
        "high_obligation",
        "soft_ranked",
    ]:
        raise RepositoryControlError("priority partitions drift")
    ranks = [p.get("rank") for p in partitions]
    if ranks != [0, 1, 2]:
        raise RepositoryControlError(
            "hard blocker must remain structurally ahead of soft ranking"
        )
    factors = payload.get("soft_factors")
    if not isinstance(factors, list) or not factors:
        raise RepositoryControlError("priority soft factors missing")
    caps = 0
    ids: set[str] = set()
    for factor in factors:
        factor_id = factor.get("id")
        if factor_id in ids:
            raise RepositoryControlError(f"duplicate priority factor {factor_id}")
        ids.add(factor_id)
        minimum = factor.get("min")
        maximum = factor.get("max")
        cap = factor.get("weight_cap")
        if not all(isinstance(x, int) and not isinstance(x, bool) for x in (minimum, maximum, cap)):
            raise RepositoryControlError(f"{factor_id} priority bounds must be integers")
        if minimum < 0 or maximum < minimum or cap != maximum:
            raise RepositoryControlError(f"{factor_id} priority bounds invalid")
        if factor.get("provenance_required") is not True:
            raise RepositoryControlError(f"{factor_id} priority factor needs provenance")
        caps += cap
    if caps > 100:
        raise RepositoryControlError("soft priority weights exceed bounded total")
    anti = payload.get("anti_starvation", {})
    if anti.get("enabled") is not True or anti.get("max_age_factor") != 20:
        raise RepositoryControlError("priority anti-starvation policy drift")
    if "hard_blocker" not in anti.get("protected_partitions", []):
        raise RepositoryControlError("hard blocker partition lost anti-starvation protection")


def _expected_package_requirements(
    package_id: str,
    profile: dict[str, Any],
    matrix_package: dict[str, Any],
) -> list[dict[str, str]]:
    expected: list[dict[str, str]] = []
    expected.extend(
        {
            "id": f"{package_id}:DIM:{value}",
            "source": "engineering.required_dimensions",
            "text": value,
        }
        for value in profile.get("required_dimensions", [])
    )
    expected.extend(
        {
            "id": f"{package_id}:HARD:{index:02d}",
            "source": "engineering.hard_invariants",
            "text": value,
        }
        for index, value in enumerate(profile.get("hard_invariants", []), start=1)
    )
    expected.extend(
        {
            "id": f"{package_id}:REC:{index:02d}",
            "source": "engineering.recovery_requirements",
            "text": value,
        }
        for index, value in enumerate(profile.get("recovery_requirements", []), start=1)
    )
    expected.extend(
        {
            "id": f"{package_id}:ACC:{index:02d}",
            "source": "edge_matrix.acceptance",
            "text": value,
        }
        for index, value in enumerate(matrix_package.get("acceptance", []), start=1)
    )
    return expected


def _validate_work_packages(
    payload: dict[str, Any],
    engineering: dict[str, Any],
    matrix: dict[str, Any],
    queue: dict[str, Any],
    sequence: dict[str, Any],
    accountability: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    profiles = {
        item["id"]: item for item in engineering.get("work_package_profiles", [])
    }
    matrix_by = {item["id"]: item for item in matrix.get("packages", [])}
    wave_by_package: dict[str, str] = {}
    for wave in sequence.get("waves", []):
        for package in wave.get("work_packages", []):
            if package in wave_by_package:
                raise RepositoryControlError(
                    f"work package appears in multiple waves: {package}"
                )
            wave_by_package[package] = wave["id"]
    if set(profiles) != set(matrix_by) or set(profiles) != set(wave_by_package):
        raise RepositoryControlError(
            "work package source authorities disagree on package identity"
        )
    acc_by = {
        item.get("id"): item
        for item in accountability.get("records", [])
        if isinstance(item, dict)
    }
    packages = payload.get("packages")
    if not isinstance(packages, list):
        raise RepositoryControlError("work package control packages must be a list")
    actual = {item.get("id"): item for item in packages if isinstance(item, dict)}
    if set(actual) != set(profiles) or len(actual) != len(packages):
        raise RepositoryControlError("work package control coverage drift")
    seen_tasks: set[str] = set()
    for package_id in sorted(profiles):
        profile = profiles[package_id]
        matrix_package = matrix_by[package_id]
        item = actual[package_id]
        if item.get("wave_ref") != wave_by_package[package_id]:
            raise RepositoryControlError(f"{package_id} wave binding drift")
        if item.get("engineering_class") != profile.get("engineering_class"):
            raise RepositoryControlError(f"{package_id} engineering class drift")
        expected_tasks = sorted(
            task["task_id"]
            for task in queue.get("tasks", [])
            if package_id in task.get("work_package_refs", [])
        )
        if item.get("task_refs") != expected_tasks:
            raise RepositoryControlError(f"{package_id} task binding drift")
        seen_tasks.update(expected_tasks)
        expected_acc = sorted(
            task["accountability_id"]
            for task in queue.get("tasks", [])
            if package_id in task.get("work_package_refs", [])
        )
        if item.get("accountability_refs") != expected_acc:
            raise RepositoryControlError(f"{package_id} accountability binding drift")
        expected_edges = sorted(
            matrix_package.get("historical_ids", [])
            + matrix_package.get("edge_case_ids", [])
            + matrix_package.get("obscure_ids", [])
        )
        if item.get("edge_case_refs") != expected_edges:
            raise RepositoryControlError(f"{package_id} edge-case binding drift")
        if item.get("exact_requirements") != _expected_package_requirements(
            package_id, profile, matrix_package
        ):
            raise RepositoryControlError(f"{package_id} exact requirement drift")
        if item.get("test_targets") != matrix_package.get("test_targets", []):
            raise RepositoryControlError(f"{package_id} test target drift")
        if item.get("change_impact_triggers") != profile.get(
            "change_impact_triggers", []
        ):
            raise RepositoryControlError(f"{package_id} impact trigger drift")
        if item.get("rollback_recovery") != profile.get(
            "recovery_requirements", []
        ):
            raise RepositoryControlError(f"{package_id} recovery binding drift")

        tasks = [
            task
            for task in queue.get("tasks", [])
            if package_id in task.get("work_package_refs", [])
        ]
        signed = sum(
            acc_by.get(task["accountability_id"], {})
            .get("implementation_signoff", {})
            .get("signed")
            is True
            for task in tasks
        )
        verified = sum(
            acc_by.get(task["accountability_id"], {})
            .get("verification_signoff", {})
            .get("signed")
            is True
            for task in tasks
        )
        queue_done = sum(task.get("status") == "done" for task in tasks)
        package_evidence = len(matrix_package.get("evidence", []))
        expected_rollup = {
            "task_count": len(tasks),
            "queue_done_count": queue_done,
            "implementation_signed_count": signed,
            "verification_signed_count": verified,
            "package_evidence_count": package_evidence,
            "state": (
                "signed_tasks_verified"
                if tasks and signed == len(tasks) and verified == len(tasks)
                else "evidence_pending"
            ),
        }
        if item.get("evidence_rollup") != expected_rollup:
            raise RepositoryControlError(f"{package_id} evidence rollup drift")
    all_task_ids = {task["task_id"] for task in queue.get("tasks", [])}
    if seen_tasks != all_task_ids:
        raise RepositoryControlError(
            f"AIQ package coverage drift; missing={sorted(all_task_ids - seen_tasks)}"
        )
    return actual


def _validate_antipatterns(
    root: Path,
    payload: dict[str, Any],
    catalog: dict[str, Any],
) -> None:
    expected = {
        item["id"]: item
        for item in catalog.get("entries", [])
        if item.get("type") == "historical"
        and item.get("criticality") in {"high", "critical"}
    }
    entries = payload.get("entries")
    if not isinstance(entries, list):
        raise RepositoryControlError("anti-pattern entries must be a list")
    actual = {
        item.get("source_case_id"): item
        for item in entries
        if isinstance(item, dict)
    }
    if set(actual) != set(expected) or len(actual) != len(entries):
        raise RepositoryControlError("historical anti-pattern coverage drift")
    for source_id, source in expected.items():
        item = actual[source_id]
        if item.get("id") != f"AP-{source_id}":
            raise RepositoryControlError(f"{source_id} anti-pattern id drift")
        for field in ("title", "domain", "criticality"):
            if item.get(field) != source.get(field):
                raise RepositoryControlError(
                    f"{source_id} anti-pattern {field} drift"
                )
        if item.get("failure_history") != source.get("lesson"):
            raise RepositoryControlError(f"{source_id} historical lesson drift")
        detectors = item.get("detector_refs")
        if not isinstance(detectors, list):
            raise RepositoryControlError(f"{source_id} detector refs must be a list")
        if item.get("detectability") == "automatable":
            if not detectors:
                raise RepositoryControlError(
                    f"{source_id} automatable anti-pattern lacks detector"
                )
            for detector in detectors:
                path = _repo_path(detector)
                if not (root / path).is_file():
                    raise RepositoryControlError(
                        f"{source_id} detector missing: {path}"
                    )
        policy = item.get("exception_policy", {})
        if not all(
            policy.get(field) is True
            for field in (
                "allowed",
                "owner_required",
                "rationale_required",
                "expires_at_required",
            )
        ):
            raise RepositoryControlError(
                f"{source_id} anti-pattern exception policy incomplete"
            )
        if not isinstance(policy.get("max_days"), int) or not 1 <= policy["max_days"] <= 90:
            raise RepositoryControlError(
                f"{source_id} anti-pattern exception TTL invalid"
            )


def _validate_build_order(
    payload: dict[str, Any],
    sequence: dict[str, Any],
    queue: dict[str, Any],
    engineering_matrix: dict[str, Any],
) -> None:
    source_waves = {item["id"]: item for item in sequence.get("waves", [])}
    waves = payload.get("waves")
    if not isinstance(waves, list):
        raise RepositoryControlError("build-order waves must be a list")
    actual_waves = {item.get("id"): item for item in waves if isinstance(item, dict)}
    if set(actual_waves) != set(source_waves) or len(actual_waves) != len(waves):
        raise RepositoryControlError("build-order wave coverage drift")
    for wave_id, source in source_waves.items():
        item = actual_waves[wave_id]
        comparisons = {
            "hard_dependencies": source.get("hard_dependencies", []),
            "overlap_allowed_with": source.get("overlap_allowed_with", []),
            "work_package_refs": source.get("work_packages", []),
            "stop_conditions": source.get("stop_conditions", []),
            "definition_of_done": source.get("definition_of_done", []),
        }
        for field, expected in comparisons.items():
            if item.get(field) != expected:
                raise RepositoryControlError(
                    f"{wave_id} build-order {field} drift"
                )
    _assert_acyclic(
        source_waves,
        {
            wave_id: list(wave.get("hard_dependencies", []))
            for wave_id, wave in actual_waves.items()
        },
        "wave",
    )

    source_tasks = {item["task_id"]: item for item in queue.get("tasks", [])}
    engineering_tasks = {
        item["task_id"]: item for item in engineering_matrix.get("tasks", [])
    }
    tasks = payload.get("tasks")
    if not isinstance(tasks, list):
        raise RepositoryControlError("build-order tasks must be a list")
    actual_tasks = {item.get("id"): item for item in tasks if isinstance(item, dict)}
    if set(actual_tasks) != set(source_tasks) or len(actual_tasks) != len(tasks):
        raise RepositoryControlError("build-order task coverage drift")
    dependencies: dict[str, list[str]] = {}
    for task_id, source in source_tasks.items():
        item = actual_tasks[task_id]
        for field in (
            "stage",
            "status",
            "can_start_before_closure_dependencies_close",
        ):
            if item.get(field) != source.get(field):
                raise RepositoryControlError(
                    f"{task_id} build-order {field} drift"
                )
        if item.get("stop_rule") != source.get("failure_rule"):
            raise RepositoryControlError(
                f"{task_id} build-order stop_rule/failure_rule drift"
            )
        task_deps = sorted(set(source.get("task_dependencies", [])))
        closure_deps = sorted(set(source.get("closure_dependencies", [])))
        if item.get("task_dependencies") != task_deps:
            raise RepositoryControlError(f"{task_id} task-dependency drift")
        if item.get("closure_dependencies") != closure_deps:
            raise RepositoryControlError(f"{task_id} closure-dependency drift")
        if item.get("hard_dependencies") != task_deps:
            raise RepositoryControlError(
                f"{task_id} hard dependency DAG must contain task refs only"
            )
        dependencies[task_id] = task_deps
        expected_waves = engineering_tasks.get(task_id, {}).get(
            "construction_wave_refs", []
        )
        if item.get("wave_refs") != expected_waves:
            raise RepositoryControlError(f"{task_id} construction-wave drift")

        tasks_by_gap: dict[str, list[dict[str, Any]]] = {}
        for candidate in source_tasks.values():
            gap = candidate.get("gap")
            if isinstance(gap, str):
                tasks_by_gap.setdefault(gap, []).append(candidate)
        expected_closure_blockers = sorted(
            gap
            for gap in closure_deps
            if not (
                tasks_by_gap.get(gap)
                and all(
                    candidate.get("status") == "done"
                    for candidate in tasks_by_gap[gap]
                )
            )
        )
        if item.get("closure_blockers") != expected_closure_blockers:
            raise RepositoryControlError(f"{task_id} closure-blocker drift")
        expected_blocked = sorted(
            [
                dep
                for dep in task_deps
                if source_tasks.get(dep, {}).get("status") != "done"
            ]
            + (
                []
                if source.get("can_start_before_closure_dependencies_close")
                is True
                else expected_closure_blockers
            )
        )
        if item.get("blocked_by") != expected_blocked:
            raise RepositoryControlError(f"{task_id} blocked-state drift")
        if item.get("work_package_refs") != source.get("work_package_refs", []):
            raise RepositoryControlError(f"{task_id} package refs drift")
        if item.get("accountability_id") != source.get("accountability_id"):
            raise RepositoryControlError(f"{task_id} accountability drift")
    _assert_acyclic(source_tasks, dependencies, "AIQ task")


def _validate_dod(
    payload: dict[str, Any],
    queue: dict[str, Any],
    engineering_matrix: dict[str, Any],
) -> None:
    source_tasks = {item["task_id"]: item for item in queue.get("tasks", [])}
    engineering_tasks = {
        item["task_id"]: item for item in engineering_matrix.get("tasks", [])
    }
    tasks = payload.get("tasks")
    if not isinstance(tasks, list):
        raise RepositoryControlError("DoD tasks must be a list")
    actual = {item.get("task_id"): item for item in tasks if isinstance(item, dict)}
    if set(actual) != set(source_tasks) or len(actual) != len(tasks):
        raise RepositoryControlError("DoD task coverage drift")
    for task_id, source in source_tasks.items():
        engineering = engineering_tasks[task_id]
        item = actual[task_id]
        expected = {
            "accountability_id": source.get("accountability_id"),
            "work_package_refs": source.get("work_package_refs", []),
            "acceptance": source.get("acceptance", []),
            "required_dimensions": engineering.get("required_dimensions", []),
            "evidence_modes": engineering.get("evidence_modes", []),
            "recovery_requirements": engineering.get("recovery_requirements", []),
            "change_impact_triggers": engineering.get("change_impact_triggers", []),
        }
        for field, value in expected.items():
            if item.get(field) != value:
                raise RepositoryControlError(f"{task_id} DoD {field} drift")
        done_requires = item.get("done_requires")
        if not isinstance(done_requires, list) or len(done_requires) < 6:
            raise RepositoryControlError(f"{task_id} DoD requirements incomplete")
    non_comp = " ".join(payload.get("non_compensable", [])).lower()
    for required in ("hard blocker", "implementation signoff", "verification"):
        if required not in non_comp:
            raise RepositoryControlError(
                f"DoD lost non-compensable {required}"
            )


def _validate_debt(
    payload: dict[str, Any],
    master_by_ref: dict[str, dict[str, Any]],
    backlog_ids: set[str],
) -> None:
    expected_ids = {
        f"DEBT-{ref}-G{index:02d}"
        for ref in REPO_REFS
        for index, _ in enumerate(master_by_ref[ref].get("gaps", []), start=1)
    }
    items = payload.get("items")
    if not isinstance(items, list):
        raise RepositoryControlError("debt items must be a list")
    actual = {item.get("id"): item for item in items if isinstance(item, dict)}
    if set(actual) != expected_ids or len(actual) != len(items):
        raise RepositoryControlError("technical debt coverage drift")
    for ref in REPO_REFS:
        volume = master_by_ref[ref]
        for index, gap in enumerate(volume.get("gaps", []), start=1):
            debt_id = f"DEBT-{ref}-G{index:02d}"
            item = actual[debt_id]
            source = item.get("source", {})
            if source.get("ref") != f"{ref}#gap-{index}" or source.get("text") != gap:
                raise RepositoryControlError(f"{debt_id} source drift")
            if item.get("owner", {}).get("accountability_id") != volume.get(
                "accountability_id"
            ):
                raise RepositoryControlError(f"{debt_id} owner missing/drift")
            if item.get("affected_contracts") != volume.get("contracts", []):
                raise RepositoryControlError(f"{debt_id} contract impact drift")
            if item.get("risk_text") != volume.get("risks", []):
                raise RepositoryControlError(f"{debt_id} risk binding drift")
            backlog_ref = f"BL-GAP-{ref}-G{index:02d}"
            if item.get("backlog_ref") != backlog_ref or backlog_ref not in backlog_ids:
                raise RepositoryControlError(f"{debt_id} backlog binding missing")
            adr = item.get("adr_disposition")
            if not isinstance(adr, dict):
                raise RepositoryControlError(f"{debt_id} lacks ADR disposition")
            if not adr.get("adr_ref") and not (
                isinstance(adr.get("rationale"), str) and adr["rationale"].strip()
            ):
                raise RepositoryControlError(
                    f"{debt_id} requires ADR ref or explicit no-ADR rationale"
                )


def _validate_roadmap(
    payload: dict[str, Any],
    sequence: dict[str, Any],
    p2: dict[str, Any],
    p2_map: dict[str, Any],
) -> None:
    freeze = payload.get("breadth_freeze", {})
    if (
        freeze.get("last_top_level_volume") != 420
        or freeze.get("new_top_level_scope_requires_adr") is not True
    ):
        raise RepositoryControlError("roadmap breadth freeze drift")
    expected: dict[str, dict[str, Any]] = {}
    for wave in sequence.get("waves", []):
        expected[f"ROAD-{wave['id']}"] = {
            "kind": "construction_wave",
            "source_ref": wave["id"],
            "depends_on": [f"ROAD-{dep}" for dep in wave.get("hard_dependencies", [])],
            "work_package_refs": wave.get("work_packages", []),
        }
    for task in p2.get("tasks", []):
        expected[f"ROAD-{task['task_id']}"] = {
            "kind": "p2_lane",
            "source_ref": task["task_id"],
            "depends_on": [f"ROAD-{dep}" for dep in task.get("depends_on", [])],
            "volume_refs": task.get("primary_volume_refs", []),
            "status": task.get("status"),
        }
    items = payload.get("items")
    if not isinstance(items, list):
        raise RepositoryControlError("roadmap items must be a list")
    actual = {item.get("id"): item for item in items if isinstance(item, dict)}
    if set(actual) != set(expected) or len(actual) != len(items):
        raise RepositoryControlError("roadmap DAG coverage drift")
    for item_id, fields in expected.items():
        for field, value in fields.items():
            if actual[item_id].get(field) != value:
                raise RepositoryControlError(
                    f"{item_id} roadmap {field} drift"
                )
    _assert_acyclic(
        actual,
        {item_id: list(item.get("depends_on", [])) for item_id, item in actual.items()},
        "roadmap",
    )
    revisions = payload.get("revisions")
    if not isinstance(revisions, list) or len(revisions) < 4:
        raise RepositoryControlError("roadmap revision lineage incomplete")
    if len({item.get("id") for item in revisions}) != len(revisions):
        raise RepositoryControlError("duplicate roadmap revision id")
    latest = revisions[-1]
    expected_latest = {
        "p2_map_version": p2_map.get("map_version"),
        "p2_backlog_version": p2.get("backlog_version"),
        "build_sequence_version": sequence.get("sequence_version"),
    }
    for field, expected in expected_latest.items():
        if latest.get(field) != expected:
            raise RepositoryControlError(
                f"roadmap current-source revision {field} drift"
            )
    if latest.get("preserves_history") is not True:
        raise RepositoryControlError("roadmap current-source revision must preserve history")


def _atomic_state(task: dict[str, Any], acc_by: dict[str, dict[str, Any]]) -> dict[str, Any]:
    account = acc_by.get(task.get("accountability_id"), {})
    checkbox = account.get("checkbox") is True
    implementation = account.get("implementation_signoff", {}).get("signed") is True
    verification = account.get("verification_signoff", {}).get("signed") is True
    evidence_count = len(account.get("evidence", []))
    return {
        "id": task["task_id"],
        "accountability_id": task["accountability_id"],
        "queue_status": task.get("status"),
        "checkbox": checkbox,
        "implementation_signed": implementation,
        "verification_signed": verification,
        "evidence_count": evidence_count,
        "derived_state": (
            "verified_atomic"
            if (
                task.get("status") == "done"
                and checkbox
                and implementation
                and verification
                and evidence_count > 0
            )
            else "incomplete"
        ),
    }


def _validate_completion(
    payload: dict[str, Any],
    queue: dict[str, Any],
    accountability: dict[str, Any],
    work_packages: dict[str, Any],
    sequence: dict[str, Any],
    edge_queue: dict[str, Any],
) -> dict[str, int | bool]:
    acc_by = {
        item.get("id"): item
        for item in accountability.get("records", [])
        if isinstance(item, dict)
    }
    expected_atomic = [
        _atomic_state(task, acc_by) for task in queue.get("tasks", [])
    ]
    if payload.get("atomic_tasks") != expected_atomic:
        raise RepositoryControlError(
            "completion atomic state drift/manual inflation detected"
        )
    atomic_by = {item["id"]: item for item in expected_atomic}

    expected_packages: list[dict[str, Any]] = []
    for package in work_packages.get("packages", []):
        members = [
            atomic_by[task_id]
            for task_id in package.get("task_refs", [])
            if task_id in atomic_by
        ]
        verified = sum(
            member["derived_state"] == "verified_atomic" for member in members
        )
        evidence = package.get("evidence_rollup", {}).get(
            "package_evidence_count", 0
        )
        expected_packages.append(
            {
                "id": package["id"],
                "task_count": len(members),
                "verified_atomic_count": verified,
                "package_evidence_count": evidence,
                "derived_state": (
                    "verified_package"
                    if members and verified == len(members) and evidence > 0
                    else "incomplete"
                ),
            }
        )
    if payload.get("packages") != expected_packages:
        raise RepositoryControlError(
            "completion package rollup drift/manual inflation detected"
        )
    package_by = {item["id"]: item for item in expected_packages}

    expected_waves: list[dict[str, Any]] = []
    for wave in sequence.get("waves", []):
        members = [
            package_by[package_id]
            for package_id in wave.get("work_packages", [])
            if package_id in package_by
        ]
        verified = sum(
            member["derived_state"] == "verified_package" for member in members
        )
        expected_waves.append(
            {
                "id": wave["id"],
                "package_count": len(members),
                "verified_package_count": verified,
                "hard_dependencies": wave.get("hard_dependencies", []),
                "derived_state": (
                    "verified_wave"
                    if members and verified == len(members)
                    else "incomplete"
                ),
            }
        )
    if payload.get("waves") != expected_waves:
        raise RepositoryControlError(
            "completion wave rollup drift/manual inflation detected"
        )
    unresolved_p0 = [
        item
        for item in edge_queue.get("items", [])
        if item.get("priority") == "P0"
        and item.get("status") not in {"passing", "accepted_risk", "closed"}
    ]
    blockers = payload.get("blockers", {})
    refs = [item["id"] for item in unresolved_p0]
    if blockers.get("unresolved_p0_count") != len(refs) or blockers.get(
        "unresolved_p0_refs"
    ) != refs:
        raise RepositoryControlError("completion P0 blocker snapshot drift")
    rollup = {
        "atomic_total": len(expected_atomic),
        "atomic_verified": sum(
            item["derived_state"] == "verified_atomic" for item in expected_atomic
        ),
        "package_total": len(expected_packages),
        "package_verified": sum(
            item["derived_state"] == "verified_package"
            for item in expected_packages
        ),
        "wave_total": len(expected_waves),
        "wave_verified": sum(
            item["derived_state"] == "verified_wave" for item in expected_waves
        ),
        "strong_completion_blocked": bool(refs),
    }
    if payload.get("rollup") != rollup:
        raise RepositoryControlError("completion rollup drift")
    if "manual percentages are not completion authority" not in str(
        payload.get("ui_projection_rule", "")
    ).lower():
        raise RepositoryControlError(
            "completion UI projection must reject manual percentages"
        )
    return rollup


def validate(root: Path = ROOT) -> dict[str, Any]:
    root = root.resolve()
    master = _load(root, "machine/ai_master_plan.json")
    p2 = _load(root, "machine/ai_p2_task_backlog.json")
    p2_map = _load(root, "machine/ai_p2_execution_map.json")
    edge_queue = _load(root, "machine/ai_edge_case_priority_queue.json")
    engineering = _load(root, "machine/ai_engineering_pass.json")
    matrix = _load(root, "machine/ai_full_edge_case_matrix.json")
    queue = _load(root, "machine/ai_build_queue.json")
    engineering_matrix = _load(root, "machine/ai_engineering_task_matrix.json")
    sequence = _load(root, "machine/ai_master_build_sequence.json")
    accountability = _load(root, "machine/ai_build_accountability.json")
    architecture = _load(root, "machine/architecture.json")
    catalog = _load(root, "machine/ai_edge_case_catalog.json")
    _load(root, "machine/master_traceability.json")

    master_by_ref = {
        volume["key"]: volume
        for volume in master.get("volumes", [])
        if isinstance(volume, dict) and isinstance(volume.get("key"), str)
    }
    if not set(REPO_REFS) <= set(master_by_ref):
        raise RepositoryControlError("masterplan missing P2 repository volumes")

    umbrella = _load(root, "machine/repository_control.json")
    if umbrella.get("status") not in {"active_stacked", "active"}:
        raise RepositoryControlError("repository control must be active")
    if umbrella.get("task_ref") != "P2-REPO-01":
        raise RepositoryControlError("repository control task_ref drift")
    bindings = umbrella.get("masterplan_bindings")
    if not isinstance(bindings, list):
        raise RepositoryControlError("repository umbrella bindings must be a list")
    by_ref = {item.get("volume_ref"): item for item in bindings if isinstance(item, dict)}
    if set(by_ref) != set(REPO_REFS) or len(by_ref) != len(bindings):
        raise RepositoryControlError("repository umbrella volume coverage drift")
    for ref in REPO_REFS:
        volume = master_by_ref[ref]
        item = by_ref[ref]
        if (
            item.get("title") != volume.get("title")
            or item.get("accountability_id") != volume.get("accountability_id")
            or item.get("required_gap_texts") != volume.get("gaps", [])
        ):
            raise RepositoryControlError(f"repository umbrella binding drift for {ref}")

    authority_entries = umbrella.get("authorities")
    expected_authority_entries = [
        {"volume_ref": ref, "path": AUTHORITY_BY_REF[ref]}
        for ref in REPO_REFS
    ]
    if authority_entries != expected_authority_entries:
        raise RepositoryControlError("repository umbrella authority map drift")

    authorities = {
        ref: _load(root, relative)
        for ref, relative in AUTHORITY_BY_REF.items()
    }
    for ref, relative in AUTHORITY_BY_REF.items():
        _assert_binding(authorities[ref], master_by_ref, ref, relative)

    _validate_graph_contract(root, authorities["VOL-021"])
    _validate_engineering_policy(root, authorities["VOL-022"])
    _validate_maintenance(architecture, authorities["VOL-092"])
    backlog_ids = _validate_backlog(
        authorities["VOL-093"], p2, edge_queue, master_by_ref
    )
    _validate_priority(authorities["VOL-094"])
    package_by_id = _validate_work_packages(
        authorities["VOL-095"],
        engineering,
        matrix,
        queue,
        sequence,
        accountability,
    )
    _validate_antipatterns(root, authorities["VOL-108"], catalog)
    _validate_build_order(
        authorities["VOL-109"], sequence, queue, engineering_matrix
    )
    _validate_dod(authorities["VOL-110"], queue, engineering_matrix)
    _validate_debt(authorities["VOL-115"], master_by_ref, backlog_ids)
    _validate_roadmap(authorities["VOL-118"], sequence, p2, p2_map)
    rollup = _validate_completion(
        authorities["VOL-119"],
        queue,
        accountability,
        authorities["VOL-095"],
        sequence,
        edge_queue,
    )

    counts = umbrella.get("expected_counts", {})
    expected_counts = {
        "primary_volume_count": len(REPO_REFS),
        "canonical_backlog_item_count": len(backlog_ids),
        "work_package_count": len(package_by_id),
        "aiq_task_count": len(queue.get("tasks", [])),
        "build_wave_count": len(sequence.get("waves", [])),
        "debt_item_count": len(authorities["VOL-115"].get("items", [])),
        "roadmap_item_count": len(authorities["VOL-118"].get("items", [])),
    }
    if counts != expected_counts:
        raise RepositoryControlError(
            f"repository umbrella count drift: {counts!r} != {expected_counts!r}"
        )

    return {
        "status": "valid",
        "volume_count": len(REPO_REFS),
        "backlog_count": len(backlog_ids),
        "work_package_count": len(package_by_id),
        "aiq_task_count": len(queue.get("tasks", [])),
        "wave_count": len(sequence.get("waves", [])),
        "anti_pattern_count": len(authorities["VOL-108"].get("entries", [])),
        "debt_count": len(authorities["VOL-115"].get("items", [])),
        "roadmap_count": len(authorities["VOL-118"].get("items", [])),
        "completion_rollup": rollup,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        result = validate(Path(args.repo_root))
    except RepositoryControlError as exc:
        print(f"P2 repository control: FAIL: {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(result, sort_keys=True))
    else:
        print(
            "P2 repository control: OK "
            f"({result['backlog_count']} backlog, "
            f"{result['work_package_count']} packages, "
            f"{result['aiq_task_count']} tasks, "
            f"{result['wave_count']} waves)"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
