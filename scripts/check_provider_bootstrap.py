#!/usr/bin/env python3
"""Verify mandatory AI-provider bootstrap and provider-boundary isolation."""

from __future__ import annotations

import argparse
import ast
from functools import lru_cache
import json
import os
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
)
_NON_PROVIDER_NETWORK_PATH_PREFIXES = ("skeleton/ai/research/legacy/",)
_NON_RUNTIME_PROVIDER_MIRROR_PREFIXES = (
    "skeleton/ai/research/external/",
)
_NETWORK_TRANSPORT_ROOTS = frozenset(
    {
        "urllib.request",
        "requests",
        "httpx",
        "aiohttp",
    }
)
_PROVIDER_URL_MARKERS = frozenset(
    {
        "api.openai.com",
        "api.anthropic.com",
        "generativelanguage.googleapis.com",
        "api.groq.com",
        "api.mistral.ai",
        "api.cohere.ai",
    }
)
_PROVIDER_CLIENT_MARKERS = frozenset(
    {
        "AsyncOpenAI",
        "OpenAI(",
        "Anthropic(",
        "AsyncAnthropic",
        "genai.Client",
        "MODEL_API_URL",
        "OPENAI_BASE_URL",
    }
)
_ALLOWED_SURFACE_CLASSES = frozenset(
    {
        "canonical_runtime",
        "provider_declaration",
        "noncredential_compatibility_facade",
        "automation_provider_explicitly_separate_and_receipt-gated",
    }
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


@lru_cache(maxsize=16_384)
def _cached_python_tree(
    path_text: str,
    mtime_ns: int,
    size: int,
) -> ast.AST | None:
    """Parse one unchanged Python file once per validator process."""

    del mtime_ns, size  # Cache-key material; content is read only on cache miss.
    try:
        return ast.parse(Path(path_text).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, SyntaxError):
        return None


def _python_tree(path: Path) -> ast.AST | None:
    try:
        stat = path.stat()
    except OSError:
        return None
    return _cached_python_tree(
        str(path.resolve()),
        int(stat.st_mtime_ns),
        int(stat.st_size),
    )


@lru_cache(maxsize=16_384)
def _cached_source(
    path_text: str,
    mtime_ns: int,
    size: int,
) -> str:
    """Read one unchanged Python source file once per validator process."""

    del mtime_ns, size
    try:
        return Path(path_text).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def _python_source(path: Path) -> str:
    try:
        stat = path.stat()
    except OSError:
        return ""
    return _cached_source(
        str(path.resolve()),
        int(stat.st_mtime_ns),
        int(stat.st_size),
    )


def _imported_modules(path: Path) -> list[str]:
    tree = _python_tree(path)
    if tree is None:
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


def _network_transport_imports(path: Path) -> list[str]:
    hits: list[str] = []
    tree = _python_tree(path)
    if tree is None:
        return hits
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                name = alias.name
                if name in _NETWORK_TRANSPORT_ROOTS or any(
                    name.startswith(root + ".") for root in _NETWORK_TRANSPORT_ROOTS
                ):
                    hits.append(name)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module == "urllib" and any(alias.name == "request" for alias in node.names):
                hits.append("urllib.request")
            elif module in _NETWORK_TRANSPORT_ROOTS or any(
                module.startswith(root + ".") for root in _NETWORK_TRANSPORT_ROOTS
            ):
                hits.append(module)
    return hits


def _credential_environment_reads(path: Path) -> list[str]:
    """Return credential names actually read from os.getenv/os.environ APIs."""

    tree = _python_tree(path)
    if tree is None:
        return []

    hits: set[str] = set()
    os_module_names = {"os"}
    getenv_names: set[str] = set()
    environ_names: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "os":
                    os_module_names.add(alias.asname or alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module == "os":
            for alias in node.names:
                if alias.name == "getenv":
                    getenv_names.add(alias.asname or alias.name)
                elif alias.name == "environ":
                    environ_names.add(alias.asname or alias.name)

    def constant_string(node: ast.AST | None) -> str | None:
        return (
            node.value
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
            else None
        )

    def credential_name(node: ast.AST | None) -> str | None:
        name = constant_string(node)
        return name if name in _AI_CREDENTIAL_MARKERS else None

    def is_environ_value(node: ast.AST) -> bool:
        if isinstance(node, ast.Name):
            return node.id in environ_names
        return (
            isinstance(node, ast.Attribute)
            and node.attr == "environ"
            and isinstance(node.value, ast.Name)
            and node.value.id in os_module_names
        )

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            direct_getenv = (
                isinstance(func, ast.Name)
                and func.id in getenv_names
            )
            module_getenv = (
                isinstance(func, ast.Attribute)
                and func.attr == "getenv"
                and isinstance(func.value, ast.Name)
                and func.value.id in os_module_names
            )
            environ_get = (
                isinstance(func, ast.Attribute)
                and func.attr == "get"
                and is_environ_value(func.value)
            )
            if (direct_getenv or module_getenv or environ_get) and node.args:
                name = credential_name(node.args[0])
                if name:
                    hits.add(name)
        elif isinstance(node, ast.Subscript) and is_environ_value(node.value):
            name = credential_name(node.slice)
            if name:
                hits.add(name)

    return sorted(hits)

def _credential_markers(path: Path) -> list[str]:
    """Return credential edges from real environment reads or declared key slots.

    AST-based assignment detection keeps comments/docstrings harmless while still
    classifying modules that explicitly own a provider credential variable.
    """
    hits = set(_credential_environment_reads(path))
    tree = _python_tree(path)
    if tree is None:
        return sorted(hits)

    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Name)
            and isinstance(node.ctx, ast.Store)
            and node.id in _AI_CREDENTIAL_MARKERS
        ):
            hits.add(node.id)
    return sorted(hits)


def _is_non_runtime_provider_mirror(relative: str) -> bool:
    normalized = relative.replace("\\", "/")
    return any(
        normalized.startswith(prefix)
        for prefix in _NON_RUNTIME_PROVIDER_MIRROR_PREFIXES
    )


def _provider_surface_signals(path: Path, source: str) -> dict[str, list[str]]:
    credential_markers = _credential_markers(path)
    sdk_imports = sorted(set(_provider_sdk_imports(path)))
    network_imports = sorted(set(_network_transport_imports(path)))
    provider_urls = sorted(
        marker for marker in _PROVIDER_URL_MARKERS if marker in source
    )
    client_markers = sorted(
        marker for marker in _PROVIDER_CLIENT_MARKERS if marker in source
    )
    return {
        "credential_markers": credential_markers,
        "sdk_imports": sdk_imports,
        "network_imports": network_imports,
        "provider_urls": provider_urls,
        "client_markers": client_markers,
    }

def _looks_like_provider_network_surface(
    path: Path,
    source: str,
    signals: dict[str, list[str]],
) -> bool:
    if not signals["network_imports"]:
        return False

    relative = "/" + path.as_posix().lower().lstrip("/")
    if any(f"/{prefix}" in relative for prefix in _NON_PROVIDER_NETWORK_PATH_PREFIXES):
        return False

    provider_path = any(term in relative for term in _AI_SURFACE_PATH_TERMS)
    provider_context = (
        bool(signals["credential_markers"])
        or bool(signals["sdk_imports"])
        or bool(signals["provider_urls"])
        or bool(signals["client_markers"])
        or provider_path
    )
    return provider_context


def discover_provider_surfaces(repo_root: Path) -> dict[str, dict[str, list[str]]]:
    discovered: dict[str, dict[str, list[str]]] = {}
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
                or _is_non_runtime_provider_mirror(relative)
            ):
                continue
            source = _python_source(path)
            if not source:
                continue
            signals = _provider_surface_signals(path, source)
            edge_classes: list[str] = []
            provider_context = (
                bool(signals["sdk_imports"])
                or bool(signals["provider_urls"])
                or bool(signals["client_markers"])
            )
            if signals["credential_markers"] and provider_context:
                edge_classes.append("credential")
            if signals["sdk_imports"]:
                edge_classes.append("sdk_client")
            if _looks_like_provider_network_surface(path, source, signals):
                edge_classes.append("network_transport")
            if edge_classes:
                discovered[relative] = {
                    **signals,
                    "edge_classes": sorted(edge_classes),
                }
    return discovered


def _looks_like_ai_provider_surface(path: Path, source: str) -> bool:
    relative = path.as_posix().lower()
    if not any(term in relative for term in _AI_SURFACE_PATH_TERMS):
        return False
    if any(marker in source for marker in _AI_CREDENTIAL_MARKERS):
        return True
    return bool(_provider_sdk_imports(path))


def _discover_credential_bearing_ai_surfaces(repo_root: Path) -> set[str]:
    return {
        path
        for path, signals in discover_provider_surfaces(repo_root).items()
        if "credential" in signals["edge_classes"]
    }


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
        "COPY --chown=appuser:appuser machine/state_topology.json ./machine/state_topology.json",
        "COPY --chown=appuser:appuser machine/ai_runtime_schemas.json ./machine/ai_runtime_schemas.json",
        "COPY --chown=appuser:appuser machine/ai_capabilities.json ./machine/ai_capabilities.json",
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
    declared_by_owner: dict[str, dict] = {}
    credential_surface_owners: set[str] = set()
    network_surface_owners: set[str] = set()
    sdk_surface_owners: set[str] = set()
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
            if owner in declared_by_owner:
                errors.append(f"duplicate provider surface owner: {owner}")
            declared_by_owner[owner] = item
            path = repo_root / owner
            if not path.is_file():
                errors.append(f"provider surface owner missing: {owner}")
                continue

            surface_class = item.get("surface_class")
            if surface_class not in _ALLOWED_SURFACE_CLASSES:
                errors.append(
                    f"provider surface {surface_id} has invalid surface_class: "
                    f"{surface_class!r}"
                )

            ownership_fields = (
                "credential_owner",
                "network_transport_owner",
                "sdk_client_owner",
            )
            for field in ownership_fields:
                if not isinstance(item.get(field), bool):
                    errors.append(
                        f"provider surface {surface_id}.{field} must be boolean"
                    )

            expected_edges = item.get("discovery_edge_classes")
            if not isinstance(expected_edges, list) or any(
                edge not in {"credential", "network_transport", "sdk_client"}
                for edge in expected_edges
            ):
                errors.append(
                    f"provider surface {surface_id} discovery_edge_classes are invalid"
                )
                expected_edges = []

            if item.get("credential_owner") is True:
                credential_surface_owners.add(owner)
            if item.get("network_transport_owner") is True:
                network_surface_owners.add(owner)
            if item.get("sdk_client_owner") is True:
                sdk_surface_owners.add(owner)

            if item.get("credential_bearing") is not item.get("credential_owner"):
                errors.append(
                    f"provider surface {surface_id} credential_bearing disagrees "
                    "with credential_owner"
                )

            if item.get("credential_owner") is True:
                if item.get("receipt_required") is not True:
                    errors.append(
                        f"credential-bearing provider surface lacks receipt: {surface_id}"
                    )
                source = path.read_text(encoding="utf-8", errors="replace")
                if "load_provider_architecture" not in source:
                    errors.append(
                        f"credential-bearing provider surface does not load architecture: {owner}"
                    )

    discovered = discover_provider_surfaces(repo_root)
    for owner, signals in sorted(discovered.items()):
        declaration = declared_by_owner.get(owner)
        if declaration is None:
            errors.append(
                "provider edge surface missing from construction inventory: "
                f"{owner}: {', '.join(signals['edge_classes'])}"
            )
            continue
        expected = set(declaration.get("discovery_edge_classes", []))
        actual = set(signals["edge_classes"])
        if expected != actual:
            errors.append(
                f"provider surface edge classification drift: {owner}: "
                f"declared={sorted(expected)} discovered={sorted(actual)}"
            )
        if "credential" in actual and declaration.get("credential_owner") is not True:
            errors.append(f"provider credential edge lacks ownership: {owner}")
        if (
            "network_transport" in actual
            and declaration.get("network_transport_owner") is not True
        ):
            errors.append(f"provider network edge lacks ownership: {owner}")
        if "sdk_client" in actual and declaration.get("sdk_client_owner") is not True:
            errors.append(f"provider SDK edge lacks ownership: {owner}")

    for owner in sorted(credential_surface_owners):
        if owner not in discovered or "credential" not in discovered[owner]["edge_classes"]:
            errors.append(f"declared credential owner has no discovered credential edge: {owner}")
    for owner in sorted(network_surface_owners):
        if owner not in discovered or "network_transport" not in discovered[owner]["edge_classes"]:
            errors.append(f"declared network owner has no discovered network edge: {owner}")
    for owner in sorted(sdk_surface_owners):
        if owner not in discovered or "sdk_client" not in discovered[owner]["edge_classes"]:
            errors.append(f"declared SDK owner has no discovered SDK edge: {owner}")

    convergence = contract.get("provider_surface_convergence_blueprint")
    isolation_surfaces = (
        convergence.get("application_isolation_surfaces", [])
        if isinstance(convergence, dict)
        else []
    )
    if not isinstance(isolation_surfaces, list) or not isolation_surfaces:
        errors.append("provider application isolation surfaces are missing")
    else:
        for item in isolation_surfaces:
            if not isinstance(item, dict):
                errors.append("provider application isolation entry must be an object")
                continue
            relative = item.get("path")
            if not isinstance(relative, str) or not relative:
                errors.append("provider application isolation path is invalid")
                continue
            path = repo_root / relative
            if not path.is_file():
                errors.append(
                    f"provider application isolation surface missing: {relative}"
                )
                continue
            source = path.read_text(encoding="utf-8", errors="replace")
            required_tokens = item.get("required_tokens")
            if not isinstance(required_tokens, list):
                errors.append(
                    f"provider application isolation required_tokens invalid: {relative}"
                )
                required_tokens = []
            for token in required_tokens:
                if not isinstance(token, str) or not token:
                    errors.append(
                        f"provider application isolation token invalid: {relative}"
                    )
                elif token not in source:
                    errors.append(
                        f"provider application surface lost canonical delegation token: "
                        f"{relative}: {token}"
                    )

            forbidden = item.get("forbidden_edge_classes")
            if not isinstance(forbidden, list):
                errors.append(
                    f"provider application isolation forbidden_edge_classes invalid: "
                    f"{relative}"
                )
                forbidden = []
            signals = _provider_surface_signals(path, source)
            edge_classes: set[str] = set()
            if signals["credential_markers"]:
                edge_classes.add("credential")
            if signals["sdk_imports"]:
                edge_classes.add("sdk_client")
            if _looks_like_provider_network_surface(path, source, signals):
                edge_classes.add("network_transport")
            violations = sorted(edge_classes.intersection(forbidden))
            if violations:
                errors.append(
                    "provider application surface owns forbidden provider edges: "
                    f"{relative}: {', '.join(violations)}"
                )


    for root_name in ("backend", "skeleton"):
        source_root = repo_root / root_name
        if not source_root.is_dir():
            continue
        for path in sorted(source_root.rglob("*.py")):
            relative = path.relative_to(repo_root).as_posix()
            if (
                "/tests/" in "/" + relative
                or relative.startswith("tests/")
                or "/testing/" in "/" + relative
                or path.name.startswith("test_")
                or _is_non_runtime_provider_mirror(relative)
            ):
                continue
            if relative not in sdk_surface_owners:
                hits = _provider_sdk_imports(path)
                if hits:
                    errors.append(
                        "provider SDK bypass outside declared SDK owner: "
                        f"{relative}: {', '.join(hits)}"
                    )

            source = _python_source(path)
            signals = _provider_surface_signals(path, source)
            if (
                relative not in network_surface_owners
                and _looks_like_provider_network_surface(path, source, signals)
            ):
                errors.append(
                    "provider network bypass outside declared network owner: "
                    f"{relative}: {', '.join(signals['network_imports'])}"
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


def build_provider_surface_evidence(
    repo_root: Path = ROOT,
    *,
    head_sha: str | None = None,
    errors: list[str] | None = None,
) -> dict:
    """Return a secret-free current-head provider surface receipt."""

    try:
        contract = _load() if repo_root == ROOT else json.loads(
            (repo_root / "machine/ai_app_construction.json").read_text(
                encoding="utf-8"
            )
        )
    except (ValueError, OSError, json.JSONDecodeError):
        contract = {}

    declared: list[dict] = []
    for item in contract.get("provider_surfaces", []):
        if not isinstance(item, dict):
            continue
        declared.append(
            {
                "id": item.get("id"),
                "owner": item.get("owner"),
                "surface_class": item.get("surface_class"),
                "credential_owner": item.get("credential_owner"),
                "network_transport_owner": item.get("network_transport_owner"),
                "sdk_client_owner": item.get("sdk_client_owner"),
                "discovery_edge_classes": item.get(
                    "discovery_edge_classes", []
                ),
            }
        )

    convergence = contract.get("provider_surface_convergence_blueprint", {})
    isolated = []
    if isinstance(convergence, dict):
        for item in convergence.get("application_isolation_surfaces", []):
            if isinstance(item, dict) and isinstance(item.get("path"), str):
                isolated.append(item["path"])

    return {
        "schema_version": 1,
        "head_sha": (
            head_sha
            if head_sha is not None
            else os.environ.get("EVIDENCE_HEAD_SHA", "").strip()\n            or os.environ.get("GITHUB_SHA", "").strip()\n            or "unknown"
        ),
        "declared_surfaces": sorted(
            declared,
            key=lambda item: str(item.get("id") or ""),
        ),
        "discovered_surfaces": discover_provider_surfaces(repo_root),
        "application_isolation_surfaces": sorted(isolated),
        "validation_errors": list(errors or []),
        "valid": not bool(errors),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate and inventory provider execution surfaces."
    )
    parser.add_argument(
        "--evidence-out",
        type=Path,
        default=None,
        help="Write a secret-free JSON evidence receipt to this path.",
    )
    parser.add_argument(
        "--print-evidence",
        action="store_true",
        help="Print the JSON evidence receipt after validation.",
    )
    args = parser.parse_args(argv)

    errors = validate_provider_bootstrap()
    evidence = build_provider_surface_evidence(errors=errors)
    if args.evidence_out is not None:
        args.evidence_out.parent.mkdir(parents=True, exist_ok=True)
        args.evidence_out.write_text(
            json.dumps(evidence, indent=2, sort_keys=True) + "\\n",
            encoding="utf-8",
        )
    if args.print_evidence:
        print(json.dumps(evidence, indent=2, sort_keys=True))

    if errors:
        print("provider-bootstrap: rejected", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1
    print(
        "provider-bootstrap: OK "
        "(mandatory docs, shared receipts, provider families, classified surface inventory, network/SDK isolation)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
