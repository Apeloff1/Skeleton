#!/usr/bin/env python3
"""Validate the focused P2-TRACE-01 projections against canonical trace authority.

The canonical requirements-to-runtime graph is the sharded master trace validated by
check_master_traceability.py and check_traceability_spine.py. This validator adds
narrow runtime projections for capability presence, P2 maturity observation, and
runtime protocol families. It never replaces or promotes canonical authority.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

TRACE_REFS = (
    "VOL-112", "VOL-113", "VOL-122", "VOL-123", "VOL-124", "VOL-125",
    "VOL-126", "VOL-127", "VOL-128", "VOL-129", "VOL-130", "VOL-131",
)

FOCUSED_WORKFLOW = Path(".github/workflows/p2-traceability.yml")
MASTER_WORKFLOW = Path(".github/workflows/p2-traceability-spine.yml")


class P2TraceabilityError(RuntimeError):
    pass


def _load(root: Path, relative: str | Path) -> dict[str, Any]:
    path = root / Path(relative)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise P2TraceabilityError(f"missing required file: {relative}") from exc
    except json.JSONDecodeError as exc:
        raise P2TraceabilityError(f"invalid JSON in {relative}: {exc}") from exc
    if not isinstance(data, dict):
        raise P2TraceabilityError(f"{relative} must contain an object")
    return data


def _load_module(root: Path, module_name: str, relative: str):
    path = root / relative
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise P2TraceabilityError(f"cannot load validator module: {relative}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _git_blob_sha(path: Path) -> str:
    data = path.read_bytes()
    return hashlib.sha1(f"blob {len(data)}\0".encode("ascii") + data).hexdigest()


def _master_by_ref(master: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        item["key"]: item
        for item in master.get("volumes", [])
        if isinstance(item, dict) and isinstance(item.get("key"), str)
    }


def _assert_binding(
    master_by_ref: dict[str, dict[str, Any]],
    payload: dict[str, Any],
    ref: str,
) -> None:
    binding = payload.get("masterplan_binding")
    volume = master_by_ref.get(ref)
    if not isinstance(binding, dict) or not isinstance(volume, dict):
        raise P2TraceabilityError(f"{ref} projection requires a masterplan binding")
    if binding.get("volume_ref") != ref or binding.get("title") != volume.get("title"):
        raise P2TraceabilityError(f"{ref} projection masterplan identity drift")
    required = binding.get("required_gap_texts")
    if not isinstance(required, list) or set(required) != set(volume.get("gaps", [])):
        raise P2TraceabilityError(f"{ref} projection must preserve exact masterplan gaps")


def _validate_task(master: dict[str, Any], backlog: dict[str, Any]) -> dict[str, Any]:
    task = next(
        (
            item
            for item in backlog.get("tasks", [])
            if isinstance(item, dict) and item.get("task_id") == "P2-TRACE-01"
        ),
        None,
    )
    if not isinstance(task, dict):
        raise P2TraceabilityError("P2-TRACE-01 is missing")

    if task.get("primary_volume_refs") != list(TRACE_REFS):
        raise P2TraceabilityError("P2-TRACE-01 volume scope drift")
    if task.get("status") != "in_progress":
        raise P2TraceabilityError("P2-TRACE-01 must remain in_progress")
    if task.get("completion_checkbox") is not False or task.get("completion_checkbox_mark") != "[ ]":
        raise P2TraceabilityError("P2-TRACE-01 may not claim completion")
    if task.get("implementation_signed") is not False or task.get("verification_signed") is not False:
        raise P2TraceabilityError("P2-TRACE-01 may not fabricate sign-off")

    canonical = _master_by_ref(master)
    obligations = task.get("masterplan_obligations")
    if not isinstance(obligations, list) or len(obligations) != len(TRACE_REFS):
        raise P2TraceabilityError("P2-TRACE-01 obligation coverage drift")
    by_ref = {
        item.get("volume_ref"): item
        for item in obligations
        if isinstance(item, dict)
    }
    if set(by_ref) != set(TRACE_REFS):
        raise P2TraceabilityError("P2-TRACE-01 obligation identity drift")

    for ref in TRACE_REFS:
        volume = canonical.get(ref)
        obligation = by_ref[ref]
        if not isinstance(volume, dict):
            raise P2TraceabilityError(f"masterplan missing {ref}")
        for field in ("title", "contracts", "risks", "gaps"):
            if obligation.get(field) != volume.get(field):
                raise P2TraceabilityError(f"P2-TRACE-01 narrows {ref}.{field}")
        if obligation.get("completion_checkbox") is not False:
            raise P2TraceabilityError(f"{ref} obligation may not claim completion")
        if obligation.get("signing_required") is not True:
            raise P2TraceabilityError(f"{ref} signing requirement drift")

    evidence = set(task.get("evidence_refs", []))
    required = {
        "machine:master_traceability.json",
        "workflow:P2 Master Traceability Spine",
        "workflow:P2 Traceability Focused Contract",
    }
    if not required <= evidence:
        raise P2TraceabilityError("P2-TRACE-01 must reference both independent trace workflows")
    return {"task_status": task["status"], "trace_volume_count": len(TRACE_REFS)}


def _workflow_descriptor(root: Path, relative: Path) -> dict[str, str]:
    text = (root / relative).read_text(encoding="utf-8")
    name = re.search(r"^name:\s*(.+?)\s*$", text, re.MULTILINE)
    group = re.search(r"^\s*group:\s*(.+?)\s*$", text, re.MULTILINE)
    if name is None or group is None:
        raise P2TraceabilityError(f"{relative} lacks workflow name/concurrency group")
    if "feat/p2-traceability-spine" not in text:
        raise P2TraceabilityError(f"{relative} must self-validate the active trace branch")
    return {"path": relative.as_posix(), "name": name.group(1), "group": group.group(1)}


def _validate_workflows(root: Path) -> dict[str, Any]:
    entries = [
        _workflow_descriptor(root, FOCUSED_WORKFLOW),
        _workflow_descriptor(root, MASTER_WORKFLOW),
    ]
    if len({item["name"] for item in entries}) != 2:
        raise P2TraceabilityError("P2 trace workflows must have distinct names")
    if len({item["group"] for item in entries}) != 2:
        raise P2TraceabilityError("P2 trace workflows must have distinct concurrency groups")
    return {"workflow_count": 2, "workflows": entries}


def _validate_capability_projection(
    root: Path,
    master_by_ref: dict[str, dict[str, Any]],
    projection: dict[str, Any],
) -> dict[str, Any]:
    _assert_binding(master_by_ref, projection, "VOL-113")
    if projection.get("authority_role") != "runtime_projection":
        raise P2TraceabilityError("capability projection authority_role drift")
    if projection.get("canonical_sources") != [
        "machine/capability_taxonomy.json",
        "machine/capability_interfaces.json",
    ]:
        raise P2TraceabilityError("capability projection canonical source drift")
    source = projection.get("source")
    if source != "machine/capability_interfaces.json":
        raise P2TraceabilityError("capability projection source drift")
    if projection.get("source_git_blob_sha") != _git_blob_sha(root / source):
        raise P2TraceabilityError("capability projection source digest drift")

    interfaces = _load(root, source)
    expected_planes = sorted(
        {
            plane
            for edge in interfaces.get("entries", [])
            if isinstance(edge, dict)
            for plane in (edge.get("source_plane"), edge.get("target_plane"))
            if isinstance(plane, str) and plane
        }
    )
    entries = projection.get("capabilities")
    if not isinstance(entries, list):
        raise P2TraceabilityError("capability projection entries must be a list")
    actual = [item.get("plane") for item in entries if isinstance(item, dict)]
    if sorted(actual) != expected_planes or len(actual) != len(set(actual)):
        raise P2TraceabilityError("capability projection plane coverage drift")
    if any(item.get("status") != "present" for item in entries if isinstance(item, dict)):
        raise P2TraceabilityError("capability projection may report presence only")
    return {"runtime_projection_count": len(entries)}


def _validate_maturity_projection(
    root: Path,
    master_by_ref: dict[str, dict[str, Any]],
    projection: dict[str, Any],
    canonical: dict[str, Any],
) -> dict[str, Any]:
    _assert_binding(master_by_ref, projection, "VOL-125")
    if projection.get("authority_role") != "p2_trace_maturity_projection":
        raise P2TraceabilityError("maturity projection authority_role drift")
    if projection.get("canonical_source") != "machine/maturity_registry.json":
        raise P2TraceabilityError("maturity projection canonical source drift")
    if projection.get("scope_volume_refs") != list(TRACE_REFS):
        raise P2TraceabilityError("maturity projection scope drift")

    for key, expected_path in (
        ("master_plan", "machine/ai_master_plan.json"),
        ("accountability", "machine/ai_build_accountability.json"),
    ):
        descriptor = projection.get("sources", {}).get(key)
        if not isinstance(descriptor, dict) or descriptor.get("path") != expected_path:
            raise P2TraceabilityError(f"maturity projection {key} source drift")
        if descriptor.get("git_blob_sha") != _git_blob_sha(root / expected_path):
            raise P2TraceabilityError(f"maturity projection {key} digest drift")

    canonical_entries = canonical.get("entries")
    if not isinstance(canonical_entries, list):
        raise P2TraceabilityError("canonical maturity registry entries must be a list")
    canonical_by_ref = {
        item.get("volume_ref"): item
        for item in canonical_entries
        if isinstance(item, dict)
    }

    entries = projection.get("volumes")
    if not isinstance(entries, list) or [item.get("volume_ref") for item in entries] != list(TRACE_REFS):
        raise P2TraceabilityError("maturity projection volume coverage/order drift")

    for item in entries:
        ref = item["volume_ref"]
        canon = canonical_by_ref.get(ref)
        if not isinstance(canon, dict):
            raise P2TraceabilityError(f"canonical maturity registry missing {ref}")
        if item.get("accountability_id") != canon.get("accountability_id"):
            raise P2TraceabilityError(f"{ref} accountability identity drift")
        if item.get("masterplan_status") != canon.get("current_implementation_status"):
            raise P2TraceabilityError(
                f"{ref} maturity implementation-status drift"
            )
        if item.get("checkbox") != canon.get("completion_checkbox"):
            raise P2TraceabilityError(f"{ref} maturity checkbox drift")
        if item.get("implementation_signed") is not False or item.get("verification_signed") is not False:
            raise P2TraceabilityError(f"{ref} maturity projection may not sign")
    return {"maturity_projection_count": len(entries)}


def _schema_names(registry: dict[str, Any]) -> set[str]:
    result: set[str] = set()
    for item in registry.get("schemas", []):
        if not isinstance(item, dict):
            continue
        if isinstance(item.get("name"), str):
            result.add(item["name"])
            continue
        schema_id = item.get("schema_id") or item.get("id")
        if isinstance(schema_id, str) and schema_id.startswith("SCHEMA-"):
            result.add(schema_id[7:])
    return result


def _validate_protocol_projection(
    root: Path,
    master_by_ref: dict[str, dict[str, Any]],
    projection: dict[str, Any],
) -> dict[str, Any]:
    _assert_binding(master_by_ref, projection, "VOL-131")
    if projection.get("authority_role") != "runtime_protocol_projection":
        raise P2TraceabilityError("protocol projection authority_role drift")
    if projection.get("canonical_source") != "machine/protocol_registry.json":
        raise P2TraceabilityError("protocol projection canonical source drift")
    if not (root / projection["canonical_source"]).is_file():
        raise P2TraceabilityError("canonical protocol registry is missing")
    if projection.get("schema_source") != "machine/schema_registry.json":
        raise P2TraceabilityError("protocol projection schema source drift")

    schemas = _schema_names(_load(root, projection["schema_source"]))
    protocols = projection.get("protocols")
    if not isinstance(protocols, list) or len(protocols) != 4:
        raise P2TraceabilityError("protocol projection must contain four runtime families")
    ids: set[str] = set()
    for item in protocols:
        if not isinstance(item, dict):
            raise P2TraceabilityError("protocol projection entry must be an object")
        protocol_id = item.get("id")
        if not isinstance(protocol_id, str) or not protocol_id or protocol_id in ids:
            raise P2TraceabilityError(f"invalid/duplicate protocol projection ID: {protocol_id!r}")
        ids.add(protocol_id)
        envelopes = item.get("envelope_schemas")
        if not isinstance(envelopes, list) or not envelopes:
            raise P2TraceabilityError(f"{protocol_id} lacks envelope schemas")
        missing = sorted(set(envelopes) - schemas)
        if missing:
            raise P2TraceabilityError(
                f"{protocol_id} references schemas outside canonical registry: {missing}"
            )
        if not isinstance(item.get("tracing"), str) or not item["tracing"].strip():
            raise P2TraceabilityError(f"{protocol_id} lacks tracing semantics")
    return {"protocol_projection_count": len(protocols)}


def validate(
    root: Path = ROOT,
    *,
    changed_files: list[str] | None = None,
) -> dict[str, Any]:
    root = root.resolve()

    # Canonical deep authority validates first. A focused projection can never turn
    # a broken master trace green.
    master_module = _load_module(
        root, "p2_master_trace", "scripts/check_master_traceability.py"
    )
    spine_module = _load_module(
        root, "p2_trace_spine", "scripts/check_traceability_spine.py"
    )
    try:
        master_result = master_module.validate(root)
        spine_result = spine_module.validate(root, changed_files=changed_files)
    except Exception as exc:
        raise P2TraceabilityError(f"canonical trace validation failed: {exc}") from exc

    master = _load(root, "machine/ai_master_plan.json")
    master_by_ref = _master_by_ref(master)
    backlog = _load(root, "machine/ai_p2_task_backlog.json")
    capability = _load(root, "machine/capability_registry.json")
    maturity = _load(root, "machine/capability_maturity.json")
    canonical_maturity = _load(root, "machine/maturity_registry.json")
    protocols = _load(root, "machine/internal_protocols.json")

    result: dict[str, Any] = {"status": "valid"}
    result.update(_validate_task(master, backlog))
    result.update(_validate_workflows(root))
    result.update(_validate_capability_projection(root, master_by_ref, capability))
    result.update(
        _validate_maturity_projection(
            root, master_by_ref, maturity, canonical_maturity
        )
    )
    result.update(_validate_protocol_projection(root, master_by_ref, protocols))

    result["master_trace_volume_count"] = master_result.get("volume_count")
    result["master_trace_requirement_count"] = master_result.get("requirement_count")
    result["master_trace_node_count"] = master_result.get("node_count")
    result["master_trace_edge_count"] = master_result.get("edge_count")
    result["canonical_spine_requirement_count"] = spine_result.get("requirement_count")
    result["canonical_spine_maturity_entry_count"] = spine_result.get(
        "maturity_entry_count"
    )
    if changed_files is not None:
        result["impact"] = spine_result.get("impact")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--changed-file-list",
        help="Optional newline-delimited changed paths for canonical impact analysis.",
    )
    args = parser.parse_args()
    root = Path(args.repo_root).resolve()
    changed = None
    if args.changed_file_list:
        try:
            changed = [
                line.strip()
                for line in Path(args.changed_file_list)
                .read_text(encoding="utf-8")
                .splitlines()
                if line.strip()
            ]
        except OSError as exc:
            print(f"P2 traceability projection: FAIL: {exc}", file=sys.stderr)
            return 1
    try:
        result = validate(root, changed_files=changed)
    except (P2TraceabilityError, OSError) as exc:
        print(f"P2 traceability projection: FAIL: {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(result, sort_keys=True))
    else:
        print(
            "P2 traceability projection: OK "
            f"({result['trace_volume_count']} P2 volumes, "
            f"{result['runtime_projection_count']} runtime planes, "
            f"{result['protocol_projection_count']} protocol families)"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
