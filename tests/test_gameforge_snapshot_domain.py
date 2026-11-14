import math
import pytest

from skeleton.frontier.gameforge_snapshot import RuntimeSnapshot


def base():
    return dict(lifecycle="ready", dependencies_ready=True, active=0, budget_used=0, budget_capacity=4)


def test_snapshot_requires_real_lifecycle_and_dependency_state():
    values = base()
    values["lifecycle"] = ""
    with pytest.raises(TypeError):
        RuntimeSnapshot(**values)
    values = base()
    values["dependencies_ready"] = 1
    with pytest.raises(TypeError):
        RuntimeSnapshot(**values)  # type: ignore[arg-type]


def test_snapshot_rejects_non_finite_health():
    values = base()
    values["health"] = math.nan
    with pytest.raises(ValueError):
        RuntimeSnapshot(**values)
