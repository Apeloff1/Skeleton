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
        "skeleton/provider_runtime.py",
    }
)
_SHADOW_PROVIDER_RUNTIME_MODULES = frozenset(
    {
        "skeleton.frontier.model_runtime",
    }
)
_ALLOWED_SHADOW_RUNTIME_IMPORTERS = frozenset()

_AI_CREDENTIAL_MARKERS = frozenset(
    {
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "SKELETON_OPENAI_API_KEY",
        "SKELETON_ANTHROPIC_API_KEY",
        "MODEL_API_KEY",
        "EMERGENT_LLM_KEY",
        "GEMINI_API_KEY",
        "GOOGLE_API_KEY",
        "GROQ_API_KEY",
        "MISTRAL_API_KEY",
        "COHERE_API_KEY",
    }
)
_AI_SURFACE_PATH_TERMS = (
    "provider",
    "llm",
    "model",
    "ai_",
    "/ai.",
    "/ai/",
)


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



def _looks_like_ai_provider_surface(path: Path, source: str) -> bool:
    relative = path.as_posix().lower()
    if not any(term in relative for term in _AI_SURFACE_PATH_TERMS):
        return False
    if any(marker in source for marker in _AI_CREDENTIAL_MARKERS):
        return True
    return bool(_provider_sdk_imports(path))


def _discover_credential_bearing_ai_surfaces(repo_root: Path) -> set[str]:
    discovered: set[str] = set()
    for root_name in ("backend", "skeleton"):
        root = repo_root / root_name
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*.py")):
            relative = path.relative_to(repo_root).as_posix()
            if (
                "/tests/" in "/" + relative
                or relative.startswith("tests/")
                or "/testing/" in "/" + relative
                or path.name.startswith("test_")
            ):
                continue
            try:
                source = path.read_text(encoding="utf-8")
            except OSError:
                continue
            if _looks_like_ai_provider_surface(path, source):
                discovered.add(relative)
    return discovered


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
    engine_docker_path = runtime.get("engine_docker_materialization")
    for label, relative in (
        ("loader", loader_path),
        ("activation boundary", boundary_path),
        ("docker materialization", docker_path),
        ("engine docker materialization", engine_docker_path),
    ):
        if not isinstance(relative, str) or not (repo_root / relative).is_file():
            errors.append(f"runtime provider {label} is missing: {relative!r}")

    if isinstance(loader_path, str) and (repo_root / loader_path).is_file():
        loader = (repo_root / loader_path).read_text(encoding="utf-8")
        for token in (
            "ProviderArchitectureReceipt",
            "provider_family",
            "runtime_model_providers",
            "automation_model_providers",
            "must_read",
        ):
            if token not in loader:
                errors.append(
                    f"shared provider loader does not enforce contract token {token!r}"
                )

    compatibility_loaders = runtime.get("compatibility_loaders", [])
    if not isinstance(compatibility_loaders, list) or not compatibility_loaders:
        errors.append("provider compatibility loaders are missing")
    else:
        for relative in compatibility_loaders:
            if not isinstance(relative, str):
                errors.append("provider compatibility loader path is invalid")
                continue
            path = repo_root / relative
            if not path.is_file():
                errors.append(f"provider compatibility loader missing: {relative}")
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            if "from skeleton.provider_contract import" not in text:
                errors.append(
                    f"provider compatibility loader is not a shared-contract re-export: {relative}"
                )

    compatibility_boundaries = runtime.get("compatibility_boundaries", [])
    if not isinstance(compatibility_boundaries, list) or not compatibility_boundaries:
        errors.append("provider compatibility boundaries are missing")
    else:
        for relative in compatibility_boundaries:
            if not isinstance(relative, str):
                errors.append("provider compatibility boundary path is invalid")
                continue
            path = repo_root / relative
            if not path.is_file():
                errors.append(f"provider compatibility boundary missing: {relative}")
                continue
            source = path.read_text(encoding="utf-8", errors="replace")
            credential_hits = sorted(
                marker for marker in _AI_CREDENTIAL_MARKERS if marker in source
            )
            if credential_hits:
                errors.append(
                    "provider compatibility boundary owns credential markers: "
                    f"{relative}: {', '.join(credential_hits)}"
                )
            sdk_hits = _provider_sdk_imports(path)
            if sdk_hits:
                errors.append(
                    "provider compatibility boundary imports provider SDKs: "
                    f"{relative}: {', '.join(sdk_hits)}"
                )

    families = runtime.get("provider_families")
    if not isinstance(families, list) or set(families) != {
        "runtime_model",
        "automation_model",
    }:
        errors.append(
            "provider families must declare exactly runtime_model and automation_model"
        )

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

    required_materialized_contracts = (
        "COPY --chown=appuser:appuser machine/manifest.json ./machine/manifest.json",
        "COPY --chown=appuser:appuser machine/architecture.json ./machine/architecture.json",
        "COPY --chown=appuser:appuser machine/ai_app_construction.json ./machine/ai_app_construction.json",
        "COPY --chown=appuser:appuser machine/capability_interfaces.json ./machine/capability_interfaces.json",
        "COPY --chown=appuser:appuser machine/ai_runtime_schemas.json ./machine/ai_runtime_schemas.json",
        "COPY --chown=appuser:appuser machine/ai_implementation_handoff.json ./machine/ai_implementation_handoff.json",
        "COPY --chown=appuser:appuser machine/ai_closure_evidence.json ./machine/ai_closure_evidence.json",
        "COPY --chown=appuser:appuser docs/AI_APP_CONSTRUCTION_MANUAL.md ./docs/AI_APP_CONSTRUCTION_MANUAL.md",
    )
    for image_label, image_path in (
        ("backend runtime image", docker_path),
        ("engine runtime image", engine_docker_path),
    ):
        if isinstance(image_path, str) and (repo_root / image_path).is_file():
            docker = (repo_root / image_path).read_text(encoding="utf-8")
            for token in required_materialized_contracts:
                if token not in docker:
                    errors.append(
                        f"{image_label} does not materialize provider contract: {token}"
                    )

    for family_key, family_label in (
        ("runtime_model_providers", "runtime"),
        ("automation_model_providers", "automation"),
    ):
        declared = contract.get(family_key)
        if not isinstance(declared, list) or not declared:
            errors.append(f"{family_label} model provider declarations are missing")
            continue
        seen: set[str] = set()
        for item in declared:
            if not isinstance(item, dict):
                errors.append(f"{family_label} provider declaration must be an object")
                continue
            provider_id = item.get("id")
            if not isinstance(provider_id, str) or not provider_id:
                errors.append(f"{family_label} provider id is invalid")
                continue
            if provider_id in seen:
                errors.append(
                    f"duplicate {family_label} provider declaration: {provider_id}"
                )
            seen.add(provider_id)
            for key in (
                "architecture_read_required",
                "construction_manual_read_required",
                "activation_receipt_required",
            ):
                if item.get(key) is not True:
                    errors.append(
                        f"{family_label} provider {provider_id}.{key} must be true"
                    )

    surfaces = contract.get("provider_surfaces")
    credential_surface_owners: set[str] = set()
    if not isinstance(surfaces, list) or not surfaces:
        errors.append("provider surface inventory is missing")
    else:
        surface_ids: set[str] = set()
        for item in surfaces:
            if not isinstance(item, dict):
                errors.append("provider surface entry must be an object")
                continue
            surface_id = item.get("id")
            owner = item.get("owner")
            if not isinstance(surface_id, str) or not surface_id:
                errors.append("provider surface id is invalid")
                continue
            if surface_id in surface_ids:
                errors.append(f"duplicate provider surface id: {surface_id}")
            surface_ids.add(surface_id)
            if not isinstance(owner, str) or not owner:
                errors.append(f"provider surface {surface_id} owner is invalid")
                continue
            path = repo_root / owner
            if not path.is_file():
                errors.append(f"provider surface owner missing: {owner}")
                continue
            if item.get("credential_bearing") is True:
                credential_surface_owners.add(owner)
                if item.get("receipt_required") is not True:
                    errors.append(
                        f"credential-bearing provider surface lacks receipt: {surface_id}"
                    )
                source = path.read_text(encoding="utf-8", errors="replace")
                if "load_provider_architecture" not in source:
                    errors.append(
                        f"credential-bearing provider surface does not load architecture: {owner}"
                    )

    discovered_surfaces = _discover_credential_bearing_ai_surfaces(repo_root)
    undeclared_surfaces = sorted(discovered_surfaces - credential_surface_owners)
    if undeclared_surfaces:
        errors.append(
            "credential-bearing AI provider surfaces missing from construction inventory: "
            + ", ".join(undeclared_surfaces)
        )

    for root_name in ("backend", "skeleton"):
        source_root = repo_root / root_name
        if not source_root.is_dir():
            continue
        for path in sorted(source_root.rglob("*.py")):
            relative = path.relative_to(repo_root).as_posix()
            if relative not in _ALLOWED_PROVIDER_SDK_IMPORTERS:
                hits = _provider_sdk_imports(path)
                if hits:
                    errors.append(
                        "provider SDK bypass outside canonical boundary: "
                        f"{relative}: {', '.join(hits)}"
                    )

            # The frontier protocol/runtime is engine-local library code. Backend
            # feature code may not import it as an alternate model execution path.
            if root_name == "backend" and relative not in _ALLOWED_SHADOW_RUNTIME_IMPORTERS:
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
    print(
        "provider-bootstrap: OK "
        "(mandatory docs, shared receipts, provider families, surface inventory, SDK isolation)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
