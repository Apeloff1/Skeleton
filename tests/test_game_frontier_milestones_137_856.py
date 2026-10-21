"""Smoke coverage for milestones 137-856 (10x batch)."""
import importlib


def _funcs(mod):
    return [f for f in dir(mod) if not f.startswith("_") and callable(getattr(mod, f))]


def test_sample_ends():
    for n in (137, 400, 856):
        mod = importlib.import_module(f"skeleton.jeeves.game_frontier_milestone_{n}")
        assert _funcs(mod)


def test_identity():
    mod = importlib.import_module("skeleton.jeeves.game_frontier_milestone_137")
    func = getattr(mod, _funcs(mod)[0])
    assert func(7) == 7


def test_count():
    # Spot-check that the range is present without importing all 720.
    import os
    from pathlib import Path
    root = Path("skeleton/jeeves")
    present = sum(1 for n in range(137, 857) if (root / f"game_frontier_milestone_{n}.py").exists())
    assert present == 720
