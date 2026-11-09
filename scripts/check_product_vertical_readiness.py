#!/usr/bin/env python3
"""Validate S-grade acceptance evidence for every canonical product vertical.

This is an acceptance-control validator, not another runtime readiness owner.
Live readiness remains derived by ``backend/core/capability_readiness.py``.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REGISTRY = Path("machine/product_vertical_readiness.json")
ARCHITECTURE = Path("machine/architecture.json")
CATALOG = Path("frontend/src/product/productCatalog.ts")
KERNEL = Path("backend/core/product_kernel.py")
POLICY = Path("backend/core/canonical_product_policy.py")
EXECUTORS = Path("backend/core/product_default_executors.py")
REQUIRED_DIMENSIONS = (
    "product_surface",
    "real_data_and_state",
    "complete_actions",
    "authority_and_provenance",
    "failure_and_recovery",
    "observability",
    "vertical_validation",
)


def _json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ValueError(f"missing contract: {path}") from None
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON {path}: {exc}") from None
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain an object")
    return value


def _repo_path(value: object) -> str:
    if not isinstance(value, str) or not value or "\\" in value or "\0" in value:
        raise ValueError("must be a non-empty repository-relative POSIX path")
    path = PurePosixPath(value)
    if path.is_absolute() or path.as_posix() != value or any(p in {"", ".", ".."} for p in path.parts):
        raise ValueError("must be normalized and repository-relative")
    return value


def _kernel(root: Path) -> dict[str, tuple[str, str]]:
    tree = ast.parse((root / KERNEL).read_text(encoding="utf-8"))
    result: dict[str, tuple[str, str]] = {}
    for node in tree.body:
        if not isinstance(node, ast.AnnAssign) or not isinstance(node.target, ast.Name) or node.target.id != "CAPABILITIES":
            continue
        if not isinstance(node.value, ast.Tuple):
            break
        for item in node.value.elts:
            if not isinstance(item, ast.Call) or len(item.args) < 4:
                raise ValueError("product kernel capability must use literal Capability calls")
            capability_id = ast.literal_eval(item.args[0])
            pillar_node = item.args[1]
            pillar = pillar_node.attr.lower() if isinstance(pillar_node, ast.Attribute) else ""
            prefixes = ast.literal_eval(item.args[3])
            if not isinstance(capability_id, str) or not pillar or not isinstance(prefixes, tuple) or not prefixes:
                raise ValueError("invalid product kernel capability declaration")
            if capability_id in result:
                raise ValueError(f"duplicate product kernel vertical: {capability_id}")
            result[capability_id] = (pillar, prefixes[0])
        return result
    raise ValueError("CAPABILITIES declaration not found in product kernel")


def _policy(root: Path) -> dict[str, tuple[str, ...]]:
    tree = ast.parse((root / POLICY).read_text(encoding="utf-8"))
    result: dict[str, tuple[str, ...]] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name) or node.func.id != "CanonicalDomainPolicy":
            continue
        if len(node.args) != 2:
            raise ValueError("canonical policy must use domain/action literal pairs")
        domain, actions = ast.literal_eval(node.args[0]), ast.literal_eval(node.args[1])
        if domain in result:
            raise ValueError(f"duplicate canonical policy vertical: {domain}")
        result[domain] = tuple(actions)
    return result


def _executor_bindings(root: Path) -> set[tuple[str, str]]:
    tree = ast.parse((root / EXECUTORS).read_text(encoding="utf-8"))
    bindings: list[tuple[str, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute) or node.func.attr != "register":
            continue
        if len(node.args) < 2:
            continue
        try:
            domain, action = ast.literal_eval(node.args[0]), ast.literal_eval(node.args[1])
        except (ValueError, TypeError):
            continue
        if isinstance(domain, str) and isinstance(action, str):
            bindings.append((domain, action))
    if len(bindings) != len(set(bindings)):
        raise ValueError("duplicate canonical executor binding")
    return set(bindings)


def _catalog(root: Path) -> dict[str, tuple[str, str, tuple[str, ...]]]:
    source = (root / CATALOG).read_text(encoding="utf-8")
    block = re.compile(
        r"(?ms)^  \{\n    id: '([^']+)'.*?^    pillar: '([^']+)'.*?"
        r"^    backendSurface: '([^']+)',.*?^    actions: \[(.*?)^    \],\n^  \},"
    )
    result: dict[str, tuple[str, str, tuple[str, ...]]] = {}
    for capability_id, pillar, surface, actions_block in block.findall(source):
        actions = tuple(re.findall(r"operation: '([^']+)'", actions_block))
        result[capability_id] = (pillar, surface, actions)
    if not result:
        raise ValueError("canonical product catalog could not be parsed")
    return result


def validate(root: Path = ROOT) -> tuple[list[str], dict[str, Any]]:
    errors: list[str] = []
    try:
        registry = _json(root / REGISTRY)
        architecture = _json(root / ARCHITECTURE)
        kernel, policy, bindings, catalog = _kernel(root), _policy(root), _executor_bindings(root), _catalog(root)
    except (OSError, SyntaxError, ValueError) as exc:
        return [str(exc)], {}

    if registry.get("schema_version") != "skeleton.product_vertical_readiness.v1":
        errors.append("registry schema_version must be skeleton.product_vertical_readiness.v1")
    if registry.get("status") != "active":
        errors.append("registry status must be active")
    if registry.get("architecture_tag") != architecture.get("architecture_tag"):
        errors.append("registry architecture_tag does not match canonical architecture")

    grade = registry.get("grade_contract")
    if not isinstance(grade, dict) or grade.get("target") != "S":
        errors.append("grade contract target must be S")
    elif grade.get("required_dimensions") != list(REQUIRED_DIMENSIONS):
        errors.append("grade contract dimensions must match the fail-closed S-grade contract")

    verticals = registry.get("verticals")
    if not isinstance(verticals, list):
        return errors + ["registry verticals must be a list"], {}
    rows = {row.get("vertical_id"): row for row in verticals if isinstance(row, dict)}
    canonical = set(kernel) | set(policy) | set(catalog)
    if set(rows) != canonical or set(kernel) != set(policy) or set(kernel) != set(catalog):
        errors.append(
            f"vertical inventory drift: registry={sorted(rows)} kernel={sorted(kernel)} "
            f"policy={sorted(policy)} catalog={sorted(catalog)}"
        )

    evidence_files: set[str] = set()
    for vertical_id in sorted(canonical):
        row = rows.get(vertical_id)
        if not isinstance(row, dict):
            continue
        label = f"verticals[{vertical_id}]"
        if row.get("target_grade") != "S" or row.get("qualification_state") != "contract_qualified":
            errors.append(f"{label} must be S-targeted and contract_qualified")
        if row.get("runtime_ready_claim") is not False:
            errors.append(f"{label} must not make a static runtime readiness claim")
        owner = row.get("owner")
        pillar, kernel_surface = kernel[vertical_id]
        cat_pillar, cat_surface, cat_actions = catalog[vertical_id]
        if not isinstance(owner, dict) or owner.get("kernel") != KERNEL.as_posix() or owner.get("pillar") != pillar:
            errors.append(f"{label} owner/pillar drift")
        if pillar != cat_pillar or row.get("backend_surface") != cat_surface or cat_surface != kernel_surface:
            errors.append(f"{label} product surface drift")
        operations = row.get("governed_operations")
        if operations != list(policy[vertical_id]) or tuple(operations or ()) != cat_actions:
            errors.append(f"{label} governed operation drift")
        for action in policy[vertical_id]:
            if (vertical_id, action) not in bindings:
                errors.append(f"{label} missing executor binding for {action}")

        evidence = row.get("evidence")
        if not isinstance(evidence, dict) or set(evidence) != set(REQUIRED_DIMENSIONS):
            errors.append(f"{label} must provide exactly every S-grade evidence dimension")
            continue
        for dimension in REQUIRED_DIMENSIONS:
            paths = evidence.get(dimension)
            if not isinstance(paths, list) or not paths:
                errors.append(f"{label}.{dimension} must contain evidence paths")
                continue
            if dimension == "vertical_validation" and not any(str(p).startswith(("tests/", "backend/tests/")) for p in paths):
                errors.append(f"{label}.{dimension} must include executable test evidence")
            for index, raw in enumerate(paths):
                try:
                    path = _repo_path(raw)
                except ValueError as exc:
                    errors.append(f"{label}.{dimension}[{index}] {exc}")
                    continue
                evidence_files.add(path)
                target = root / path
                if not target.is_file():
                    errors.append(f"{label}.{dimension} missing evidence file: {path}")

        readiness = row.get("runtime_readiness")
        if not isinstance(readiness, dict) or readiness.get("source") != "backend/core/capability_readiness.py":
            errors.append(f"{label} must delegate live readiness to the canonical evaluator")

    payload = {
        "schema_version": registry.get("schema_version"),
        "registry_version": registry.get("registry_version"),
        "target_grade": "S",
        "vertical_count": len(rows),
        "operation_count": sum(len(actions) for actions in policy.values()),
        "evidence_file_count": len(evidence_files),
        "contract_qualified": not errors,
    }
    payload["attestation_sha256"] = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return errors, payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args()
    errors, report = validate()
    if args.as_json:
        print(json.dumps({**report, "errors": errors}, indent=2, sort_keys=True))
    elif errors:
        print(f"product-vertical-readiness: FAIL ({len(errors)} issue(s))", file=sys.stderr)
        for error in errors[:100]:
            print(f"  - {error}", file=sys.stderr)
    else:
        print(
            "product-vertical-readiness: OK "
            f"({report['vertical_count']} verticals, {report['operation_count']} governed operations, "
            f"{report['evidence_file_count']} evidence files; runtime readiness remains dependency-evaluated)"
        )
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
