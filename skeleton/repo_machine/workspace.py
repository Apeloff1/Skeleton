"""Generate a bounded machine workspace pack for external agents and tooling."""
from __future__ import annotations

import json
from pathlib import Path
import shutil

from .budgets import derive_zone_budgets
from .catalog import build_catalog
from .contracts import contract_map
from .architecture_layers import derive_architecture_layers
from .context_budget import allocate_context
from .coordinator import build_coordinator_snapshot
from .debt import debt_register
from .docs_map import documentation_coverage
from .naming import analyze_naming
from .package_graph import discover_package_units
from .refactor import plan_refactors
from .selfcheck import run_selfcheck
from .growth import growth_recommendations
from .health import repository_health
from .hotspots import structural_hotspots
from .manifest import save_manifest
from .metrics import structural_metrics
from .model import RepositoryModel
from .reorganize import propose_reorganization
from .shards import build_context_shards
from .steward import select_steward_plan
from .config import MachineConfig


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def generate_workspace(
    model: RepositoryModel,
    config: MachineConfig,
    destination: str | Path,
    *,
    replace: bool = True,
) -> tuple[str, ...]:
    root = Path(destination)
    if root.exists() and replace:
        shutil.rmtree(root)
    root.mkdir(parents=True, exist_ok=True)

    written: list[str] = []
    manifest = root / "repository-manifest.json"
    save_manifest(model, manifest)
    written.append(manifest.name)

    artifacts = {
        "health.json": repository_health(model).as_dict(),
        "metrics.json": structural_metrics(model).as_dict(),
        "catalog.json": build_catalog(model).as_dict(),
        "contracts.json": contract_map(model),
        "budgets.json": {
            "zones": [item.as_dict() for item in derive_zone_budgets(model)]
        },
        "hotspots.json": {
            "hotspots": [item.as_dict() for item in structural_hotspots(model)]
        },
        "growth.json": {
            "recommendations": [
                item.as_dict()
                for item in growth_recommendations(model)
            ]
        },
        "reorganization.json": {
            "proposals": [
                item.as_dict()
                for item in propose_reorganization(model, config)
            ]
        },
        "steward-plan.json": select_steward_plan(model).as_dict(),
        "coordinator.json": build_coordinator_snapshot(
            model,
            config,
        ).as_dict(),
        "architecture-layers.json": derive_architecture_layers(model).as_dict(),
        "context-budgets.json": {
            "allocations": [
                item.as_dict()
                for item in allocate_context(model)
            ]
        },
        "debt.json": {
            "items": [
                item.as_dict()
                for item in debt_register(model)
            ]
        },
        "documentation.json": {
            "coverage": [
                item.as_dict()
                for item in documentation_coverage(model)
            ]
        },
        "packages.json": {
            "packages": [
                item.as_dict()
                for item in discover_package_units(model)
            ]
        },
        "naming.json": {
            "findings": [
                item.as_dict()
                for item in analyze_naming(model)
            ]
        },
        "refactors.json": {
            "plans": [
                item.as_dict()
                for item in plan_refactors(model)
            ]
        },
        "selfcheck.json": {
            "findings": [
                item.as_dict()
                for item in run_selfcheck(model, config)
            ]
        },
    }
    for filename, payload in artifacts.items():
        _write_json(root / filename, payload)
        written.append(filename)

    shards_root = root / "shards"
    for shard in build_context_shards(model):
        filename = f"{shard.zone}.json"
        _write_json(shards_root / filename, shard.as_dict())
        written.append(f"shards/{filename}")

    index = {
        "schema_version": 1,
        "repository_fingerprint": model.fingerprint,
        "files": sorted(written),
    }
    _write_json(root / "index.json", index)
    written.append("index.json")
    return tuple(sorted(written))
