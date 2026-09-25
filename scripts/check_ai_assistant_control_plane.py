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
TOOLING_PATH = ROOT / "skeleton" / "ai" / "assistant" / "tooling.py"
REQUIRED_TOOLING_MARKERS = (
    "AsyncToolRuntime",
    "ToolExecutionRequest",
    "canonical-async-tool-runtime",
    "durable-receipt-store-required",
)
FORBIDDEN_TOOLING_MARKERS = (
    "self._receipts",
    "self._handlers",
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

    if not TOOLING_PATH.is_file():
        errors.append("assistant tooling module is missing")
    else:
        try:
            tooling_source = TOOLING_PATH.read_text(encoding="utf-8")
            tooling_tree = ast.parse(tooling_source)
        except (OSError, UnicodeDecodeError, SyntaxError) as exc:
            errors.append(f"cannot inspect assistant tooling authority: {exc}")
        else:
            missing_markers = [
                marker
                for marker in REQUIRED_TOOLING_MARKERS
                if marker not in tooling_source
            ]
            if missing_markers:
                errors.append(
                    "assistant tooling lost canonical-runtime delegation markers: "
                    + ", ".join(missing_markers)
                )
            forbidden_hits = [
                marker
                for marker in FORBIDDEN_TOOLING_MARKERS
                if marker in tooling_source
            ]
            if forbidden_hits:
                errors.append(
                    "assistant tooling regained shadow execution state: "
                    + ", ".join(forbidden_hits)
                )

            coordinator = next(
                (
                    node
                    for node in tooling_tree.body
                    if isinstance(node, ast.ClassDef)
                    and node.name == "ToolCoordinator"
                ),
                None,
            )
            if coordinator is None:
                errors.append("assistant tooling must define ToolCoordinator")
            else:
                init = next(
                    (
                        node
                        for node in coordinator.body
                        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                        and node.name == "__init__"
                    ),
                    None,
                )
                if init is None:
                    errors.append("ToolCoordinator must define an explicit constructor")
                else:
                    kwonly = {
                        arg.arg: default
                        for arg, default in zip(
                            init.args.kwonlyargs,
                            init.args.kw_defaults,
                        )
                    }
                    if "tool_runtime" not in kwonly:
                        errors.append(
                            "ToolCoordinator must require injected tool_runtime"
                        )
                    elif kwonly["tool_runtime"] is not None:
                        errors.append(
                            "ToolCoordinator tool_runtime must not have a default"
                        )

                canonical_execute = False
                for node in ast.walk(coordinator):
                    if not isinstance(node, ast.Call):
                        continue
                    func = node.func
                    if (
                        isinstance(func, ast.Attribute)
                        and func.attr == "execute"
                        and isinstance(func.value, ast.Attribute)
                        and func.value.attr == "tool_runtime"
                        and isinstance(func.value.value, ast.Name)
                        and func.value.value.id == "self"
                    ):
                        canonical_execute = True
                        break
                if not canonical_execute:
                    errors.append(
                        "ToolCoordinator must delegate admitted calls to self.tool_runtime.execute"
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
