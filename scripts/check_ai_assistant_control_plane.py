#!/usr/bin/env python3
"""Fail-closed validation for the clean-room AI assistant control plane."""

from __future__ import annotations

import ast
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "machine" / "ai_assistant_control_plane.json"
EXPECTED_SCHEMA = "ai-assistant-control-plane/v1"
FORBIDDEN_SOURCE_MARKERS = (
    "OPENAI_API_KEY",
    "SKELETON_OPENAI_API_KEY",
    "api.openai.com",
    "from openai import",
    "import openai",
)


def validate() -> list[str]:
    errors: list[str] = []
    if not MANIFEST.is_file():
        return ["missing machine/ai_assistant_control_plane.json"]
    try:
        data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return [f"cannot parse assistant control-plane manifest: {exc}"]

    if data.get("schema_version") != EXPECTED_SCHEMA:
        errors.append("assistant manifest schema_version drifted")
    if data.get("canonical_root") != "skeleton/ai/assistant":
        errors.append("assistant canonical_root must be skeleton/ai/assistant")
    if data.get("status") != "implemented_candidate":
        errors.append("assistant status must remain implemented_candidate before signoff")

    modules = data.get("modules")
    tests = data.get("tests")
    if not isinstance(modules, list) or len(modules) < 10:
        errors.append("assistant manifest must enumerate the implementation modules")
        modules = []
    if not isinstance(tests, list) or len(tests) < 5:
        errors.append("assistant manifest must enumerate regression tests")
        tests = []

    for raw in modules + tests:
        if not isinstance(raw, str) or not raw:
            errors.append("assistant manifest paths must be non-empty strings")
            continue
        path = ROOT / raw
        if not path.is_file():
            errors.append(f"assistant manifest path missing: {raw}")

    for raw in modules:
        if not isinstance(raw, str) or not raw.endswith(".py"):
            continue
        path = ROOT / raw
        if not path.is_file():
            continue
        try:
            source = path.read_text(encoding="utf-8")
            ast.parse(source)
        except (OSError, UnicodeDecodeError, SyntaxError) as exc:
            errors.append(f"assistant module is not valid Python: {raw}: {exc}")
            continue
        hits = [marker for marker in FORBIDDEN_SOURCE_MARKERS if marker in source]
        if hits:
            errors.append(
                f"assistant module crosses provider boundary: {raw}: {', '.join(hits)}"
            )

    exclusions = data.get("explicit_exclusions")
    if not isinstance(exclusions, list):
        errors.append("assistant manifest explicit_exclusions must be a list")
    else:
        required = {
            "vendor model weights",
            "vendor private source code",
            "provider credentials",
            "hidden chain-of-thought or private reasoning traces",
        }
        if not required <= set(exclusions):
            errors.append("assistant clean-room exclusions are incomplete")

    promotion = data.get("promotion_rule")
    if not isinstance(promotion, str) or "no completion" not in promotion:
        errors.append("assistant promotion rule must not fabricate completion")

    return errors


if __name__ == "__main__":
    failures = validate()
    if failures:
        for failure in failures:
            print(f"ERROR: {failure}")
        raise SystemExit(1)
    print("AI assistant control-plane manifest: OK")
