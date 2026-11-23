#!/usr/bin/env python3
"""Export, lint and drift-check the engine HTTP API OpenAPI contract.

The contract is generated from the code that actually serves traffic,
``skeleton.api.server.create_app()``, so the published document can never
describe routes that are not mounted. Generation pins the surface-toggle
environment to product defaults, which makes the output deterministic.

Usage::

    python scripts/export_openapi.py            # rewrite docs/api/openapi.v1.json
    python scripts/export_openapi.py --check    # exit 1 on drift or lint errors
    python scripts/export_openapi.py --lint     # lint the live spec only
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = ROOT / "docs" / "api" / "openapi.v1.json"
HTTP_METHODS = frozenset({"get", "put", "post", "delete", "options", "head", "patch", "trace"})
# Surface toggles that change which routers are mounted; pinned to defaults.
PINNED_UNSET = ("SKELETON_OMNIFABRIC_API", "SKELETON_PUBLIC_DEV_SURFACES")
_PATH_PARAM = re.compile(r"\{([^}:]+)(?::[^}]*)?\}")


def generate() -> dict[str, Any]:
    """Build the live application and return its OpenAPI document."""
    saved = {name: os.environ.pop(name, None) for name in PINNED_UNSET}
    try:
        for entry in (str(ROOT), str(ROOT / "backend")):
            if entry not in sys.path:
                sys.path.insert(0, entry)
        from skeleton.api.server import create_app

        spec = create_app().openapi()
    finally:
        for name, value in saved.items():
            if value is not None:
                os.environ[name] = value
    return json.loads(json.dumps(spec, sort_keys=True, default=str))


def render(spec: Mapping[str, Any]) -> str:
    return json.dumps(spec, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def operations(spec: Mapping[str, Any]) -> Iterator[tuple[str, str, Mapping[str, Any]]]:
    for path, item in sorted((spec.get("paths") or {}).items()):
        if not isinstance(item, Mapping):
            continue
        for method, operation in sorted(item.items()):
            if method in HTTP_METHODS and isinstance(operation, Mapping):
                yield method.upper(), path, operation


def lint(spec: Mapping[str, Any]) -> list[str]:
    """Structural rules every published operation must satisfy."""
    problems: list[str] = []
    version = str(spec.get("openapi", ""))
    if not version.startswith("3.1"):
        problems.append(f"openapi version must be 3.1.x, got {version!r}")
    info = spec.get("info") or {}
    if not info.get("title") or not info.get("version"):
        problems.append("info.title and info.version are required")
    seen: dict[str, str] = {}
    for method, path, operation in operations(spec):
        where = f"{method} {path}"
        op_id = operation.get("operationId")
        if not isinstance(op_id, str) or not op_id:
            problems.append(f"{where}: missing operationId")
        elif op_id in seen:
            problems.append(f"{where}: duplicate operationId {op_id!r} (also {seen[op_id]})")
        else:
            seen[op_id] = where
        responses = operation.get("responses")
        if not isinstance(responses, Mapping) or not responses:
            problems.append(f"{where}: no responses declared")
        declared = {
            p.get("name") for p in operation.get("parameters") or []
            if isinstance(p, Mapping) and p.get("in") == "path"
        }
        for name in _PATH_PARAM.findall(path):
            if name not in declared:
                problems.append(f"{where}: path parameter {name!r} is not declared")
    return problems


def diff_summary(old: Mapping[str, Any], new: Mapping[str, Any]) -> list[str]:
    before = {(m, p) for m, p, _ in operations(old)}
    after = {(m, p) for m, p, _ in operations(new)}
    lines = [f"+ {m} {p}" for m, p in sorted(after - before)]
    lines += [f"- {m} {p}" for m, p in sorted(before - after)]
    old_ops = {(m, p): o for m, p, o in operations(old)}
    for m, p, o in operations(new):
        if (m, p) in old_ops and old_ops[(m, p)] != o:
            lines.append(f"~ {m} {p}")
    if old.get("components") != new.get("components"):
        lines.append("~ components")
    return lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="fail on snapshot drift or lint errors")
    mode.add_argument("--lint", action="store_true", help="lint the live spec without touching the snapshot")
    parser.add_argument("--output", type=Path, default=SNAPSHOT)
    args = parser.parse_args(argv)

    spec = generate()
    problems = lint(spec)
    for problem in problems:
        print(f"openapi lint: {problem}", file=sys.stderr)
    count = sum(1 for _ in operations(spec))
    if args.lint:
        print(f"openapi: {len(spec.get('paths') or {})} paths, {count} operations, {len(problems)} problems")
        return 1 if problems else 0
    if args.check:
        if not args.output.is_file():
            print(f"openapi: snapshot {args.output} is missing; run scripts/export_openapi.py", file=sys.stderr)
            return 1
        committed = json.loads(args.output.read_text(encoding="utf-8"))
        changes = diff_summary(committed, spec)
        if render(committed) != render(spec):
            print("openapi: committed snapshot drifted from the mounted routes:", file=sys.stderr)
            for line in changes[:200] or ["(metadata or schema ordering change)"]:
                print("  " + line, file=sys.stderr)
            print("run: python scripts/export_openapi.py", file=sys.stderr)
            return 1
        print(f"openapi: snapshot matches code ({count} operations)")
        return 1 if problems else 0
    if problems:
        return 1
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(render(spec), encoding="utf-8")
    print(f"openapi: wrote {args.output.relative_to(ROOT) if args.output.is_relative_to(ROOT) else args.output} "
          f"({len(spec.get('paths') or {})} paths, {count} operations)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
