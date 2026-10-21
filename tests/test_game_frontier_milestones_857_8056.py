"""Smoke coverage for milestones 857-8056 (10x batch)."""
import importlib
from pathlib import Path


def _funcs(mod):
    return [f for f in dir(mod) if not f.startswith("_") and callable(getattr(mod, f))]


def test_sample_ends():
    for n in (857, 4000, 8056):
        mod = importlib.import_module(f"skeleton.jeeves.game_frontier_milestone_{n}")
        assert _funcs(mod)


def test_identity():
    mod = importlib.import_module("skeleton.jeeves.game_frontier_milestone_857")
    func = getattr(mod, _funcs(mod)[0])
    assert func(9) == 9


def test_count():
    root = Path("skeleton/jeeves")
    present = sum(1 for n in range(857, 8057) if (root / f"game_frontier_milestone_{n}.py").exists())
    assert present == 7200
