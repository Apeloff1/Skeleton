from __future__ import annotations

import json
import re
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
    assert all(re.fullmatch(r"TREE-\d{3}", value) for value in ids)
    routes = [(item["source"], item["destination"]) for item in batches]
    assert len(routes) == len(set(routes))
    move_modes = {
        "move-with-shims",
        "move-with-shim",
        "facade-convergence-with-shims",
        "intra-domain-extraction-with-shims",
    }
    for item in batches:
        assert item["source"] != item["destination"]
        assert item["notes"]
        if item["mode"] == "taxonomy-classification":
            assert item["state"] == "classified"
            assert item["compatibility"] is None
            assert item["destination"].startswith(".machine/repository.toml ")
            assert (root / ".machine/repository.toml").is_file()
        else:
            assert item["mode"] in move_modes
            assert item["state"] in {"planned", "canonicalized"}
            assert item["destination"].startswith("skeleton/")
            assert item["compatibility"]
            if item["state"] == "canonicalized":
                assert (root / item["destination"]).exists(), item["id"]

        # Compound migrations enumerate modules or glob families. Each retained
        # source must still exist, including compatibility and classified roots.
        for expression in item["source"].split(" + "):
            match = re.search(r"\{([^}]+)\}", expression)
            patterns = (
                [expression[:match.start()] + member + expression[match.end():]
                 for member in match[1].split(",")]
                if match else [expression]
            )
            for pattern in patterns:
                assert not Path(pattern).is_absolute()
                assert ".." not in Path(pattern).parts
                assert any(root.glob(pattern.rstrip("/"))), (item["id"], pattern)
