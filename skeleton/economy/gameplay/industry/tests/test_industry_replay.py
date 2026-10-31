"""Replay determinism: same script, same digest; refusals recorded."""

from __future__ import annotations

from skeleton.economy.gameplay.industry import replay
from skeleton.economy.gameplay.industry.tests.conftest import build_system

SCRIPT = [
    {"op": "grant", "faucet": "daily", "owner": "ana", "tick": 0},
    {"op": "grant", "faucet": "daily", "owner": "bo", "tick": 0},
    {
        "op": "grant_items",
        "source": "stockpile",
        "owner": "ana",
        "item": "coal",
        "qty": 50,
    },
    {"op": "extract", "owner": "ana", "node": "vein_a", "tick": 0},
    {"op": "extract", "owner": "bo", "node": "vein_a", "tick": 1},
    {"op": "extract", "owner": "bo", "node": "vein_a", "tick": 2},  # refused: cooldown
    {"op": "set_lines", "owner": "ana", "lines": 3},
    {"op": "research", "owner": "ana", "bp": "smelt_ingot", "track": "me", "tick": 3},
    {"op": "build", "owner": "ana", "bp": "smelt_ingot", "runs": 5, "tick": 4},
    {"op": "extract", "owner": "ana", "node": "vein_a", "tick": 12},
    {"op": "chain", "owner": "ana", "target": "plate", "qty": 2, "tick": 13},
    {"op": "advance", "tick": 80},
    {"op": "list", "owner": "ana", "item": "ingot", "qty": 2, "price": 52, "tick": 81},
    {"op": "buy", "owner": "bo", "item": "ingot", "qty": 1, "price": 60, "tick": 82},
    {"op": "build", "owner": "bo", "bp": "weld_hull", "runs": 1, "tick": 83},
    {"op": "cancel", "owner": "bo", "job_id": 99, "tick": 84},  # refused: unknown job
    {"op": "advance", "tick": 400},
]


def _build():
    return build_system(market=True)


def test_same_script_same_digest():
    a = replay.fingerprint(_build, SCRIPT)
    assert a == replay.fingerprint(_build, SCRIPT)
    system, results = replay.run(_build, SCRIPT)
    assert system.digest() == a
    assert sum(1 for r in results if isinstance(r, dict) and "refused" in r) >= 2
    assert system.audit()["ok"]


def test_log_replays_to_same_state():
    system, _ = replay.run(_build, SCRIPT)
    # economy grants go straight to the ledger; industry logs everything it does
    grants = [c for c in SCRIPT if c["op"].startswith("grant")]
    again, _ = replay.run(_build, grants + system.log)
    assert again.digest() == system.digest()


def test_different_script_different_digest():
    assert replay.fingerprint(_build, SCRIPT) != replay.fingerprint(_build, SCRIPT[:-1])
