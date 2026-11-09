"""Swarm snapshots never import/execute arbitrary caller-provided modules."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from skeleton.gate_plane.agent_edge.swarm_adapter import (
    CallableSwarmDirectory,
    DEFAULT_SWARM_FUNCTION,
    DEFAULT_SWARM_MODULE,
    ModuleSwarmDirectory,
)


@pytest.mark.parametrize(
    ("module", "function"),
    [
        ("os", DEFAULT_SWARM_FUNCTION),
        ("skeleton.swarm.unknown", DEFAULT_SWARM_FUNCTION),
        (DEFAULT_SWARM_MODULE, "other"),
        (DEFAULT_SWARM_MODULE, "__getattribute__"),
        ("", ""),
    ],
)
def test_unreviewed_module_or_function_never_imported(module: str, function: str):
    provider = ModuleSwarmDirectory(module=module, function=function)
    with patch("skeleton.gate_plane.agent_edge.swarm_adapter.importlib.import_module") as importer:
        with pytest.raises(ValueError, match="unknown swarm provider"):
            provider.snapshot()
    importer.assert_not_called()


def test_default_provider_uses_literal_reviewed_import_and_function():
    result = {"agents": [{"agent_id": "swarm-1", "capabilities": ["work"]}]}
    mock_mod = SimpleNamespace(capabilities=lambda: result)
    with patch("skeleton.gate_plane.agent_edge.swarm_adapter.importlib.import_module",
               return_value=mock_mod) as importer:
        assert ModuleSwarmDirectory().snapshot() == result
    importer.assert_called_once_with("skeleton.swarm.capabilities")


def test_non_mapping_builtin_provider_result_fails_closed():
    with patch("skeleton.gate_plane.agent_edge.swarm_adapter.importlib.import_module",
               return_value=SimpleNamespace(capabilities=lambda: [])):
        with pytest.raises(TypeError, match="did not return a mapping"):
            ModuleSwarmDirectory().snapshot()


def test_explicit_custom_provider_can_use_injected_callable():
    assert CallableSwarmDirectory(lambda: {"agents": []}).snapshot() == {"agents": []}
