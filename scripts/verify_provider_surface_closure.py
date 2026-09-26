#!/usr/bin/env python3
"""Independent provider-surface closure verifier.

This verifier intentionally does not import the primary provider bootstrap or
runtime-boundary validators. It reconstructs provider ownership from the
machine contract and independently audits production Python source for vendor
SDK imports, provider credential reads, known provider URLs, and application
isolation violations.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import sys
from typing import Any, Iterable, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]
CONSTRUCTION_PATH = Path("machine/ai_app_construction.json")
PRODUCTION_ROOTS = ("backend", "skeleton")
SKIP_PARTS = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    "node_modules",
    "tests",
    "test",
    "testing",
}
SKIP_PREFIXES = (
    Path("skeleton/ai/research/external"),
    Path("skeleton/ai/research/legacy"),
)
VENDOR_SDK_ROOTS = {
    "openai",
    "anthropic",
    "cohere",
    "groq",
    "mistralai",
    "litellm",
}
GOOGLE_VENDOR_MODULES = {
    "google.genai",
    "google.generativeai",
}
CREDENTIAL_KEYS = {
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
PROVIDER_URLS = {
    "api.openai.com",
    "api.anthropic.com",
    "generativelanguage.googleapis.com",
    "api.groq.com",
    "api.mistral.ai",
    "api.cohere.ai",
}
ALLOWED_SURFACE_CLASSES = {
    "canonical_runtime",
    "provider_declaration",
    "noncredential_compatibility_facade",
    "automation_provider_explicitly_separate_and_receipt-gated",
}


class VerificationError(RuntimeError):
    """Independent provider-surface verification failed."""


def _load_contract(root: Path) -> dict[str, Any]:
    path = root / CONSTRUCTION_PATH
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise VerificationError(
            "machine/ai_app_construction.json is unavailable or invalid"
        ) from exc
    if not isinstance(payload, dict):
        raise VerificationError("construction contract must be an object")
    return payload


def _production_python_files(root: Path) -> Iterable[Path]:
    for root_name in PRODUCTION_ROOTS:
        base = root / root_name
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*.py")):
            rel = path.relative_to(root)
            if any(part in SKIP_PARTS for part in rel.parts):
                continue
            if any(rel == prefix or prefix in rel.parents for prefix in SKIP_PREFIXES):
                continue
            yield path


def _module_root(module: str) -> str:
    if module.startswith("google.genai"):
        return "google.genai"
    if module.startswith("google.generativeai"):
        return "google.generativeai"
    return module.split(".", 1)[0]


def _sdk_imports(tree: ast.AST) -> set[str]:
    found: set[str] = set()
    for node in ast.walk(tree):
        modules: list[str] = []
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.append(node.module)
        for module in modules:
            root = _module_root(module)
            if root in VENDOR_SDK_ROOTS or root in GOOGLE_VENDOR_MODULES:
                found.add(module)
    return found


def _constant_string(node: ast.AST | None) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _credential_reads(tree: ast.AST) -> set[str]:
    found: set[str] = set()
    os_aliases = {"os"}
    getenv_aliases: set[str] = set()
    environ_aliases: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "os":
                    os_aliases.add(alias.asname or "os")
        elif isinstance(node, ast.ImportFrom) and node.module == "os":
            for alias in node.names:
                if alias.name == "getenv":
                    getenv_aliases.add(alias.asname or alias.name)
                elif alias.name == "environ":
                    environ_aliases.add(alias.asname or alias.name)

    def is_environ(node: ast.AST) -> bool:
        if isinstance(node, ast.Name):
            return node.id in environ_aliases
        return (
            isinstance(node, ast.Attribute)
            and node.attr == "environ"
            and isinstance(node.value, ast.Name)
            and node.value.id in os_aliases
        )

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            direct = isinstance(func, ast.Name) and func.id in getenv_aliases
            module_getenv = (
                isinstance(func, ast.Attribute)
                and func.attr == "getenv"
                and isinstance(func.value, ast.Name)
                and func.value.id in os_aliases
            )
            environ_get = (
                isinstance(func, ast.Attribute)
                and func.attr == "get"
                and is_environ(func.value)
            )
            if (direct or module_getenv or environ_get) and node.args:
                value = _constant_string(node.args[0])
                if value in CREDENTIAL_KEYS:
                    found.add(value)
        elif isinstance(node, ast.Subscript) and is_environ(node.value):
            value = _constant_string(node.slice)
            if value in CREDENTIAL_KEYS:
                found.add(value)
    return found


def _provider_urls(tree: ast.AST) -> set[str]:
    found: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
            continue
        value = node.value.lower()
        for marker in PROVIDER_URLS:
            if marker in value:
                found.add(marker)
    return found


def _parse_source(path: Path) -> tuple[str, ast.AST]:
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
    except (OSError, UnicodeDecodeError, SyntaxError) as exc:
        raise VerificationError(
            f"cannot independently audit {path}: {type(exc).__name__}: {exc}"
        ) from exc
    return source, tree


def _surface_map(contract: Mapping[str, Any]) -> tuple[dict[str, dict[str, Any]], list[str]]:
    errors: list[str] = []
    raw = contract.get("provider_surfaces")
    if not isinstance(raw, list) or not raw:
        return {}, ["provider_surfaces must be a non-empty list"]

    by_owner: dict[str, dict[str, Any]] = {}
    seen_ids: set[str] = set()
    for index, item in enumerate(raw):
        prefix = f"provider_surfaces[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{prefix} must be an object")
            continue
        surface_id = item.get("id")
        owner = item.get("owner")
        surface_class = item.get("surface_class")
        if not isinstance(surface_id, str) or not surface_id.strip():
            errors.append(f"{prefix}.id must be non-empty")
            continue
        if surface_id in seen_ids:
            errors.append(f"duplicate provider surface id: {surface_id}")
        seen_ids.add(surface_id)
        if not isinstance(owner, str) or not owner.strip():
            errors.append(f"{prefix}.owner must be non-empty")
            continue
        if owner in by_owner:
            errors.append(f"provider owner declared more than once: {owner}")
            continue
        if surface_class not in ALLOWED_SURFACE_CLASSES:
            errors.append(f"{prefix}.surface_class is invalid: {surface_class!r}")

        credential_owner = item.get("credential_owner")
        network_owner = item.get("network_transport_owner")
        sdk_owner = item.get("sdk_client_owner")
        credential_bearing = item.get("credential_bearing")
        receipt_required = item.get("receipt_required")

        for field, value in (
            ("credential_owner", credential_owner),
            ("network_transport_owner", network_owner),
            ("sdk_client_owner", sdk_owner),
            ("credential_bearing", credential_bearing),
            ("receipt_required", receipt_required),
        ):
            if not isinstance(value, bool):
                errors.append(f"{prefix}.{field} must be boolean")

        if isinstance(credential_bearing, bool) and isinstance(credential_owner, bool):
            if credential_bearing != credential_owner:
                errors.append(
                    f"{prefix} credential_bearing must equal credential_owner"
                )
        if credential_bearing is True and receipt_required is not True:
            errors.append(
                f"{prefix} credential-bearing provider surface must require receipts"
            )

        declared_edges = item.get("discovery_edge_classes")
        if not isinstance(declared_edges, list):
            errors.append(f"{prefix}.discovery_edge_classes must be a list")
            declared_edges = []
        expected_edges = set()
        if credential_owner is True:
            expected_edges.add("credential")
        if network_owner is True:
            expected_edges.add("network_transport")
        if sdk_owner is True:
            expected_edges.add("sdk_client")
        if set(declared_edges) != expected_edges:
            errors.append(
                f"{prefix}.discovery_edge_classes does not match ownership flags"
            )

        by_owner[owner] = dict(item)

    canonical = by_owner.get("skeleton/provider_runtime.py")
    if canonical is None:
        errors.append("canonical provider runtime owner is missing")
    else:
        if canonical.get("surface_class") != "canonical_runtime":
            errors.append("canonical provider runtime has wrong surface_class")
        for field in (
            "credential_owner",
            "network_transport_owner",
            "sdk_client_owner",
            "receipt_required",
        ):
            if canonical.get(field) is not True:
                errors.append(f"canonical provider runtime must set {field}=true")
    return by_owner, errors


def _source_edges(tree: ast.AST) -> dict[str, list[str]]:
    return {
        "sdk_client": sorted(_sdk_imports(tree)),
        "credential": sorted(_credential_reads(tree)),
        "network_transport": sorted(_provider_urls(tree)),
    }


def _audit_application_isolation(
    root: Path,
    contract: Mapping[str, Any],
) -> list[str]:
    errors: list[str] = []
    blueprint = contract.get("provider_surface_convergence_blueprint")
    if not isinstance(blueprint, dict):
        return ["provider_surface_convergence_blueprint must be an object"]
    surfaces = blueprint.get("application_isolation_surfaces")
    if not isinstance(surfaces, list) or not surfaces:
        return ["application_isolation_surfaces must be a non-empty list"]

    for index, item in enumerate(surfaces):
        prefix = f"application_isolation_surfaces[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{prefix} must be an object")
            continue
        rel = item.get("path")
        if not isinstance(rel, str) or not rel.strip():
            errors.append(f"{prefix}.path must be non-empty")
            continue
        path = root / rel
        if not path.is_file():
            errors.append(f"application isolation path is missing: {rel}")
            continue
        source, tree = _parse_source(path)
        required = item.get("required_tokens")
        if not isinstance(required, list):
            errors.append(f"{prefix}.required_tokens must be a list")
            required = []
        for token in required:
            if not isinstance(token, str) or not token:
                errors.append(f"{prefix} has invalid required token")
            elif token not in source:
                errors.append(f"{rel} lost required delegation token: {token}")

        forbidden = item.get("forbidden_edge_classes")
        if not isinstance(forbidden, list):
            errors.append(f"{prefix}.forbidden_edge_classes must be a list")
            forbidden = []
        edges = _source_edges(tree)
        for edge_class in forbidden:
            values = edges.get(str(edge_class), [])
            if values:
                errors.append(
                    f"{rel} owns forbidden {edge_class} edges: {', '.join(values)}"
                )
    return errors


def verify_repository(root: Path = ROOT) -> dict[str, Any]:
    contract = _load_contract(root)
    owner_map, errors = _surface_map(contract)
    errors.extend(_audit_application_isolation(root, contract))

    scanned = 0
    discovered: list[dict[str, Any]] = []
    for path in _production_python_files(root):
        scanned += 1
        rel = path.relative_to(root).as_posix()
        _source, tree = _parse_source(path)
        edges = _source_edges(tree)
        active = {key for key, values in edges.items() if values}
        if not active:
            continue
        declared = owner_map.get(rel)
        discovered.append(
            {
                "path": rel,
                "edge_classes": sorted(active),
                "sdk_imports": edges["sdk_client"],
                "credential_reads": edges["credential"],
                "provider_urls": edges["network_transport"],
                "declared_surface_id": (
                    None if declared is None else declared.get("id")
                ),
            }
        )
        if declared is None:
            errors.append(
                f"undeclared provider-bearing production surface: {rel}: "
                + ", ".join(sorted(active))
            )
            continue
        allowed = set()
        if declared.get("credential_owner") is True:
            allowed.add("credential")
        if declared.get("network_transport_owner") is True:
            allowed.add("network_transport")
        if declared.get("sdk_client_owner") is True:
            allowed.add("sdk_client")
        forbidden = active - allowed
        if forbidden:
            errors.append(
                f"{rel} owns undeclared provider edges: "
                + ", ".join(sorted(forbidden))
            )

    declared_payload = [
        {
            "id": item.get("id"),
            "owner": owner,
            "surface_class": item.get("surface_class"),
            "credential_owner": item.get("credential_owner"),
            "network_transport_owner": item.get("network_transport_owner"),
            "sdk_client_owner": item.get("sdk_client_owner"),
            "receipt_required": item.get("receipt_required"),
        }
        for owner, item in sorted(owner_map.items())
    ]
    digest_bytes = json.dumps(
        declared_payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return {
        "schema_version": 1,
        "verifier": "independent-provider-surface-v1",
        "head_sha": os.environ.get("GITHUB_SHA", "").strip() or "unknown",
        "scanned_python_files": scanned,
        "declared_surface_digest": hashlib.sha256(digest_bytes).hexdigest(),
        "declared_surfaces": declared_payload,
        "discovered_provider_edges": discovered,
        "errors": errors,
        "valid": not errors,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-out", type=Path)
    parser.add_argument("--print-evidence", action="store_true")
    args = parser.parse_args(argv)

    try:
        receipt = verify_repository(ROOT)
    except VerificationError as exc:
        print(f"independent-provider-surface: rejected: {exc}", file=sys.stderr)
        return 1

    if args.evidence_out is not None:
        args.evidence_out.parent.mkdir(parents=True, exist_ok=True)
        args.evidence_out.write_text(
            json.dumps(receipt, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    if args.print_evidence:
        print(json.dumps(receipt, indent=2, sort_keys=True))

    if not receipt["valid"]:
        print("independent-provider-surface: rejected", file=sys.stderr)
        for error in receipt["errors"]:
            print(f"  - {error}", file=sys.stderr)
        return 1
    print(
        "independent-provider-surface: OK "
        f"(scanned={receipt['scanned_python_files']}, "
        f"provider_edges={len(receipt['discovered_provider_edges'])})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
