#!/usr/bin/env python3
"""Inventory stub and truncation evidence across all tracked source paths.

Emits complete JSONL findings and a summary. Categories are evidence-based
triage, NOT proof that any feature or model is implemented or broken.
Reads immutable Git blobs; works even when Windows cannot check out every path.
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

SOURCE_EXTENSIONS = (".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs")
TEXT_EXTENSIONS = SOURCE_EXTENSIONS + (".json", ".md", ".rst", ".toml", ".yml", ".yaml")
TRUNCATION = re.compile(r"\[truncated\]|<truncated>|(?:content|output)\s+truncated", re.I)
TODO = re.compile(r"\b(?:TODO|FIXME|XXX)\b", re.I)
TS_UNIMPLEMENTED = re.compile(
    r"\bthrow\s+new\s+(?:Error|TypeError)\s*\(\s*['\"](?:not implemented|unimplemented|todo)\b", re.I
)
TS_PLACEHOLDER = re.compile(r"^\s*(?:\.\.\.|throw\s+['\"]TODO['\"])\s*;?\s*$", re.M)
MAX_SOURCE_BYTES = 4 * 1024 * 1024


def owner(path: str) -> str:
    if path.startswith("satellites/branch-snapshots/"):
        return "historical_snapshot"
    if path.startswith(("tests/", "skeleton/testing/", "backend/tests/")) or "/__tests__/" in path or path.endswith((".test.ts", ".test.tsx", ".spec.ts", ".spec.tsx")):
        return "test_or_fixture"
    if path.endswith((".md", ".rst")) or path.startswith("docs/"):
        return "documentation"
    if path.startswith(("scripts/", ".github/", "packaging/")):
        return "tooling"
    if path.startswith(("frontend/", "backend/", "skeleton/", "core/", "apps/", "volume_forge/")):
        return "production_candidate"
    return "other"


def severity(category: str, kind: str) -> str:
    if category in {"historical_snapshot", "documentation", "test_or_fixture"}:
        return "context_only"
    if kind in {"python_syntax_error", "raise_not_implemented", "throw_not_implemented"}:
        return "implementation_review"
    if kind in {"truncation_marker", "empty_statement"}:
        return "manual_review"
    return "maintenance_note"


def markers(path: str, text: str) -> list[tuple[int, str]]:
    found: list[tuple[int, str]] = []
    def locate(match: re.Match[str], kind: str) -> None:
        found.append((text.count("\n", 0, match.start()) + 1, kind))
    for regex, kind in ((TRUNCATION, "truncation_marker"), (TODO, "todo_note")):
        for match in regex.finditer(text):
            locate(match, kind)
    if path.endswith(".py"):
        try:
            tree = ast.parse(text, filename=path)
        except SyntaxError as exc:
            found.append((exc.lineno or 1, "python_syntax_error"))
        else:
            for node in ast.walk(tree):
                if isinstance(node, ast.Pass):
                    found.append((node.lineno, "empty_statement"))
                elif isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and node.value.value is Ellipsis:
                    found.append((node.lineno, "empty_statement"))
                elif isinstance(node, ast.Raise) and node.exc is not None:
                    expr = node.exc.func if isinstance(node.exc, ast.Call) else node.exc
                    if isinstance(expr, ast.Name) and expr.id == "NotImplementedError":
                        found.append((node.lineno, "raise_not_implemented"))
    elif path.endswith((".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs")):
        for regex, kind in ((TS_UNIMPLEMENTED, "throw_not_implemented"), (TS_PLACEHOLDER, "empty_statement")):
            for match in regex.finditer(text):
                locate(match, kind)
    return sorted(set(found))


def tracked_blobs(ref: str):
    process = subprocess.run(
        ["git", "ls-tree", "-r", "-l", "-z", ref],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True
    )
    for record in process.stdout.split(b"\0"):
        if not record:
            continue
        header, name = record.split(b"\t", 1)
        fields = header.decode("ascii").split()
        if len(fields) != 4 or fields[1] != "blob":
            continue
        yield fields[0], fields[2], int(fields[3]), name.decode("utf-8", "surrogateescape")


def classify(ref: str, output: Path, summary_file: Path, max_bytes: int = MAX_SOURCE_BYTES) -> dict:
    if max_bytes < 1024:
        raise ValueError("max-bytes must be >= 1024")
    tracked = sorted(tracked_blobs(ref), key=lambda e: e[3])
    eligible = [(mode, sha, size, path) for mode, sha, size, path in tracked if path.endswith(TEXT_EXTENSIONS)]
    counters: Counter[str] = Counter()
    categories: Counter[str] = Counter()
    # Cache small marker lists, never entire source blobs: historical snapshots
    # repeat large files and unbounded byte caching could exhaust the runner.
    seen_markers: dict[tuple[str, str], tuple[str, list[tuple[int, str]]]] = {}
    output.parent.mkdir(parents=True, exist_ok=True)
    summary_file.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as stream:
        worker = subprocess.Popen(
            ["git", "cat-file", "--batch"], stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        assert worker.stdin and worker.stdout
        try:
            for mode, sha, size, path in eligible:
                counters["tracked_text_paths"] += 1
                if mode == "120000":
                    counters["symlinks_not_read"] += 1
                    continue
                if size > max_bytes:
                    counters["oversized_sources_not_read"] += 1
                    categories[owner(path)] += 1
                    stream.write(json.dumps({
                        "path": path, "blob": sha, "kind": "source_too_large_to_inspect",
                        "bytes": size, "category": owner(path), "severity": "manual_review"
                    }, ensure_ascii=False) + "\n")
                    continue
                cache_key = (sha, Path(path).suffix.lower())
                if cache_key not in seen_markers:
                    worker.stdin.write((sha + "\n").encode("ascii"))
                    worker.stdin.flush()
                    header = worker.stdout.readline().decode("ascii").split()
                    if len(header) != 3 or header[0] != sha or header[1] != "blob":
                        raise ValueError("Git blob header mismatch")
                    length = int(header[2])
                    blob = worker.stdout.read(length)
                    if worker.stdout.read(1) != b"\n":
                        raise ValueError("Git blob terminator missing")
                    if length != size:
                        raise ValueError("Git tree reported inconsistent blob size")
                    if b"\0" in blob:
                        seen_markers[cache_key] = ("binary", [])
                    else:
                        try:
                            decoded = blob.decode("utf-8", errors="strict")
                        except UnicodeDecodeError:
                            seen_markers[cache_key] = ("non_utf8", [])
                        else:
                            seen_markers[cache_key] = ("ok", markers(path, decoded))
                status, found = seen_markers[cache_key]
                counters["inspected_text_paths"] += 1
                if status == "binary":
                    counters["binary_marked_text"] += 1
                    continue
                if status == "non_utf8":
                    counters["non_utf8_sources"] += 1
                    continue
                category = owner(path)
                for line, kind in found:
                    item = {
                        "path": path, "blob": sha, "line": line,
                        "kind": kind, "category": category,
                        "severity": severity(category, kind),
                    }
                    stream.write(json.dumps(item, ensure_ascii=False) + "\n")
                    counters["findings_total"] += 1
                    counters["kind:" + kind] += 1
                    counters["severity:" + item["severity"]] += 1
                    categories[category] += 1
        finally:
            worker.stdin.close()
            worker.stdout.close()
            worker.wait()
            if worker.returncode:
                raise RuntimeError(f"Git cat-file failed: {worker.returncode}")
    summary = {
        "schema_version": "skeleton.stub_truncation_classification.v1",
        "git_ref": ref,
        "tracked_paths": len(tracked),
        "max_source_bytes": max_bytes,
        "counts": dict(sorted(counters.items())),
        "finding_categories": dict(sorted(categories.items())),
        "inventory_complete": not any(counters[k] for k in (
            "oversized_sources_not_read", "symlinks_not_read", "binary_marked_text", "non_utf8_sources"
        )),
        "qualification": "static triage only: no runtime execution or human-reviewed stub disposition is implied",
    }
    summary_file.write_text(json.dumps(summary, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ref", default="HEAD")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--max-bytes", type=int, default=MAX_SOURCE_BYTES)
    args = parser.parse_args(argv)
    try:
        summary = classify(args.ref, args.output, args.summary, args.max_bytes)
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"stub-classifier: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(summary, indent=2, sort_keys=True))
    # Findings need review. Do not block unrelated PRs on raw TODO markers.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
