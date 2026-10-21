"""Smoke coverage for milestones 8057-80056 (10x batch)."""
import importlib
from pathlib import Path


def _funcs(mod):
    return [f for f in dir(mod) if not f.startswith("_") and callable(getattr(mod, f))]


def test_sample_ends():
    for n in (8057, 40000, 80056):
        mod = importlib.import_module(f"skeleton.jeeves.game_frontier_milestone_{n}")
        assert _funcs(mod)


def test_identity():
    mod = importlib.import_module("skeleton.jeeves.game_frontier_milestone_8057")
    func = getattr(mod, _funcs(mod)[0])
    assert func(11) == 11


def test_count():
    root = Path("skeleton/jeeves")
    present = sum(1 for n in (8057, 40000, 80056) if (root / f"game_frontier_milestone_{n}.py").exists())
    assert present == 3
