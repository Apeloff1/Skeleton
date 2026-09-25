#!/usr/bin/env python3
"""Validate xAI/Grok OSS provenance, license disposition, and runtime isolation."""

from __future__ import annotations

import ast
import hashlib
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "machine" / "xai_grok_oss_assimilation.json"
FULL_SHA = re.compile(r"^[0-9a-f]{40}$")


def _git_blob_sha(path: Path) -> str:
    data = path.read_bytes()
    header = f"blob {len(data)}\0".encode("ascii")
    return hashlib.sha1(header + data).hexdigest()


def validate() -> list[str]:
    errors: list[str] = []
    if not MANIFEST.is_file():
        return ["missing machine/xai_grok_oss_assimilation.json"]
    try:
        data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return [f"cannot parse xAI OSS manifest: {exc}"]

    if data.get("schema_version") != "xai-grok-oss-assimilation/v1":
        errors.append("xAI OSS manifest schema drifted")

    sources = data.get("sources")
    if not isinstance(sources, dict) or set(sources) != {
        "grok-1",
        "grok-build",
        "grok-build-plugin-cc",
        "xai-sdk-python",
        "xai-proto",
    }:
        errors.append("xAI OSS manifest runtime-admitted source inventory drifted")
        sources = {}

    for source_id, source in sources.items():
        if not isinstance(source, dict):
            errors.append(f"{source_id}: source entry must be an object")
            continue
        repository = source.get("repository")
        if not isinstance(repository, str) or not repository.startswith("xai-org/"):
            errors.append(f"{source_id}: repository must be xai-org/*")
        commit = str(source.get("commit_sha", ""))
        if not FULL_SHA.fullmatch(commit):
            errors.append(f"{source_id}: commit_sha must be a full lowercase SHA")
        if source.get("license_expression") != "Apache-2.0":
            errors.append(f"{source_id}: executable source must remain Apache-2.0")
        if source.get("disposition") != "runtime_admitted":
            errors.append(f"{source_id}: copied source must be runtime_admitted")

        root = source.get("snapshot_root")
        if not isinstance(root, str) or not root.startswith(
            "skeleton/ai/research/external/xAI/"
        ):
            errors.append(f"{source_id}: snapshot_root escapes xAI quarantine")
            continue

        license_path = source.get("license_evidence_path")
        if not isinstance(license_path, str) or not (ROOT / license_path).is_file():
            errors.append(f"{source_id}: license evidence is missing")

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
            if not destination.endswith(".txt"):
                errors.append(f"{source_id}: copied material must remain non-executable .txt")
            if not FULL_SHA.fullmatch(blob):
                errors.append(f"{source_id}: invalid upstream blob SHA for {source_path}")
            elif _git_blob_sha(path) != blob:
                errors.append(f"{source_id}: byte drift from upstream blob: {source_path}")

    excluded = data.get("excluded_sources")
    if not isinstance(excluded, dict):
        errors.append("excluded xAI source registry is missing")
    else:
        prompts = excluded.get("grok-prompts", {})
        cookbook = excluded.get("xai-cookbook", {})
        if prompts.get("license_expression") != "AGPL-3.0-only":
            errors.append("grok-prompts AGPL disposition drifted")
        if cookbook.get("license_expression") != "LicenseRef-xAI-Beta-Testing":
            errors.append("xai-cookbook custom-license disposition drifted")
        for source_id, item in excluded.items():
            if item.get("disposition") != "metadata_only":
                errors.append(f"{source_id}: excluded source must remain metadata_only")

    adapters = data.get("executable_adapters")
    if not isinstance(adapters, list) or len(adapters) < 9:
        errors.append("xAI executable adapter inventory is incomplete")
        adapters = []
    for relative in adapters:
        path = ROOT / relative
        if not path.is_file():
            errors.append(f"missing xAI OSS adapter: {relative}")
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
                if "research.external.xAI" in rendered:
                    errors.append(f"adapter imports xAI snapshot directly: {relative}")

    rules = data.get("authority_rules")
    if not isinstance(rules, list) or not any(
        "server-side tools are disabled by default" in str(rule) for rule in rules
    ):
        errors.append("xAI server-side tool authority rule missing")
    if not isinstance(rules, list) or not any(
        "credentials are ephemeral" in str(rule) for rule in rules
    ):
        errors.append("xAI ephemeral credential rule missing")

    promotion = data.get("promotion_rule")
    if not isinstance(promotion, str) or "No xAI research snapshot" not in promotion:
        errors.append("xAI OSS promotion boundary is missing")

    return errors


if __name__ == "__main__":
    failures = validate()
    if failures:
        for failure in failures:
            print(f"ERROR: {failure}")
        raise SystemExit(1)
    print("xAI/Grok OSS assimilation: OK")
