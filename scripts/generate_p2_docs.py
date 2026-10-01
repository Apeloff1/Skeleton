#!/usr/bin/env python3
"""Deterministically generate P2 machine-derived documentation."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import sys
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = Path("machine/generated_documentation.json")
GENERATOR_ID = "p2-docs/0.1.0"


class GeneratedDocumentationError(RuntimeError):
    pass


def _load(root: Path, relative: str) -> dict[str, Any]:
    path = root / relative
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise GeneratedDocumentationError(f"missing source: {relative}") from exc
    except json.JSONDecodeError as exc:
        raise GeneratedDocumentationError(f"invalid JSON in {relative}: {exc}") from exc
    if not isinstance(data, dict):
        raise GeneratedDocumentationError(f"{relative} must contain a JSON object")
    return data


def _path(value: object) -> str:
    if not isinstance(value, str) or not value or "\x00" in value or "\\" in value:
        raise GeneratedDocumentationError(f"invalid repository path: {value!r}")
    pure = PurePosixPath(value)
    if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
        raise GeneratedDocumentationError(f"unsafe repository path: {value!r}")
    if pure.as_posix() != value:
        raise GeneratedDocumentationError(f"non-canonical repository path: {value!r}")
    return value


def _git_blob_sha(path: Path) -> str:
    data = path.read_bytes()
    return hashlib.sha1(f"blob {len(data)}\0".encode("ascii") + data).hexdigest()


def _source_marker(root: Path, relative: str) -> str:
    return f"<!-- source-git-blob: {relative}@{_git_blob_sha(root / relative)} -->"


def _render_p2(root: Path) -> str:
    p2map = _load(root, "machine/ai_p2_execution_map.json")
    backlog = _load(root, "machine/ai_p2_task_backlog.json")
    trace = _load(root, "machine/master_traceability.json")
    tasks = backlog.get("tasks")
    if not isinstance(tasks, list):
        raise GeneratedDocumentationError("P2 backlog tasks must be a list")
    for task in tasks:
        if not isinstance(task, dict) or not isinstance(task.get("task_id"), str):
            raise GeneratedDocumentationError("P2 backlog contains invalid task identity")
    lines = [
        "# P2 Authority Snapshot",
        "",
        "<!-- generated-document: do-not-edit -->",
        f"<!-- generator: {GENERATOR_ID} -->",
        _source_marker(root, "machine/ai_p2_execution_map.json"),
        _source_marker(root, "machine/ai_p2_task_backlog.json"),
        _source_marker(root, "machine/master_traceability.json"),
        "",
        "> Generated from machine authority. This file has zero completion, maturity, signing, or promotion authority. Regenerate it; do not hand-edit derived sections.",
        "",
        "## Scope",
        "",
        f"- P2 source volumes: **{p2map['source_scope']['expected_volume_count']}**",
        f"- First-tranche scheduled volumes: **{p2map['first_tranche']['scheduled_volume_count']}**",
        f"- Explicitly queued volumes: **{p2map['first_tranche']['queued_volume_count']}**",
        f"- Task records: **{len(tasks)}**",
        "",
        "## Task authority snapshot",
        "",
        "| Task | Lane | Source status | Checkbox | Implementation signed | Verification signed |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for task in sorted(tasks, key=lambda item: item["task_id"]):
        lines.append(
            f"| {task['task_id']} | {task['lane_id']} | {task['status']} | "
            f"{task['completion_checkbox_mark']} | {task['implementation_signed']} | "
            f"{task['verification_signed']} |"
        )
    summary = trace.get("summary")
    if not isinstance(summary, dict):
        raise GeneratedDocumentationError("traceability summary missing")
    lines.extend(
        [
            "",
            "The status/signing fields above are reproduced exactly from the machine backlog. This generator does not reinterpret them or infer completion from merged code.",
            "",
            "## Traceability snapshot",
            "",
            f"- Trace nodes: **{summary['node_count']}**",
            f"- Trace edges: **{summary['edge_count']}**",
            f"- Canonical requirements: **{summary['requirement_count']}**",
            f"- Requirements without evidence: **{summary['requirements_without_evidence']}**",
            f"- Trace shards: **{summary['shard_count']}**",
            "",
            "Evidence debt remains debt; it is not averaged away by the generated snapshot.",
            "",
        ]
    )
    return "\n".join(lines)


def _render_architecture(root: Path) -> str:
    registry = _load(root, "machine/architecture_rule_registry.json")
    architecture = _load(root, "machine/architecture.json")
    adr = _load(root, "machine/adr_index.json")
    rules = registry.get("rules")
    roots = architecture.get("canonical_roots")
    zones = architecture.get("zones")
    records = adr.get("records")
    if not all(isinstance(x, list) for x in (rules, roots, zones, records)):
        raise GeneratedDocumentationError("architecture source lists are malformed")
    rule_ids = [item.get("id") for item in rules if isinstance(item, dict)]
    if len(rule_ids) != len(rules) or len(rule_ids) != len(set(rule_ids)):
        raise GeneratedDocumentationError("architecture rule IDs are invalid/duplicate")
    adr_ids = [item.get("id") for item in records if isinstance(item, dict)]
    if len(adr_ids) != len(records) or len(adr_ids) != len(set(adr_ids)):
        raise GeneratedDocumentationError("ADR IDs are invalid/duplicate")
    lines = [
        "# Architecture Control Index",
        "",
        "<!-- generated-document: do-not-edit -->",
        f"<!-- generator: {GENERATOR_ID} -->",
        _source_marker(root, "machine/architecture_rule_registry.json"),
        _source_marker(root, "machine/architecture.json"),
        _source_marker(root, "machine/adr_index.json"),
        "",
        "> Generated from architecture machine authority. Regenerate this file after source changes; do not hand-edit rule or ADR listings.",
        "",
        "## Canonical topology",
        "",
        f"- Canonical roots: **{len(roots)}**",
        f"- Architecture zones: **{len(zones)}**",
        f"- Registered fitness rules: **{len(rules)}**",
        f"- ADR records: **{len(records)}**",
        "",
        "## Registered architecture rules",
        "",
        "| Rule | Validator | Severity | Waivable |",
        "| --- | --- | --- | --- |",
    ]
    for rule in sorted(rules, key=lambda item: item["id"]):
        validator = _path(rule["validator_path"])
        if not (root / validator).is_file():
            raise GeneratedDocumentationError(
                f"architecture rule validator missing: {validator}"
            )
        lines.append(
            f"| {rule['id']} | `{validator}` | {rule['severity']} | "
            f"{rule['waiver_policy']['allowed']} |"
        )
    lines.extend(["", "## Architecture decisions", ""])
    if records:
        lines.extend(
            [
                "| ADR | Status | Document | Masterplan refs |",
                "| --- | --- | --- | --- |",
            ]
        )
        for record in sorted(records, key=lambda item: item["id"]):
            document = _path(record["path"])
            if not (root / document).is_file():
                raise GeneratedDocumentationError(
                    f"indexed ADR document missing: {document}"
                )
            refs = ", ".join(record.get("masterplan_refs", []))
            lines.append(
                f"| {record['id']} | {record['status']} | `{document}` | {refs} |"
            )
    else:
        lines.append("_No ADR records are currently indexed._")
    lines.extend(
        [
            "",
            "Generated listings are navigational only; machine manifests remain authoritative.",
            "",
        ]
    )
    return "\n".join(lines)


RENDERERS: dict[str, Callable[[Path], str]] = {
    "docs/generated/P2_AUTHORITY_SNAPSHOT.md": _render_p2,
    "docs/generated/ARCHITECTURE_CONTROL_INDEX.md": _render_architecture,
}


def validate_manifest(root: Path) -> dict[str, Any]:
    manifest = _load(root, MANIFEST.as_posix())
    master = _load(root, "machine/ai_master_plan.json")
    if manifest.get("status") != "active":
        raise GeneratedDocumentationError("generated documentation manifest must be active")
    policy = manifest.get("policy")
    if not isinstance(policy, dict):
        raise GeneratedDocumentationError("generated documentation policy missing")
    if policy.get("output_root") != "docs/generated":
        raise GeneratedDocumentationError("generated output root drift")
    if policy.get("generator_identity") != GENERATOR_ID:
        raise GeneratedDocumentationError("generator identity drift")
    if policy.get("source_identity") != "git-blob-sha1":
        raise GeneratedDocumentationError("source identity policy drift")

    volumes = {
        item.get("key"): item
        for item in master.get("volumes", [])
        if isinstance(item, dict)
    }
    bindings = {
        item.get("volume_ref"): item
        for item in manifest.get("masterplan_bindings", [])
        if isinstance(item, dict)
    }
    if set(bindings) != {"VOL-089", "VOL-090"}:
        raise GeneratedDocumentationError("masterplan binding coverage drift")
    for ref, binding in bindings.items():
        volume = volumes.get(ref)
        if not isinstance(volume, dict):
            raise GeneratedDocumentationError(f"masterplan volume missing: {ref}")
        expected = {
            "title": volume.get("title"),
            "accountability_id": volume.get("accountability_id"),
            "required_gap_texts": volume.get("gaps"),
            "risks": volume.get("risks"),
            "contracts": volume.get("contracts"),
        }
        for field, value in expected.items():
            if binding.get(field) != value:
                raise GeneratedDocumentationError(f"{ref}.{field} drift")

    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list) or len(artifacts) != len(RENDERERS):
        raise GeneratedDocumentationError("generated artifact coverage drift")
    outputs: set[str] = set()
    ids: set[str] = set()
    for item in artifacts:
        if not isinstance(item, dict):
            raise GeneratedDocumentationError("generated artifact must be an object")
        artifact_id = item.get("artifact_id")
        output = _path(item.get("output"))
        if not output.startswith("docs/generated/"):
            raise GeneratedDocumentationError("generated output escapes docs/generated")
        if artifact_id in ids or output in outputs:
            raise GeneratedDocumentationError("duplicate generated artifact identity/output")
        ids.add(artifact_id)
        outputs.add(output)
        if output not in RENDERERS:
            raise GeneratedDocumentationError(f"unknown generated output: {output}")
        if item.get("generator") != "scripts/generate_p2_docs.py":
            raise GeneratedDocumentationError(f"{artifact_id} generator drift")
        if item.get("generator_version") != "0.1.0":
            raise GeneratedDocumentationError(f"{artifact_id} generator version drift")
        sources = item.get("sources")
        if not isinstance(sources, list) or not sources:
            raise GeneratedDocumentationError(f"{artifact_id} sources missing")
        for source in sources:
            relative = _path(source)
            if not (root / relative).is_file():
                raise GeneratedDocumentationError(
                    f"{artifact_id} source missing: {relative}"
                )
    if outputs != set(RENDERERS):
        raise GeneratedDocumentationError("generated output registry drift")
    return manifest


def render_all(root: Path = ROOT) -> dict[str, str]:
    root = root.resolve()
    validate_manifest(root)
    return {
        output: renderer(root)
        for output, renderer in sorted(RENDERERS.items())
    }


def check(root: Path = ROOT) -> dict[str, Any]:
    root = root.resolve()
    rendered = render_all(root)
    drift: list[str] = []
    for output, expected in rendered.items():
        path = root / output
        if not path.is_file():
            drift.append(f"{output}: missing")
            continue
        actual = path.read_text(encoding="utf-8")
        if actual != expected:
            drift.append(f"{output}: stale or hand-edited")
    if drift:
        raise GeneratedDocumentationError(
            "generated documentation drift: " + "; ".join(drift)
        )
    return {"status": "clean", "artifact_count": len(rendered)}


def write(root: Path = ROOT) -> dict[str, Any]:
    root = root.resolve()
    rendered = render_all(root)
    for output, content in rendered.items():
        path = root / output
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return {"status": "written", "artifact_count": len(rendered)}


def main() -> int:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--check", action="store_true")
    group.add_argument("--write", action="store_true")
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        result = check(Path(args.repo_root)) if args.check else write(Path(args.repo_root))
    except GeneratedDocumentationError as exc:
        print(f"generated documentation: FAIL: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True) if args.json else result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
