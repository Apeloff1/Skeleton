"""Generate a bounded machine workspace pack for external agents and tooling."""
from __future__ import annotations

import json
from pathlib import Path, PurePosixPath
import shutil

from .budgets import derive_zone_budgets
from .catalog import build_catalog
from .contracts import contract_map
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


def _safe_workspace_path(root: Path, relative: str) -> Path:
    rel = PurePosixPath(relative)
    if (
        rel.is_absolute()
        or not rel.parts
        or any(part in {"", ".", ".."} for part in rel.parts)
    ):
        raise ValueError("workspace artifact path is not canonical")
    candidate = root.joinpath(*rel.parts)
    parent = candidate.parent
    parent.mkdir(parents=True, exist_ok=True)
    if parent.is_symlink():
        raise ValueError("workspace artifact parent must not be a symlink")
    resolved_parent = parent.resolve(strict=True)
    if not resolved_parent.is_relative_to(root):
        raise ValueError("workspace artifact escapes workspace root")
    if candidate.is_symlink():
        raise ValueError("workspace artifact must not be a symlink")
    return candidate


def _write_json(root: Path, relative: str, payload: object) -> None:
    path = _safe_workspace_path(root, relative)
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
    if root.is_symlink():
        raise ValueError("workspace destination must not be a symlink")
    if root.exists():
        if not root.is_dir():
            raise ValueError("workspace destination must be a directory")
        if replace:
            shutil.rmtree(root)
        elif any(root.iterdir()):
            raise ValueError(
                "workspace destination must be empty when replace is disabled"
            )
    root.mkdir(parents=True, exist_ok=True)
    root = root.resolve(strict=True)

    written: list[str] = []
    manifest = _safe_workspace_path(root, "repository-manifest.json")
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
    }
    for filename, payload in artifacts.items():
        _write_json(root, filename, payload)
        written.append(filename)

    for shard in build_context_shards(model):
        filename = f"{shard.zone}.json"
        relative = f"shards/{filename}"
        _write_json(root, relative, shard.as_dict())
        written.append(relative)

    index = {
        "schema_version": 1,
        "repository_fingerprint": model.fingerprint,
        "files": sorted(written),
    }
    _write_json(root, "index.json", index)
    written.append("index.json")
    return tuple(sorted(written))
