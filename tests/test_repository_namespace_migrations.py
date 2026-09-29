from __future__ import annotations

import json
from pathlib import Path


def test_deployment_compatibility_symbols_are_canonical_identities() -> None:
    from skeleton.deploy.strategies.blue_green import BlueGreenDeployer as canonical
    from skeleton.deployment.blue_green import BlueGreenDeployer as legacy
    assert legacy is canonical

    from skeleton.deploy.strategies.canary import CanaryController as canonical_canary
    from skeleton.deployment.canary import CanaryController as legacy_canary
    assert legacy_canary is canonical_canary


def test_context_compatibility_symbols_are_canonical_identities() -> None:
    from skeleton.context.domains import ContextFabric as canonical
    from skeleton.contexts import ContextFabric as legacy
    assert legacy is canonical

    from skeleton.context.domains.workorder import WorkOrderEngine as canonical_workorder
    from skeleton.contexts.workorder import WorkOrderEngine as legacy_workorder
    assert legacy_workorder is canonical_workorder


def test_repository_migration_plan_is_unique_and_canonical() -> None:
    root = Path(__file__).resolve().parents[1]
    payload = json.loads((root / "machine" / "repository_migration_plan.json").read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1
    batches = payload["batches"]
    ids = [item["id"] for item in batches]
    assert len(ids) == len(set(ids))
    for item in batches:
        assert item["source"].startswith("skeleton/")
        assert item["destination"].startswith("skeleton/")
        assert item["source"] != item["destination"]
        assert item["state"] in {"planned", "canonicalized"}
        assert item["mode"] == "move-with-shims"
