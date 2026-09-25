#!/usr/bin/env python3
"""Validate pinned OpenAI OSS snapshots and clean-room runtime separation."""

from __future__ import annotations

import ast
import hashlib
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "machine" / "openai_oss_assimilation.json"
FULL_SHA = re.compile(r"^[0-9a-f]{40}$")
ALLOWED_LICENSES = {"MIT", "Apache-2.0", "CC0-1.0"}


def _git_blob_sha(path: Path) -> str:
    data = path.read_bytes()
    header = f"blob {len(data)}\0".encode("ascii")
    return hashlib.sha1(header + data).hexdigest()


def validate() -> list[str]:
    errors: list[str] = []
    if not MANIFEST.is_file():
        return ["missing machine/openai_oss_assimilation.json"]
    try:
        data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return [f"cannot parse OpenAI OSS manifest: {exc}"]

    if data.get("schema_version") != "openai-oss-assimilation/v1":
        errors.append("OpenAI OSS manifest schema drifted")
    sources = data.get("sources")
    if not isinstance(sources, dict) or len(sources) != 8:
        errors.append("OpenAI OSS manifest must contain exactly eight governed sources")
        sources = {}

    for source_id, source in sources.items():
        if not isinstance(source, dict):
            errors.append(f"{source_id}: source entry must be an object")
            continue
        repository = source.get("repository")
        if not isinstance(repository, str) or not repository.startswith("openai/"):
            errors.append(f"{source_id}: repository must be openai/*")
        commit = str(source.get("commit_sha", ""))
        if not FULL_SHA.fullmatch(commit):
            errors.append(f"{source_id}: commit_sha must be a full lowercase SHA")
        if source.get("license_spdx") not in ALLOWED_LICENSES:
            errors.append(f"{source_id}: unsupported license")
        root = source.get("snapshot_root")
        if not isinstance(root, str) or not root.startswith(
            "skeleton/ai/research/external/OpenAI/"
        ):
            errors.append(f"{source_id}: snapshot_root escapes research quarantine")
            continue
        license_seen = False
        files = source.get("files")
        if not isinstance(files, list) or not files:
            errors.append(f"{source_id}: source file list is empty")
            continue
        for item in files:
            if not isinstance(item, dict):
                errors.append(f"{source_id}: file entry must be an object")
                continue
            destination = item.get("destination_path")
            blob = str(item.get("upstream_blob_sha", ""))
            source_path = item.get("source_path")
            if not isinstance(destination, str) or not destination.startswith(root + "/"):
                errors.append(f"{source_id}: destination escapes snapshot root")
                continue
            path = ROOT / destination
            if not path.is_file():
                errors.append(f"{source_id}: missing snapshot {destination}")
                continue
            if not FULL_SHA.fullmatch(blob):
                errors.append(f"{source_id}: invalid upstream blob SHA for {source_path}")
            elif _git_blob_sha(path) != blob:
                errors.append(f"{source_id}: byte drift from upstream blob: {source_path}")
            if destination.endswith("LICENSE.upstream.txt"):
                license_seen = True
            elif not destination.endswith(".txt"):
                errors.append(f"{source_id}: copied source must remain non-executable .txt")
        if not license_seen:
            errors.append(f"{source_id}: adjacent upstream license snapshot missing")

    adapters = data.get("executable_adapters")
    if not isinstance(adapters, list) or len(adapters) < 10:
        errors.append("OpenAI OSS executable adapter inventory is incomplete")
        adapters = []
    for relative in adapters:
        path = ROOT / relative
        if not path.is_file():
            errors.append(f"missing OpenAI OSS adapter: {relative}")
            continue
        try:
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source)
        except (OSError, UnicodeDecodeError, SyntaxError) as exc:
            errors.append(f"invalid adapter Python {relative}: {exc}")
            continue
        if "skeleton.ai.research.external" in source:
            errors.append(f"adapter illegally imports research quarantine: {relative}")
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                rendered = ast.unparse(node)
                if "research.external.OpenAI" in rendered:
                    errors.append(
                        f"adapter imports upstream snapshot directly: {relative}"
                    )

    promotion = data.get("promotion_rule")
    if not isinstance(promotion, str) or "No upstream research snapshot" not in promotion:
        errors.append("OpenAI OSS promotion boundary is missing")

    return errors


if __name__ == "__main__":
    failures = validate()
    if failures:
        for failure in failures:
            print(f"ERROR: {failure}")
        raise SystemExit(1)
    print("OpenAI OSS assimilation: OK")
