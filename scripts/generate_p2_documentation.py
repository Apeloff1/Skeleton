#!/usr/bin/env python3
"""Deterministically generate P2 documentation from machine authority."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = Path("machine/generated_documentation.json")


class DocumentationGenerationError(RuntimeError):
    pass


def _load_json(root: Path, relative: str | Path) -> dict[str, Any]:
    path = root / Path(relative)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise DocumentationGenerationError(f"missing source: {relative}") from exc
    except json.JSONDecodeError as exc:
        raise DocumentationGenerationError(f"invalid JSON in {relative}: {exc}") from exc
    if not isinstance(payload, dict):
        raise DocumentationGenerationError(f"{relative} must contain a JSON object")
    return payload


def _repo_path(value: object) -> str:
    if not isinstance(value, str) or not value or "\x00" in value or "\\" in value:
        raise DocumentationGenerationError(f"invalid repository path: {value!r}")
    pure = PurePosixPath(value)
    if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
        raise DocumentationGenerationError(f"invalid repository path: {value!r}")
    if pure.as_posix() != value:
        raise DocumentationGenerationError(f"non-canonical repository path: {value!r}")
    return value


def _git_blob_sha(path: Path) -> str:
    data = path.read_bytes()
    return hashlib.sha1(f"blob {len(data)}\0".encode("ascii") + data).hexdigest()


def _source_rows(root: Path, sources: list[str]) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    for relative in sorted(sources):
        normalized = _repo_path(relative)
        target = root / normalized
        if target.is_symlink():
            raise DocumentationGenerationError(
                f"generated-doc source must not be a symlink: {normalized}"
            )
        if not target.is_file():
            raise DocumentationGenerationError(f"generated-doc source missing: {normalized}")
        rows.append((normalized, _git_blob_sha(target)))
    return rows


def render_p2_machine_authority(root: Path, entry: dict[str, Any]) -> str:
    sources = entry.get("sources")
    if not isinstance(sources, list) or not sources:
        raise DocumentationGenerationError("generated document requires sources")
    source_rows = _source_rows(root, sources)

    master = _load_json(root, "machine/ai_master_plan.json")
    execution = _load_json(root, "machine/ai_p2_execution_map.json")
    backlog = _load_json(root, "machine/ai_p2_task_backlog.json")

    volumes = {
        item["key"]: item
        for item in master.get("volumes", [])
        if isinstance(item, dict) and isinstance(item.get("key"), str)
    }
    tranche = execution.get("first_tranche")
    if not isinstance(tranche, dict):
        raise DocumentationGenerationError("P2 execution map lacks first_tranche")
    scheduled = tranche.get("scheduled_volume_refs")
    queued = tranche.get("queued_volume_refs")
    if not isinstance(scheduled, list) or not isinstance(queued, list):
        raise DocumentationGenerationError("P2 scheduled/queued volume refs must be lists")

    tasks = backlog.get("tasks")
    if not isinstance(tasks, list):
        raise DocumentationGenerationError("P2 task backlog tasks must be a list")

    lines = [
        "# P2 Machine Authority Reference",
        "",
        "<!-- GENERATED FILE: DO NOT EDIT BY HAND -->",
        "<!-- generator: scripts/generate_p2_documentation.py -->",
        "<!-- manifest: machine/generated_documentation.json -->",
        "",
        "This document is a deterministic projection of machine authority. It has no completion, maturity, runtime, or sign-off authority.",
        "",
        "## Source identities",
        "",
        "| Source | Git blob SHA-1 |",
        "| --- | --- |",
    ]
    lines.extend(f"| `{path}` | `{digest}` |" for path, digest in source_rows)

    lines.extend([
        "",
        "## P2 execution boundary",
        "",
        f"- Source scope: **{execution.get('source_scope', {}).get('expected_volume_count', 'unknown')}** deferred masterplan volumes.",
        f"- First tranche scheduled: **{len(scheduled)}** volumes.",
        f"- Explicitly queued: **{len(queued)}** volumes.",
        f"- Execution-map state: `{execution.get('status', 'unknown')}`.",
        "",
        "## Task dependency/status projection",
        "",
        "| Task | Lane | Status | Depends on |",
        "| --- | --- | --- | --- |",
    ])
    for task in sorted(
        (item for item in tasks if isinstance(item, dict)),
        key=lambda item: str(item.get("task_id", "")),
    ):
        task_id = str(task.get("task_id", ""))
        lane = str(task.get("lane_id", ""))
        status = str(task.get("status", ""))
        deps = task.get("depends_on", [])
        if not isinstance(deps, list):
            raise DocumentationGenerationError(f"{task_id} depends_on must be a list")
        dep_text = ", ".join(f"`{dep}`" for dep in deps) if deps else "—"
        lines.append(f"| `{task_id}` | `{lane}` | `{status}` | {dep_text} |")

    lines.extend([
        "",
        "## Scheduled masterplan volumes",
        "",
        "| Volume | Title | Implementation status |",
        "| --- | --- | --- |",
    ])
    for ref in scheduled:
        volume = volumes.get(ref)
        if not isinstance(volume, dict):
            raise DocumentationGenerationError(f"scheduled volume missing from masterplan: {ref}")
        title = str(volume.get("title", "")).replace("|", "\\|")
        status = str(volume.get("implementation_status", ""))
        lines.append(f"| `{ref}` | {title} | `{status}` |")

    lines.extend([
        "",
        "## Authority boundary",
        "",
        "Generated documentation is reviewable evidence of synchronization only. Canonical machine manifests, runtime behavior, exact-head test evidence, and signed accountability remain authoritative.",
        "",
    ])
    return "\n".join(lines)


def render_document(root: Path, entry: dict[str, Any]) -> str:
    renderer = entry.get("renderer")
    if renderer == "p2_machine_authority":
        return render_p2_machine_authority(root, entry)
    raise DocumentationGenerationError(f"unsupported documentation renderer: {renderer!r}")


def generate(root: Path = ROOT, *, check: bool = False) -> dict[str, Any]:
    root = root.resolve()
    manifest = _load_json(root, MANIFEST)
    if manifest.get("status") not in {"active", "active_stacked"}:
        raise DocumentationGenerationError("generated documentation manifest must be active")
    entries = manifest.get("generated_files")
    if not isinstance(entries, list) or not entries:
        raise DocumentationGenerationError("generated_files must be a non-empty list")

    changed: list[str] = []
    outputs: list[dict[str, str]] = []
    for entry in entries:
        if not isinstance(entry, dict):
            raise DocumentationGenerationError("generated file entry must be an object")
        output = _repo_path(entry.get("output"))
        rendered = render_document(root, entry)
        target = root / output
        if target.is_symlink():
            raise DocumentationGenerationError(
                f"generated output must not be a symlink: {output}"
            )
        existing = target.read_text(encoding="utf-8") if target.is_file() else None
        if existing != rendered:
            changed.append(output)
            if not check:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(rendered, encoding="utf-8")
        outputs.append({
            "output": output,
            "sha256": hashlib.sha256(rendered.encode("utf-8")).hexdigest(),
        })

    if check and changed:
        raise DocumentationGenerationError(
            "generated documentation drift: " + ", ".join(sorted(changed))
        )
    return {"status": "clean" if not changed else "updated", "outputs": outputs}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        result = generate(Path(args.repo_root), check=args.check)
    except DocumentationGenerationError as exc:
        print(f"P2 documentation generation: FAIL: {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(result, sort_keys=True))
    else:
        print(f"P2 documentation generation: {result['status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
