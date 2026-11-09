#!/usr/bin/env python3
"""Validate P1 API registry coverage and optional compatibility against a baseline."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

from backend.core.api_contract_registry import (
    ApiContract,
    ApiContractError,
    CompatibilityClass,
    MigrationRule,
    evaluate_compatibility,
    registry_digest,
)


ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = Path("machine/p1_api_contract_registry.json")
RUNTIME_SCHEMAS_PATH = Path("machine/ai_runtime_schemas.json")
EXPECTED_TASK = "P1-PROD-01"
EXPECTED_ACCOUNTABILITY = "ACC-P1-PROD-01"
_METHODS = {"get", "post", "put", "patch", "delete", "head", "options"}


class RegistryValidationError(RuntimeError):
    pass


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RegistryValidationError(f"cannot read {path}") from exc


def _canonical_digest(value: Any) -> str:
    raw = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _join_path(*parts: str) -> str:
    chunks: list[str] = []
    for part in parts:
        if not isinstance(part, str):
            raise RegistryValidationError("path fragments must be strings")
        chunks.extend(piece for piece in part.split("/") if piece)
    return "/" + "/".join(chunks)


def _literal_router_prefix(source_path: Path) -> str:
    try:
        tree = ast.parse(source_path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError) as exc:
        raise RegistryValidationError(f"cannot parse route source {source_path}") from exc
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(target, ast.Name) and target.id == "router" for target in node.targets):
            continue
        call = node.value
        if not isinstance(call, ast.Call):
            continue
        func = call.func
        if not (isinstance(func, ast.Name) and func.id == "APIRouter"):
            continue
        for keyword in call.keywords:
            if (
                keyword.arg == "prefix"
                and isinstance(keyword.value, ast.Constant)
                and isinstance(keyword.value.value, str)
            ):
                return keyword.value.value
    raise RegistryValidationError("route module lacks literal APIRouter prefix")


def _registered_mount_prefix(registry_path: Path, route_import: str) -> str:
    try:
        tree = ast.parse(registry_path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError) as exc:
        raise RegistryValidationError(
            f"cannot parse route registry {registry_path}"
        ) from exc
    matches: list[str] = []
    for node in tree.body:
        if not isinstance(node, ast.AnnAssign) or not isinstance(node.target, ast.Name):
            continue
        if node.target.id not in {"KNOWN_ROUTES", "KNOWN_ROUTES_WITH_PREFIX"}:
            continue
        if not isinstance(node.value, (ast.List, ast.Tuple)):
            continue
        for item in node.value.elts:
            if not isinstance(item, ast.Tuple) or len(item.elts) < 2:
                continue
            values: list[Any] = []
            for element in item.elts:
                if isinstance(element, ast.Constant):
                    values.append(element.value)
                else:
                    values.append(None)
            if values[0] != route_import:
                continue
            prefix = values[2] if len(values) >= 3 else ""
            if not isinstance(prefix, str):
                raise RegistryValidationError(
                    f"{route_import}: route mount prefix must be literal"
                )
            matches.append(prefix)
    if len(matches) != 1:
        raise RegistryValidationError(
            f"{route_import}: expected exactly one route registry entry"
        )
    return matches[0]


def _decorator_inventory(
    source_path: Path,
    *,
    mount_prefix: str,
    router_prefix: str,
) -> set[tuple[str, str]]:
    try:
        tree = ast.parse(source_path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError) as exc:
        raise RegistryValidationError(f"cannot parse route source {source_path}") from exc

    found: set[tuple[str, str]] = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call):
                continue
            func = decorator.func
            if (
                not isinstance(func, ast.Attribute)
                or not isinstance(func.value, ast.Name)
                or func.value.id != "router"
                or func.attr not in _METHODS
                or not decorator.args
            ):
                continue
            raw_path = decorator.args[0]
            if not isinstance(raw_path, ast.Constant) or not isinstance(raw_path.value, str):
                raise RegistryValidationError(
                    "P1 API inventory requires literal router decorator paths"
                )
            found.add(
                (
                    func.attr.upper(),
                    _join_path(mount_prefix, router_prefix, raw_path.value),
                )
            )
    return found


def _shape_digest(
    row: dict[str, Any],
    *,
    prefix: str,
    runtime_records: dict[str, Any],
) -> str:
    ref_key = f"{prefix}_schema_ref"
    shape_key = f"{prefix}_shape"
    has_ref = ref_key in row
    has_shape = shape_key in row
    if has_ref == has_shape:
        raise RegistryValidationError(
            f"{row.get('contract_id', '?')}: exactly one of {ref_key}/{shape_key} is required"
        )
    if has_ref:
        name = row[ref_key]
        if not isinstance(name, str) or name not in runtime_records:
            raise RegistryValidationError(
                f"{row.get('contract_id', '?')}: unknown runtime schema {name!r}"
            )
        return _canonical_digest(
            {
                "catalog": str(RUNTIME_SCHEMAS_PATH),
                "record": name,
                "schema": runtime_records[name],
            }
        )
    return _canonical_digest({"inline_shape": row[shape_key]})


def _load_contracts(
    root: Path,
    registry_path: Path,
) -> tuple[dict[str, Any], tuple[ApiContract, ...], tuple[MigrationRule, ...]]:
    registry = _load_json(root / registry_path)
    runtime = _load_json(root / RUNTIME_SCHEMAS_PATH)
    if not isinstance(registry, dict) or not isinstance(runtime, dict):
        raise RegistryValidationError("registry/schema roots must be objects")
    if registry.get("schema_version") != 1:
        raise RegistryValidationError("registry schema_version must equal 1")
    if registry.get("task_id") != EXPECTED_TASK:
        raise RegistryValidationError("registry task_id drift")
    if registry.get("accountability_ref") != EXPECTED_ACCOUNTABILITY:
        raise RegistryValidationError("registry accountability_ref drift")
    records = runtime.get("records")
    if not isinstance(records, dict):
        raise RegistryValidationError("runtime schema records must be an object")

    rows = registry.get("contracts")
    if not isinstance(rows, list) or not rows:
        raise RegistryValidationError("registry contracts must be non-empty")
    allowed = {
        "contract_id",
        "version",
        "method",
        "path",
        "producer",
        "consumers",
        "request_schema_ref",
        "request_shape",
        "response_schema_ref",
        "response_shape",
        "transport",
        "tenant_scoped",
        "idempotent",
    }
    contracts: list[ApiContract] = []
    for row in rows:
        if not isinstance(row, dict):
            raise RegistryValidationError("contract entries must be objects")
        unknown = set(row) - allowed
        if unknown:
            raise RegistryValidationError(
                f"{row.get('contract_id', '?')}: unknown fields {sorted(unknown)}"
            )
        contracts.append(
            ApiContract(
                contract_id=row["contract_id"],
                version=row["version"],
                method=row["method"],
                path=row["path"],
                producer=row["producer"],
                consumers=tuple(row["consumers"]),
                request_schema_digest=_shape_digest(
                    row,
                    prefix="request",
                    runtime_records=records,
                ),
                response_schema_digest=_shape_digest(
                    row,
                    prefix="response",
                    runtime_records=records,
                ),
                tenant_scoped=row["tenant_scoped"],
                idempotent=row["idempotent"],
            )
        )

    migrations_raw = registry.get("migrations", [])
    if not isinstance(migrations_raw, list):
        raise RegistryValidationError("migrations must be a list")
    migrations: list[MigrationRule] = []
    for row in migrations_raw:
        if not isinstance(row, dict):
            raise RegistryValidationError("migration entries must be objects")
        migrations.append(
            MigrationRule(
                contract_id=row["contract_id"],
                from_version=row["from_version"],
                to_version=row["to_version"],
                compatibility=CompatibilityClass(row["compatibility"]),
                migration_id=row["migration_id"],
                expires_at_epoch=row.get("expires_at_epoch"),
            )
        )
    return registry, tuple(contracts), tuple(migrations)


def validate_repository(
    root: Path = ROOT,
    *,
    registry_path: Path = REGISTRY_PATH,
) -> dict[str, Any]:
    registry, contracts, migrations = _load_contracts(root, registry_path)
    scope = registry.get("scope")
    if not isinstance(scope, dict):
        raise RegistryValidationError("registry scope must be an object")
    source_rel = scope.get("route_module")
    registry_rel = scope.get("route_registry_module")
    route_import = scope.get("route_import")
    if not isinstance(source_rel, str):
        raise RegistryValidationError("scope.route_module must be a string")
    if not isinstance(registry_rel, str):
        raise RegistryValidationError("scope.route_registry_module must be a string")
    if not isinstance(route_import, str):
        raise RegistryValidationError("scope.route_import must be a string")
    source_path = root / source_rel
    actual_router_prefix = _literal_router_prefix(source_path)
    actual_mount_prefix = _registered_mount_prefix(
        root / registry_rel,
        route_import,
    )
    if scope.get("router_prefix") != actual_router_prefix:
        raise RegistryValidationError(
            "machine router_prefix does not match APIRouter declaration"
        )
    if scope.get("mount_prefix") != actual_mount_prefix:
        raise RegistryValidationError(
            "machine mount_prefix does not match route registry"
        )
    declared = {(item.method, item.path) for item in contracts}
    actual = _decorator_inventory(
        source_path,
        mount_prefix=actual_mount_prefix,
        router_prefix=actual_router_prefix,
    )
    if scope.get("require_complete_decorator_inventory") is not True:
        raise RegistryValidationError(
            "bounded P1 route-module inventory must be complete"
        )
    if declared != actual:
        missing = sorted(actual - declared)
        stale = sorted(declared - actual)
        raise RegistryValidationError(
            f"route inventory drift: missing={missing} stale={stale}"
        )
    return {
        "schema_version": 1,
        "task_id": EXPECTED_TASK,
        "accountability_ref": EXPECTED_ACCOUNTABILITY,
        "contract_count": len(contracts),
        "migration_count": len(migrations),
        "registry_digest": registry_digest(contracts),
        "route_inventory": [f"{method} {path}" for method, path in sorted(actual)],
        "valid": True,
    }


def compare_registries(
    root: Path,
    *,
    baseline_path: Path,
    candidate_path: Path = REGISTRY_PATH,
    observed_at_epoch: int,
) -> dict[str, Any]:
    _, baseline, _ = _load_contracts(root, baseline_path)
    _, candidate, migrations = _load_contracts(root, candidate_path)
    decision = evaluate_compatibility(
        baseline,
        candidate,
        migrations=migrations,
        observed_at_epoch=observed_at_epoch,
    )
    payload = {
        "accepted": decision.accepted,
        "baseline_digest": decision.baseline_digest,
        "candidate_digest": decision.candidate_digest,
        "breaking": list(decision.breaking),
        "incompatible": list(decision.incompatible),
        "additive": list(decision.additive),
        "unchanged": list(decision.unchanged),
        "task_id": decision.task_id,
        "accountability_id": decision.accountability_id,
        "decision_digest": decision.decision_digest,
    }
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, default=REGISTRY_PATH)
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--observed-at-epoch", type=int, default=0)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--print-summary", action="store_true")
    args = parser.parse_args(argv)
    try:
        payload: dict[str, Any] = {
            "registry": validate_repository(ROOT, registry_path=args.registry)
        }
        if args.baseline is not None:
            comparison = compare_registries(
                ROOT,
                baseline_path=args.baseline,
                candidate_path=args.registry,
                observed_at_epoch=args.observed_at_epoch,
            )
            payload["compatibility"] = comparison
            if comparison["accepted"] is not True:
                raise RegistryValidationError(
                    "candidate API registry is not backward compatible"
                )
        if args.out is not None:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(
                json.dumps(payload, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        if args.print_summary:
            print(json.dumps(payload, indent=2, sort_keys=True))
        return 0
    except (RegistryValidationError, ApiContractError, KeyError, TypeError, ValueError) as exc:
        print(f"P1 API registry: rejected: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
