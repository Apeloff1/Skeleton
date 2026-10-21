"""Smoke coverage for milestones 65-136."""
import importlib


def _funcs(mod):
    return [f for f in dir(mod) if not f.startswith("_") and callable(getattr(mod, f))]


def test_all_import():
    for n in range(65, 137):
        mod = importlib.import_module(f"skeleton.jeeves.game_frontier_milestone_{n}")
        assert _funcs(mod), f"milestone {n} has no function"


def test_sample_callable():
    mod = importlib.import_module("skeleton.jeeves.game_frontier_milestone_65")
    func = getattr(mod, _funcs(mod)[0])
    assert func(1) == 1


def test_ends():
    for n in (65, 100, 136):
        mod = importlib.import_module(f"skeleton.jeeves.game_frontier_milestone_{n}")
        assert _funcs(mod)
