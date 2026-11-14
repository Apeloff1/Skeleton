#!/usr/bin/env python3
"""Verify source-object pins for the integrated AI tree; repair only on request.

This is repository bookkeeping, not an AI-tree parity exception, a source
replacement, or a release approval. The 28 integrated source pins remain
checked independently by tests/test_repository_integration.py.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tempfile
from typing import Callable, Mapping

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = Path("machine/ai_file_tree.json")
_SHA = re.compile(r"[0-9a-f]{40}\Z")
INTEGRATED_SOURCE_PIN_IDS = frozenset({
    "AIFT-APPLICATION", "AIFT-DISTRIBUTED", "AIFT-RESEARCH",
    "AIFT-KNOWLEDGE", "AIFT-PROVENANCE", "AIFT-TOOLS",
    "AIFT-SIMULATION", "AIFT-GAME", "AIFT-SCHOOL",
    "AIFT-LEARNING", "AIFT-KERNEL", "AIFT-SWARM",
    "AIFT-NETWORK", "AIFT-ORGANISM", "AIFT-AUTOMATION",
    "AIFT-GALAXY", "AIFT-CORTEX", "AIFT-AGENTS",
    "AIFT-PERSISTENCE", "AIFT-RETRIEVAL", "AIFT-RELIABILITY",
    "AIFT-VAULT", "AIFT-MEMORY", "AIFT-JEEVES",
    "AIFT-FOUNDATION", "AIFT-RESILIENCE",
    "AIFT-OBSERVABILITY", "AIFT-ARCHITECTURE-LEGACY",
})


class SourcePinError(ValueError):
    """Ambiguous metadata, missing Git source or unsafe repair."""


@dataclass(frozen=True)
class PinDrift:
    mapping_id: str
    source: str
    declared: str
    actual: str


def _source_path(raw: object) -> str:
    if not isinstance(raw, str) or not raw.startswith("skeleton/"):
        raise SourcePinError("source pin must name a canonical Skeleton path")
    if len(raw) > 512 or ":" in raw or "\\" in raw or "\x00" in raw:
        raise SourcePinError("invalid source pin path")
    parts = raw.split("/")
    if any(not part or part in (".", "..", ".git") for part in parts):
        raise SourcePinError("source pin path is not canonical")
    return raw


def compare_pins(
    manifest: Mapping[str, object],
    resolve: Callable[[str], str],
    *,
    ids: frozenset[str] = INTEGRATED_SOURCE_PIN_IDS,
) -> list[PinDrift]:
    """Compare independent source objects; reject missing/duplicated pin IDs."""
    mappings = manifest.get("mappings")
    if not isinstance(mappings, list):
        raise SourcePinError("AI-tree mapping list is missing")
    selected: dict[str, dict[str, object]] = {}
    for item in mappings:
        if not isinstance(item, dict):
            raise SourcePinError("malformed AI-tree mapping")
        mapping_id = item.get("id")
        if mapping_id not in ids:
            continue
        if mapping_id in selected:
            raise SourcePinError("duplicate integrated source mapping: " + mapping_id)
        selected[mapping_id] = item
    missing = ids - selected.keys()
    if missing:
        raise SourcePinError("missing integrated source mappings: " + ", ".join(sorted(missing)))

    drift: list[PinDrift] = []
    for mapping_id in sorted(ids):
        item = selected[mapping_id]
        source = _source_path(item.get("source"))
        declared = item.get("source_git_object_sha")
        if not isinstance(declared, str) or not _SHA.fullmatch(declared):
            raise SourcePinError("invalid recorded source object: " + mapping_id)
        actual = resolve(source)
        if not isinstance(actual, str) or not _SHA.fullmatch(actual):
            raise SourcePinError("unresolved source Git object: " + mapping_id)
        if declared != actual:
            drift.append(PinDrift(mapping_id, source, declared, actual))
    return drift


def replace_pins(original: str, drifts: list[PinDrift]) -> str:
    """Preserve all non-pin manifest bytes, including ordering and comments.

    Refuse an ambiguous SHA occurrence rather than silently rewriting another
    source owner. The original is JSON, which has no comment syntax.
    """
    manifest = json.loads(original)
    mappings = manifest["mappings"]
    selected = {item["id"]: item for item in mappings if isinstance(item, dict)}
    revised = original
    for drift in drifts:
        item = selected.get(drift.mapping_id)
        if (not isinstance(item, dict) or item.get("source") != drift.source
                or item.get("source_git_object_sha") != drift.declared):
            raise SourcePinError("source pin changed since comparison")
        old = '"source_git_object_sha": "' + drift.declared + '"'
        new = '"source_git_object_sha": "' + drift.actual + '"'
        if revised.count(old) != 1:
            raise SourcePinError("ambiguous source pin rewrite: " + drift.mapping_id)
        revised = revised.replace(old, new, 1)
    reparsed = json.loads(revised)
    by_id = {item["id"]: item for item in reparsed["mappings"]}
    for drift in drifts:
        if by_id[drift.mapping_id]["source_git_object_sha"] != drift.actual:
            raise SourcePinError("source pin postcondition failed")
    return revised


def _git(root: Path, *args: str) -> str:
    try:
        result = subprocess.run(
            ["git", *args], cwd=root, capture_output=True, text=True,
            timeout=30, check=True,
        )
    except (OSError, subprocess.TimeoutExpired, subprocess.CalledProcessError) as exc:
        raise SourcePinError("Git index or source object unavailable") from exc
    result_text = result.stdout.strip()
    if not _SHA.fullmatch(result_text):
        raise SourcePinError("Git returned an invalid object identifier")
    return result_text


def _publish_manifest(path: Path, before: str, after: str) -> None:
    """Write an owner-controlled replacement atomically; never edit a symlink."""
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise SourcePinError("manifest must be a regular single-link file")
    if path.read_text(encoding="utf-8") != before:
        raise SourcePinError("manifest changed during source pin reconciliation")
    temporary: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", prefix=".ai-source-pins-",
            dir=path.parent, delete=False,
        ) as output:
            temporary = output.name
            output.write(after)
            output.flush()
            os.fsync(output.fileno())
            os.fchmod(output.fileno(), stat.S_IMODE(info.st_mode))
        if path.read_text(encoding="utf-8") != before:
            raise SourcePinError("manifest changed before publication")
        os.replace(temporary, path)
        temporary = None
        parent_fd = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(parent_fd)
        finally:
            os.close(parent_fd)
    finally:
        if temporary is not None:
            Path(temporary).unlink(missing_ok=True)


def main(argv: list[str] | None = None, *, root: Path = ROOT) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="read-only exact-index verification (default)")
    mode.add_argument("--write", action="store_true", help="explicitly repair only stale integrated source pins")
    args = parser.parse_args(argv)
    try:
        path = root / MANIFEST
        if path.is_symlink():
            raise SourcePinError("AI-tree manifest may not be a symlink")
        original = path.read_text(encoding="utf-8")
        manifest = json.loads(original)
        tree_before = _git(root, "write-tree")
        drifts = compare_pins(
            manifest,
            lambda source: _git(root, "rev-parse", "--verify", tree_before + ":" + source),
        )
        if not drifts:
            print("AI integration source pins: OK (28 independently resolved objects)")
            return 0
        for drift in drifts:
            print(
                f"{drift.mapping_id}: {drift.source} "
                f"recorded={drift.declared} current={drift.actual}",
                file=sys.stderr,
            )
        if not args.write:
            return 1
        updated = replace_pins(original, drifts)
        if _git(root, "write-tree") != tree_before:
            raise SourcePinError("Git index changed during source pin reconciliation")
        _publish_manifest(path, original, updated)
        print(f"Refreshed {len(drifts)} AI integration source pins; review and stage the manifest")
        return 0
    except (SourcePinError, OSError, UnicodeError, ValueError, TypeError) as exc:
        print(f"AI source pin reconciliation blocked: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
