#!/usr/bin/env python3
"""Validate the cross-service runtime supervision contract."""

from __future__ import annotations

import argparse
import json
from pathlib import Path, PurePosixPath
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = Path("machine/runtime_supervision.json")
MASTER = Path("machine/ai_master_plan.json")


class RuntimeSupervisionError(RuntimeError):
    pass


def _load(root: Path, relative: Path) -> dict[str, Any]:
    path = root / relative
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RuntimeSupervisionError(f"missing required file: {relative}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeSupervisionError(f"invalid JSON in {relative}: {exc}") from exc
    if not isinstance(data, dict):
        raise RuntimeSupervisionError(f"{relative} must contain an object")
    return data


def _repo_path(value: object) -> str:
    if not isinstance(value, str) or not value or "\x00" in value or "\\" in value:
        raise RuntimeSupervisionError(f"invalid repository path: {value!r}")
    pure = PurePosixPath(value)
    if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
        raise RuntimeSupervisionError(f"invalid repository path: {value!r}")
    return pure.as_posix()


def _require_symbols(root: Path, binding: dict[str, Any], label: str) -> int:
    path = _repo_path(binding.get("path"))
    target = root / path
    if not target.is_file():
        raise RuntimeSupervisionError(f"{label} source missing: {path}")
    text = target.read_text(encoding="utf-8")
    symbols = binding.get("required_symbols")
    if not isinstance(symbols, list) or not symbols:
        raise RuntimeSupervisionError(f"{label} required_symbols must be non-empty")
    if len(symbols) != len(set(symbols)):
        raise RuntimeSupervisionError(f"{label} required_symbols contains duplicates")
    for symbol in symbols:
        if not isinstance(symbol, str) or not symbol:
            raise RuntimeSupervisionError(f"{label} contains invalid required symbol")
        if symbol not in text:
            raise RuntimeSupervisionError(
                f"{label} required runtime symbol missing from {path}: {symbol!r}"
            )
    return len(symbols)


def validate(root: Path = ROOT) -> dict[str, Any]:
    root = root.resolve()
    contract = _load(root, CONTRACT)
    master = _load(root, MASTER)
    if contract.get("status") != "active":
        raise RuntimeSupervisionError("runtime supervision contract must be active")

    binding = contract.get("masterplan_binding")
    if not isinstance(binding, dict):
        raise RuntimeSupervisionError("masterplan_binding must be an object")
    volume = next(
        (v for v in master.get("volumes", []) if isinstance(v, dict) and v.get("key") == "VOL-004"),
        None,
    )
    if not isinstance(volume, dict) or binding.get("title") != volume.get("title"):
        raise RuntimeSupervisionError("runtime supervision must remain bound to VOL-004")
    gaps = binding.get("required_gap_texts")
    if not isinstance(gaps, list) or not gaps:
        raise RuntimeSupervisionError("VOL-004 gap bindings must be non-empty")
    for gap in gaps:
        if gap not in volume.get("gaps", []):
            raise RuntimeSupervisionError(f"VOL-004 masterplan gap drift: {gap!r}")

    sources = contract.get("sources")
    if not isinstance(sources, dict):
        raise RuntimeSupervisionError("sources must be an object")
    manifest_path = _repo_path(sources.get("runtime_manifest"))
    manifest = _load(root, Path(manifest_path))
    manifest_services = {
        item.get("name"): item
        for item in manifest.get("services", [])
        if isinstance(item, dict) and isinstance(item.get("name"), str)
    }

    services = contract.get("services")
    if not isinstance(services, list) or not services:
        raise RuntimeSupervisionError("services must be non-empty")
    service_ids: set[str] = set()
    symbol_count = 0
    for service in services:
        if not isinstance(service, dict):
            raise RuntimeSupervisionError("service supervision entry must be an object")
        service_id = service.get("service")
        if not isinstance(service_id, str) or not service_id or service_id in service_ids:
            raise RuntimeSupervisionError(f"invalid/duplicate supervised service {service_id!r}")
        service_ids.add(service_id)
        live = manifest_services.get(service_id)
        if not isinstance(live, dict):
            raise RuntimeSupervisionError(f"runtime manifest lacks supervised service {service_id}")

        if service.get("role") != live.get("role"):
            raise RuntimeSupervisionError(f"{service_id} role drift")
        if sorted(service.get("expected_dependencies", [])) != sorted(live.get("depends_on", [])):
            raise RuntimeSupervisionError(f"{service_id} dependency drift")
        if service.get("expected_health_path") != live.get("health_path"):
            raise RuntimeSupervisionError(f"{service_id} health-path drift")
        if service.get("expected_entrypoint") != live.get("entrypoint"):
            raise RuntimeSupervisionError(f"{service_id} entrypoint drift")

        groups = ["lifecycle_bindings", "connector_bindings", "cancellation_bindings"]
        if not any(isinstance(service.get(group), list) and service.get(group) for group in groups):
            raise RuntimeSupervisionError(f"{service_id} has no concrete supervision bindings")
        for group in groups:
            raw = service.get(group, [])
            if not isinstance(raw, list):
                raise RuntimeSupervisionError(f"{service_id}.{group} must be a list")
            for index, item in enumerate(raw):
                if not isinstance(item, dict):
                    raise RuntimeSupervisionError(f"{service_id}.{group}[{index}] must be an object")
                symbol_count += _require_symbols(
                    root,
                    item,
                    f"{service_id}.{group}[{index}]",
                )

    if service_ids != {"backend", "skeleton"}:
        raise RuntimeSupervisionError("supervision contract must cover backend and skeleton exactly")

    backend = next(s for s in services if s["service"] == "backend")
    engine = next(s for s in services if s["service"] == "skeleton")
    if "skeleton" not in backend["expected_dependencies"]:
        raise RuntimeSupervisionError("backend must depend on skeleton")
    if "mongo" not in backend["expected_dependencies"] or "mongo" not in engine["expected_dependencies"]:
        raise RuntimeSupervisionError("backend and skeleton must retain mongo dependency")
    if engine["service"] not in backend["expected_dependencies"]:
        raise RuntimeSupervisionError("application->engine dependency missing")

    invariants = contract.get("invariants")
    if not isinstance(invariants, list) or len(invariants) < 8:
        raise RuntimeSupervisionError("runtime supervision invariants are incomplete")

    return {
        "status": "valid",
        "service_count": len(services),
        "required_symbol_count": symbol_count,
        "masterplan_binding": "VOL-004",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        result = validate(Path(args.repo_root))
    except RuntimeSupervisionError as exc:
        print(f"runtime supervision: FAIL: {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(result, sort_keys=True))
    else:
        print(
            "runtime supervision: OK "
            f"({result['service_count']} services, "
            f"{result['required_symbol_count']} symbols)"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
