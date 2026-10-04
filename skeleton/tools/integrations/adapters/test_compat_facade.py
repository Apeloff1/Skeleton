"""Regression coverage for TREE-040 adapter compatibility facades."""

from skeleton.integrations import adapters as legacy
from skeleton.integrations.adapters.client import ModelClient as LegacyModelClient
from skeleton.integrations.adapters.offline import OfflineProvider as LegacyOfflineProvider
from skeleton.integrations.adapters.tool_loop import ToolLoop as LegacyToolLoop
from skeleton.integrations.adapters.tools import ToolExecutor as LegacyToolExecutor
from skeleton.tools.integrations import adapters as canonical
from skeleton.tools.integrations.adapters.client import ModelClient
from skeleton.tools.integrations.adapters.offline import OfflineProvider
from skeleton.tools.integrations.adapters.tool_loop import ToolLoop
from skeleton.tools.integrations.adapters.tools import ToolExecutor


def test_package_facade_reexports_canonical_objects() -> None:
    assert legacy.ModelClient is canonical.ModelClient
    assert legacy.OfflineProvider is canonical.OfflineProvider
    assert legacy.ToolExecutor is canonical.ToolExecutor
    assert legacy.ToolLoop is canonical.ToolLoop


def test_submodule_facades_preserve_type_identity() -> None:
    assert LegacyModelClient is ModelClient
    assert LegacyOfflineProvider is OfflineProvider
    assert LegacyToolExecutor is ToolExecutor
    assert LegacyToolLoop is ToolLoop


def test_legacy_public_surface_matches_canonical_all() -> None:
    assert legacy.__all__ is canonical.__all__
    for name in canonical.__all__:
        assert getattr(legacy, name) is getattr(canonical, name)
