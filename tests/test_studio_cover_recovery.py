"""Historical cover recovery: source 8b3ef4653a1d65af8fadc1b1509e37bb3f1aa327."""
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PATHS = (
    "skeleton/jeeves/studio/cover_system.py",
    "skeleton/ai/agents/jeeves/studio/cover_system.py",
)


@pytest.mark.parametrize("path", PATHS)
@pytest.mark.parametrize(("pos", "zones", "expected"), [
    ((0,), [(1,)], 0.5),
    ((0,), [(2,)], 0.0),
    ((0,), [{"x": 1}], 0.5),
    ((0,), [{0: 1}], 0.5),
    ((0,), [None, (), {"x": "bad"}, (1,)], 0.5),
    ((0,), [(True,), {"x": False}], 0.0),
    ((True,), [(0,)], 0.0),
    ((), [(0,)], 0.0),
    ((0,), None, 0.0),
    ((float("nan"),), [(0,)], 0.0),
    ((0,), [(float("inf"),)], 0.0),
    ((10**400,), [(0.0,), (10**400,)], 0.5),
])
def test_cover_contract(path, pos, zones, expected):
    spec = importlib.util.spec_from_file_location("cover_recovery", ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.CoverSystem().in_cover(pos, zones) == expected


def test_cover_mirror_parity():
    assert (ROOT / PATHS[0]).read_bytes() == (ROOT / PATHS[1]).read_bytes()
