"""Regression coverage for stable Skeleton capability discovery."""

from __future__ import annotations

import importlib.util
import json

from skeleton.__main__ import main
from skeleton.application import CAPABILITY_MANIFEST_VERSION, capability_manifest


def test_capability_manifest_is_versioned_unique_and_resolvable() -> None:
    payload = capability_manifest()

    assert payload["schema_version"] == CAPABILITY_MANIFEST_VERSION == 1

    capabilities = payload["capabilities"]
    assert isinstance(capabilities, list)
    assert capabilities

    ids = [capability["id"] for capability in capabilities]
    modules = [capability["module"] for capability in capabilities]

    assert len(ids) == len(set(ids))
    assert len(modules) == len(set(modules))
    assert {"gameforge", "cortex", "jeeves", "organism", "social", "galaxy"} <= set(ids)

    for capability in capabilities:
        assert set(capability) == {"id", "module", "description"}
        assert capability["id"]
        assert capability["description"]
        assert importlib.util.find_spec(capability["module"]) is not None


def test_capabilities_cli_matches_python_api(capsys) -> None:
    assert main(["capabilities"]) == 0

    stdout = capsys.readouterr().out
    assert json.loads(stdout) == capability_manifest()
