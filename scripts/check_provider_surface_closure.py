#!/usr/bin/env python3
"""Fail-closed closure gate for the runtime model-provider ownership gap.

This validator intentionally composes the existing provider bootstrap and SDK
boundary audits instead of reimplementing them.  It adds closure assertions that
must hold together:

* skeleton/provider_runtime.py is the sole runtime-model credential/network/SDK
  owner declared by the construction contract;
* every discovered provider edge maps to a declared owner;
* compatibility, Jeeves, image and TTS application surfaces own no credentials,
  provider network transport or vendor SDK clients;
* canonical Compose materializes runtime-model credentials only in the Skeleton
  engine process, never the backend process;
* async, sync and media runtime capabilities are all represented by the same
  canonical owner.

The repository-automation model family is intentionally separate and is not
counted as product runtime-model credential ownership.
"""

from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path
import sys
from typing import Any

from scripts.check_provider_bootstrap import (
    _credential_environment_reads,
    _looks_like_provider_network_surface,
    _provider_sdk_imports,
    _provider_surface_signals,
    build_provider_surface_evidence,
    discover_provider_surfaces,
    validate_provider_bootstrap,
)
from scripts.check_provider_runtime_boundary import audit_repository


ROOT = Path(__file__).resolve().parents[1]
CONSTRUCTION = ROOT / "machine" / "ai_app_construction.json"
COMPOSE = ROOT / "docker-compose.yml"

_EXPECTED_RUNTIME_OWNER = "skeleton/provider_runtime.py"
_REQUIRED_APPLICATION_SURFACES = {
    "backend/core/ai_provider.py",
    "skeleton/jeeves/providers.py",
    "backend/routes/image_generation.py",
    "backend/core/expressive_tts.py",
}
_PROVIDER_SECRETS = ("OPENAI_API_KEY", "EMERGENT_LLM_KEY")


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid JSON contract: {path}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"JSON contract must be an object: {path}")
    return payload


def _service_block(compose: str, service: str, next_service: str) -> str:
    marker = f"  {service}:\n"
    next_marker = f"\n  {next_service}:\n"
    start = compose.find(marker)
    if start < 0:
        return ""
    end = compose.find(next_marker, start + len(marker))
    if end < 0:
        return compose[start:]
    return compose[start:end]


def _declared_runtime_surfaces(contract: dict[str, Any]) -> list[dict[str, Any]]:
    surfaces = contract.get("provider_surfaces")
    if not isinstance(surfaces, list):
        return []
    return [
        item
        for item in surfaces
        if isinstance(item, dict)
        and item.get("family") == "runtime_model"
    ]


def _edge_owners(
    surfaces: list[dict[str, Any]],
    ownership_field: str,
) -> set[str]:
    return {
        str(item.get("owner"))
        for item in surfaces
        if item.get(ownership_field) is True
        and isinstance(item.get("owner"), str)
    }


def _source_uses_provider_registry_from_env(path: Path) -> bool:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, SyntaxError):
        return True
    names = {"ProviderRegistry"}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name == "ProviderRegistry":
                    names.add(alias.asname or alias.name)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not isinstance(func, ast.Attribute) or func.attr != "from_env":
            continue
        receiver = func.value
        if isinstance(receiver, ast.Name) and receiver.id in names:
            return True
        if (
            isinstance(receiver, ast.Attribute)
            and receiver.attr == "ProviderRegistry"
        ):
            return True
    return False


def _runtime_capability_errors() -> list[str]:
    try:
        from skeleton.provider_runtime import (
            OpenAIProviderAdapter,
            OpenAISyncProviderAdapter,
            ProviderRegistry,
        )
    except Exception as exc:
        return [f"canonical provider runtime import failed: {type(exc).__name__}"]

    errors: list[str] = []
    required_async = (
        "generate",
        "stream",
        "generate_image",
        "create_image_variation",
        "edit_image",
        "synthesize_speech",
    )
    for name in required_async:
        if not callable(getattr(OpenAIProviderAdapter, name, None)):
            errors.append(
                f"canonical async provider runtime missing capability: {name}"
            )
    if not callable(getattr(OpenAISyncProviderAdapter, "generate_sync", None)):
        errors.append("canonical synchronous provider runtime missing generate_sync")
    if not callable(getattr(ProviderRegistry, "from_env", None)):
        errors.append("canonical provider registry missing from_env")
    return errors


def validate_provider_surface_closure(
    repo_root: Path = ROOT,
) -> list[str]:
    errors: list[str] = []
    try:
        contract = _load_json(repo_root / "machine/ai_app_construction.json")
    except ValueError as exc:
        return [str(exc)]

    bootstrap_errors = validate_provider_bootstrap(repo_root)
    errors.extend(f"provider-bootstrap: {item}" for item in bootstrap_errors)
    boundary_errors = audit_repository(repo_root)
    errors.extend(f"provider-runtime-boundary: {item}" for item in boundary_errors)

    runtime_surfaces = _declared_runtime_surfaces(contract)
    if not runtime_surfaces:
        errors.append("no runtime_model provider surfaces declared")
        return errors

    for field in (
        "credential_owner",
        "network_transport_owner",
        "sdk_client_owner",
    ):
        owners = _edge_owners(runtime_surfaces, field)
        if owners != {_EXPECTED_RUNTIME_OWNER}:
            errors.append(
                f"runtime model {field} must be owned only by "
                f"{_EXPECTED_RUNTIME_OWNER}; found={sorted(owners)}"
            )

    canonical = next(
        (
            item
            for item in runtime_surfaces
            if item.get("owner") == _EXPECTED_RUNTIME_OWNER
        ),
        None,
    )
    if canonical is None:
        errors.append("canonical runtime_model provider surface is missing")
    elif canonical.get("surface_class") != "canonical_runtime":
        errors.append("canonical runtime_model owner has wrong surface_class")

    discovered = discover_provider_surfaces(repo_root)
    declared_by_owner = {
        str(item.get("owner")): item
        for item in contract.get("provider_surfaces", [])
        if isinstance(item, dict) and isinstance(item.get("owner"), str)
    }
    for owner, signals in discovered.items():
        declared = declared_by_owner.get(owner)
        if declared is None:
            errors.append(f"discovered provider surface is undeclared: {owner}")
            continue
        edges = set(signals.get("edge_classes", []))
        edge_to_field = {
            "credential": "credential_owner",
            "network_transport": "network_transport_owner",
            "sdk_client": "sdk_client_owner",
        }
        for edge, field in edge_to_field.items():
            if edge in edges and declared.get(field) is not True:
                errors.append(
                    f"discovered {edge} edge is not owned by declared surface: {owner}"
                )

    convergence = contract.get("provider_surface_convergence_blueprint")
    if not isinstance(convergence, dict):
        errors.append("provider_surface_convergence_blueprint is missing")
        application_surfaces: list[dict[str, Any]] = []
    else:
        application_surfaces = [
            item
            for item in convergence.get("application_isolation_surfaces", [])
            if isinstance(item, dict)
        ]

    declared_application_paths = {
        str(item.get("path"))
        for item in application_surfaces
        if isinstance(item.get("path"), str)
    }
    missing_application = sorted(
        _REQUIRED_APPLICATION_SURFACES - declared_application_paths
    )
    if missing_application:
        errors.append(
            "provider application isolation surfaces missing: "
            + ", ".join(missing_application)
        )

    for item in application_surfaces:
        relative = item.get("path")
        if not isinstance(relative, str):
            continue
        path = repo_root / relative
        if not path.is_file():
            errors.append(f"provider application surface missing: {relative}")
            continue
        source = path.read_text(encoding="utf-8")
        signals = _provider_surface_signals(path, source)
        edge_classes: set[str] = set()
        if signals["credential_markers"]:
            edge_classes.add("credential")
        if signals["sdk_imports"]:
            edge_classes.add("sdk_client")
        if _looks_like_provider_network_surface(path, source, signals):
            edge_classes.add("network_transport")
        forbidden = {
            str(value)
            for value in item.get("forbidden_edge_classes", [])
        }
        violations = sorted(edge_classes.intersection(forbidden))
        if violations:
            errors.append(
                f"application provider surface owns forbidden edges "
                f"{relative}: {', '.join(violations)}"
            )

    jeeves = repo_root / "skeleton/jeeves/providers.py"
    if jeeves.is_file():
        if _credential_environment_reads(jeeves):
            errors.append("Jeeves provider facade reads model credentials")
        if _provider_sdk_imports(jeeves):
            errors.append("Jeeves provider facade imports vendor model SDK")
        signals = _provider_surface_signals(
            jeeves,
            jeeves.read_text(encoding="utf-8"),
        )
        if _looks_like_provider_network_surface(
            jeeves,
            jeeves.read_text(encoding="utf-8"),
            signals,
        ):
            errors.append("Jeeves provider facade owns raw provider network transport")

    backend_root = repo_root / "backend"
    if backend_root.is_dir():
        activators = []
        for path in sorted(backend_root.rglob("*.py")):
            relative = path.relative_to(repo_root).as_posix()
            if (
                "/tests/" in "/" + relative
                or path.name.startswith("test_")
            ):
                continue
            if _source_uses_provider_registry_from_env(path):
                activators.append(relative)
        if activators:
            errors.append(
                "backend local ProviderRegistry.from_env activators remain: "
                + ", ".join(activators)
            )

    try:
        compose = (repo_root / "docker-compose.yml").read_text(
            encoding="utf-8"
        )
    except OSError as exc:
        errors.append(f"cannot read docker-compose.yml: {exc}")
    else:
        skeleton_block = _service_block(compose, "skeleton", "backend")
        backend_block = _service_block(compose, "backend", "frontend")
        for secret in _PROVIDER_SECRETS:
            marker = secret + "="
            if marker not in skeleton_block:
                errors.append(
                    f"engine process missing runtime provider credential: {secret}"
                )
            if marker in backend_block:
                errors.append(
                    f"backend process still receives runtime provider credential: {secret}"
                )

    if repo_root == ROOT:
        errors.extend(_runtime_capability_errors())

    return errors


def build_closure_receipt(
    repo_root: Path = ROOT,
    *,
    head_sha: str | None = None,
) -> dict[str, Any]:
    errors = validate_provider_surface_closure(repo_root)
    provider_receipt = build_provider_surface_evidence(
        repo_root,
        head_sha=head_sha,
        errors=validate_provider_bootstrap(repo_root),
    )
    contract = _load_json(repo_root / "machine/ai_app_construction.json")
    runtime_surfaces = _declared_runtime_surfaces(contract)
    return {
        "schema_version": 1,
        "gap": "gap-provider-surface-convergence",
        "head_sha": head_sha or provider_receipt.get("head_sha", "unknown"),
        "canonical_runtime_owner": _EXPECTED_RUNTIME_OWNER,
        "runtime_model_surfaces": [
            {
                "id": item.get("id"),
                "owner": item.get("owner"),
                "surface_class": item.get("surface_class"),
                "credential_owner": item.get("credential_owner"),
                "network_transport_owner": item.get("network_transport_owner"),
                "sdk_client_owner": item.get("sdk_client_owner"),
            }
            for item in runtime_surfaces
        ],
        "provider_surface_receipt": provider_receipt,
        "validation_errors": errors,
        "valid": not errors,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate runtime model-provider closure evidence."
    )
    parser.add_argument("--evidence-out", type=Path, default=None)
    parser.add_argument("--print-evidence", action="store_true")
    parser.add_argument("--head-sha", default=None)
    args = parser.parse_args(argv)

    receipt = build_closure_receipt(
        ROOT,
        head_sha=args.head_sha,
    )
    if args.evidence_out is not None:
        args.evidence_out.parent.mkdir(parents=True, exist_ok=True)
        args.evidence_out.write_text(
            json.dumps(receipt, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    if args.print_evidence:
        print(json.dumps(receipt, indent=2, sort_keys=True))
    if not receipt["valid"]:
        print("provider-surface-closure: rejected", file=sys.stderr)
        for error in receipt["validation_errors"]:
            print(f"  - {error}", file=sys.stderr)
        return 1
    print(
        "provider-surface-closure: OK "
        "(single runtime-model owner, SDK/network/credential/media isolation)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
