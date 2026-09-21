#!/usr/bin/env python3
"""Verify mandatory AI-provider bootstrap and provider-boundary isolation."""

from __future__ import annotations

import ast
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONSTRUCTION = ROOT / "machine/ai_app_construction.json"

_PROVIDER_SDK_ROOTS = frozenset(
    {
        "openai",
        "anthropic",
        "cohere",
        "groq",
        "mistralai",
        "litellm",
        "google.generativeai",
        "google.genai",
    }
)
_ALLOWED_PROVIDER_SDK_IMPORTERS = frozenset(
    {
        "backend/core/ai_provider.py",
    }
)
_SHADOW_PROVIDER_RUNTIME_MODULES = frozenset(
    {
        "skeleton.frontier.model_runtime",
    }
)
_ALLOWED_SHADOW_RUNTIME_IMPORTERS = frozenset()


def _load() -> dict:
    try:
        payload = json.loads(CONSTRUCTION.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("AI construction contract is unavailable or invalid") from exc
    if not isinstance(payload, dict):
        raise ValueError("AI construction contract must be an object")
    return payload


def _sdk_root(name: str) -> str:
    if name.startswith("google.generativeai"):
        return "google.generativeai"
    if name.startswith("google.genai"):
        return "google.genai"
    return name.split(".", 1)[0]


def _imported_modules(path: Path) -> list[str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return []
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.append(node.module)
    return modules


def _provider_sdk_imports(path: Path) -> list[str]:
    hits: list[str] = []
    for name in _imported_modules(path):
        root = _sdk_root(name)
        if root in _PROVIDER_SDK_ROOTS:
            hits.append(name)
    return hits


def _shadow_provider_runtime_imports(path: Path) -> list[str]:
    hits: list[str] = []
    for name in _imported_modules(path):
        if any(
            name == forbidden or name.startswith(forbidden + ".")
            for forbidden in _SHADOW_PROVIDER_RUNTIME_MODULES
        ):
            hits.append(name)
    return hits


def validate_provider_bootstrap(repo_root: Path = ROOT) -> list[str]:
    errors: list[str] = []
    try:
        contract = _load() if repo_root == ROOT else json.loads(
            (repo_root / "machine/ai_app_construction.json").read_text(encoding="utf-8")
        )
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        return [str(exc)]

    bootstrap = contract.get("provider_bootstrap")
    if not isinstance(bootstrap, dict):
        return ["provider_bootstrap is missing"]

    must_read = bootstrap.get("must_read")
    if not isinstance(must_read, list) or not must_read:
        errors.append("provider_bootstrap.must_read must be a non-empty list")
        must_read = []

    for relative in must_read:
        if not isinstance(relative, str) or not relative:
            errors.append("provider mandatory document path is invalid")
            continue
        path = repo_root / relative
        if not path.is_file():
            errors.append(f"provider mandatory document missing: {relative}")
        elif not path.read_text(encoding="utf-8", errors="replace").strip():
            errors.append(f"provider mandatory document empty: {relative}")

    entries = bootstrap.get("development_provider_entrypoints")
    if not isinstance(entries, list) or not entries:
        errors.append("development provider entrypoints are missing")
    else:
        for item in entries:
            if not isinstance(item, dict):
                errors.append("development provider entrypoint must be an object")
                continue
            provider = item.get("provider")
            relative = item.get("path")
            if not isinstance(provider, str) or not provider:
                errors.append("development provider id is invalid")
                continue
            if not isinstance(relative, str) or not relative:
                errors.append(f"development provider {provider} instruction path is invalid")
                continue
            path = repo_root / relative
            if not path.is_file():
                errors.append(f"development provider instruction missing: {relative}")
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            for required in must_read:
                if isinstance(required, str) and required not in text:
                    errors.append(
                        f"development provider {provider} is not instructed to read {required}"
                    )

    runtime = bootstrap.get("runtime_enforcement")
    if not isinstance(runtime, dict):
        errors.append("runtime provider enforcement contract is missing")
        return errors

    loader_path = runtime.get("loader")
    boundary_path = runtime.get("activation_boundary")
    docker_path = runtime.get("docker_materialization")
    for label, relative in (
        ("loader", loader_path),
        ("activation boundary", boundary_path),
        ("docker materialization", docker_path),
    ):
        if not isinstance(relative, str) or not (repo_root / relative).is_file():
            errors.append(f"runtime provider {label} is missing: {relative!r}")

    if isinstance(boundary_path, str) and (repo_root / boundary_path).is_file():
        boundary = (repo_root / boundary_path).read_text(encoding="utf-8")
        required_tokens = (
            "load_provider_architecture",
            "_ensure_architecture",
            "_architecture_receipt",
            "architecture_acknowledged",
        )
        for token in required_tokens:
            if token not in boundary:
                errors.append(
                    f"provider activation boundary does not enforce architecture token {token!r}"
                )

    if isinstance(docker_path, str) and (repo_root / docker_path).is_file():
        docker = (repo_root / docker_path).read_text(encoding="utf-8")
        for token in (
            "COPY --chown=appuser:appuser machine/manifest.json ./machine/manifest.json",
            "COPY --chown=appuser:appuser machine/architecture.json ./machine/architecture.json",
            "COPY --chown=appuser:appuser machine/ai_app_construction.json ./machine/ai_app_construction.json",
            "COPY --chown=appuser:appuser docs/AI_APP_CONSTRUCTION_MANUAL.md ./docs/AI_APP_CONSTRUCTION_MANUAL.md",
        ):
            if token not in docker:
                errors.append(
                    f"backend runtime image does not materialize provider contract: {token}"
                )

    declared = contract.get("runtime_model_providers")
    if not isinstance(declared, list) or not declared:
        errors.append("runtime model provider declarations are missing")
    else:
        seen: set[str] = set()
        for item in declared:
            if not isinstance(item, dict):
                errors.append("runtime provider declaration must be an object")
                continue
            provider_id = item.get("id")
            if not isinstance(provider_id, str) or not provider_id:
                errors.append("runtime provider id is invalid")
                continue
            if provider_id in seen:
                errors.append(f"duplicate runtime provider declaration: {provider_id}")
            seen.add(provider_id)
            for key in (
                "architecture_read_required",
                "construction_manual_read_required",
                "activation_receipt_required",
            ):
                if item.get(key) is not True:
                    errors.append(f"runtime provider {provider_id}.{key} must be true")

    backend = repo_root / "backend"
    if backend.is_dir():
        for path in sorted(backend.rglob("*.py")):
            relative = path.relative_to(repo_root).as_posix()
            if relative in _ALLOWED_PROVIDER_SDK_IMPORTERS:
                continue
            hits = _provider_sdk_imports(path)
            if hits:
                errors.append(
                    f"provider SDK bypass outside canonical boundary: {relative}: {', '.join(hits)}"
                )
            if relative not in _ALLOWED_SHADOW_RUNTIME_IMPORTERS:
                shadow_hits = _shadow_provider_runtime_imports(path)
                if shadow_hits:
                    errors.append(
                        "shadow provider runtime import outside canonical boundary: "
                        f"{relative}: {', '.join(shadow_hits)}"
                    )

    return errors


def main() -> int:
    errors = validate_provider_bootstrap()
    if errors:
        print("provider-bootstrap: rejected", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1
    print("provider-bootstrap: OK (mandatory docs, runtime receipt, SDK isolation)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
