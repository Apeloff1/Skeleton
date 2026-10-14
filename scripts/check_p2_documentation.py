#!/usr/bin/env python3
"""Fail-closed validation for the P2 generated-documentation authority."""

from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path, PurePosixPath
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = Path("machine/generated_documentation.json")
TRACE_REFS = ("VOL-089", "VOL-090")


class DocumentationControlError(RuntimeError):
    pass


def _load(root: Path, relative: str | Path) -> dict[str, Any]:
    path = root / Path(relative)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise DocumentationControlError(f"missing required file: {relative}") from exc
    except json.JSONDecodeError as exc:
        raise DocumentationControlError(f"invalid JSON in {relative}: {exc}") from exc
    if not isinstance(payload, dict):
        raise DocumentationControlError(f"{relative} must contain an object")
    return payload


def _repo_path(value: object) -> str:
    if not isinstance(value, str) or not value or "\x00" in value or "\\" in value:
        raise DocumentationControlError(f"invalid repository path: {value!r}")
    pure = PurePosixPath(value)
    if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
        raise DocumentationControlError(f"invalid repository path: {value!r}")
    if pure.as_posix() != value:
        raise DocumentationControlError(f"non-canonical repository path: {value!r}")
    return value


def _load_generator(root: Path):
    path = root / "scripts/generate_p2_documentation.py"
    spec = importlib.util.spec_from_file_location("p2_doc_generator", path)
    if spec is None or spec.loader is None:
        raise DocumentationControlError("cannot load documentation generator")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def validate(root: Path = ROOT) -> dict[str, Any]:
    root = root.resolve()
    manifest = _load(root, MANIFEST)
    master = _load(root, "machine/ai_master_plan.json")
    if manifest.get("status") not in {"active", "active_stacked"}:
        raise DocumentationControlError("documentation manifest must be active")
    if manifest.get("task_ref") != "P2-DOC-01":
        raise DocumentationControlError("documentation task_ref drift")
    if manifest.get("parent_lane") != "P2-TRACE-01":
        raise DocumentationControlError("documentation parent lane drift")

    master_by_ref = {
        item["key"]: item
        for item in master.get("volumes", [])
        if isinstance(item, dict) and isinstance(item.get("key"), str)
    }
    bindings = manifest.get("masterplan_bindings")
    if not isinstance(bindings, list):
        raise DocumentationControlError("masterplan_bindings must be a list")
    by_ref = {
        item.get("volume_ref"): item
        for item in bindings
        if isinstance(item, dict)
    }
    if set(by_ref) != set(TRACE_REFS) or len(by_ref) != len(bindings):
        raise DocumentationControlError("documentation masterplan binding coverage drift")
    for ref in TRACE_REFS:
        volume = master_by_ref.get(ref)
        binding = by_ref[ref]
        if not isinstance(volume, dict):
            raise DocumentationControlError(f"masterplan missing {ref}")
        for field, expected in (
            ("title", volume.get("title")),
            ("accountability_id", volume.get("accountability_id")),
            ("required_gap_texts", volume.get("gaps", [])),
        ):
            if binding.get(field) != expected:
                raise DocumentationControlError(f"{ref}.{field} drift")

    policy = manifest.get("boundary_policy")
    if not isinstance(policy, dict):
        raise DocumentationControlError("boundary_policy must be an object")
    generated_root = _repo_path(policy.get("generated_root"))
    if generated_root != "docs/generated":
        raise DocumentationControlError("generated root must remain docs/generated")
    manual_roots_raw = policy.get("manual_roots")
    if (
        not isinstance(manual_roots_raw, list)
        or not manual_roots_raw
        or len(manual_roots_raw) != len(set(manual_roots_raw))
    ):
        raise DocumentationControlError("manual_roots must be unique/non-empty")
    manual_roots = [_repo_path(item) for item in manual_roots_raw]
    for manual_root in manual_roots:
        if (
            manual_root == generated_root
            or manual_root.startswith(generated_root + "/")
            or generated_root.startswith(manual_root.rstrip("/") + "/")
        ):
            raise DocumentationControlError(
                f"manual/generated documentation roots overlap: {manual_root}"
            )
    if policy.get("derived_authority") is not False:
        raise DocumentationControlError("generated docs may not claim authority")
    if policy.get("clean_regeneration_required") is not True:
        raise DocumentationControlError("clean regeneration must remain required")
    if policy.get("deterministic_bytes_required") is not True:
        raise DocumentationControlError("deterministic bytes must remain required")
    if policy.get("undeclared_generated_file_policy") != "deny":
        raise DocumentationControlError("undeclared generated files must fail closed")

    entries = manifest.get("generated_files")
    if not isinstance(entries, list) or not entries:
        raise DocumentationControlError("generated_files must be non-empty")
    outputs: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            raise DocumentationControlError("generated file entry must be an object")
        output = _repo_path(entry.get("output"))
        if output in outputs:
            raise DocumentationControlError(f"duplicate generated output: {output}")
        outputs.add(output)
        if not (output == generated_root or output.startswith(generated_root + "/")):
            raise DocumentationControlError(f"generated output escapes generated root: {output}")
        if entry.get("editable") is not False:
            raise DocumentationControlError(f"generated output must be non-editable: {output}")
        if entry.get("generator") != "scripts/generate_p2_documentation.py":
            raise DocumentationControlError(f"unexpected generator for {output}")
        sources = entry.get("sources")
        if not isinstance(sources, list) or not sources or len(sources) != len(set(sources)):
            raise DocumentationControlError(f"{output} sources must be unique/non-empty")
        for source in sources:
            normalized = _repo_path(source)
            target = root / normalized
            if target.is_symlink():
                raise DocumentationControlError(
                    f"{output} source must not be a symlink: {normalized}"
                )
            if not target.is_file():
                raise DocumentationControlError(f"{output} source missing: {normalized}")

    generated_dir = root / generated_root
    discovered = {
        path.relative_to(root).as_posix()
        for path in generated_dir.rglob("*")
        if path.is_file() and path.name != "README.md"
    } if generated_dir.is_dir() else set()
    if discovered != outputs:
        raise DocumentationControlError(
            f"generated-document inventory drift: declared={sorted(outputs)} discovered={sorted(discovered)}"
        )

    generator = _load_generator(root)
    try:
        result = generator.generate(root, check=True)
    except Exception as exc:
        raise DocumentationControlError(f"regeneration cleanliness failed: {exc}") from exc
    if result.get("status") != "clean":
        raise DocumentationControlError("generated documentation is not clean")

    for output in sorted(outputs):
        target = root / output
        if target.is_symlink():
            raise DocumentationControlError(
                f"{output} generated output must not be a symlink"
            )
        text = target.read_text(encoding="utf-8")
        if "<!-- GENERATED FILE: DO NOT EDIT BY HAND -->" not in text:
            raise DocumentationControlError(f"{output} lacks generated-file marker")
        if "has no completion, maturity, runtime, or sign-off authority" not in text:
            raise DocumentationControlError(f"{output} lacks authority boundary")

    return {
        "status":"valid",
        "masterplan_binding_count":len(TRACE_REFS),
        "generated_file_count":len(outputs),
        "outputs":sorted(outputs),
    }


def main() -> int:
    parser=argparse.ArgumentParser()
    parser.add_argument("--repo-root",default=".")
    parser.add_argument("--json",action="store_true")
    args=parser.parse_args()
    try:
        result=validate(Path(args.repo_root))
    except DocumentationControlError as exc:
        print(f"P2 documentation control: FAIL: {exc}",file=sys.stderr)
        return 1
    print(json.dumps(result,sort_keys=True) if args.json else result)
    return 0


if __name__=="__main__":
    raise SystemExit(main())
