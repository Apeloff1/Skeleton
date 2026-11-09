"""Agent edge — seeded chaos: at-least-once without loss, order, dedup, breaker isolation."""

from __future__ import annotations

import pytest

from skeleton.gate_plane.agent_edge.chaos_edge import (
    SCENARIOS,
    run_all,
    scenario_poison_and_ttl,
    scenario_sick_agent,
    scenario_unreliable_consumer,
)

SEEDS = (1, 7, 42, 1337, 2026)


@pytest.mark.parametrize("seed", SEEDS)
def test_unreliable_consumer_no_loss_ordered(seed):
    rep = scenario_unreliable_consumer(seed)
    assert rep.ok, rep.as_dict()
    assert rep.stats["accepted"] == 12 * 15
    assert rep.stats["acked"] + rep.stats["dead"] == rep.stats["accepted"]
    assert rep.stats["duplicate_publishes"] > 0


@pytest.mark.parametrize("seed", SEEDS)
def test_poison_and_ttl_land_in_dlq(seed):
    rep = scenario_poison_and_ttl(seed)
    assert rep.ok, rep.as_dict()


@pytest.mark.parametrize("seed", SEEDS)
def test_sick_agent_is_isolated(seed):
    rep = scenario_sick_agent(seed)
    assert rep.ok, rep.as_dict()
    assert rep.stats["healthy_share"] > 0.7


def test_chaos_is_reproducible():
    a = scenario_unreliable_consumer(99).as_dict()
    b = scenario_unreliable_consumer(99).as_dict()
    assert a == b


def test_heavy_chaos_mode_still_converges():
    rep = scenario_unreliable_consumer(5, p_crash=0.35, p_lost_ack=0.25, p_duplicate_publish=0.5, max_attempts=50)
    assert rep.ok, rep.as_dict()


def test_run_all_matrix():
    reports = run_all(seeds=(3, 4))
    assert len(reports) == 2 * len(SCENARIOS)
    assert all(r.ok for r in reports), [r.as_dict() for r in reports if not r.ok]
