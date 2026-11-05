"""Original economy editor and before/after game replay acceptance."""
from __future__ import annotations

from copy import deepcopy
import pytest

from skeleton.game.gameplay.harbor_crafting import HarborError, decode, digest, load_source
from skeleton.game.gameplay.harbor_crafting_cli import DEFAULT_WORLD, DEFAULT_MISSIONS
from skeleton.game.gameplay.harbor_crafting_market_balance import balance_market, verify_market_balance


@pytest.fixture
def sources():
    world = load_source(DEFAULT_WORLD)
    board = decode(DEFAULT_MISSIONS.read_bytes())
    return world, board


def test_market_price_revision_still_earns_victory(sources):
    world, board = sources
    original = deepcopy(world)
    result = balance_market(
        world, board, [{"op": "merchant_price", "price": 3}],
        expected_source_digest=digest(world),
    )
    verified = verify_market_balance(result)
    assert verified["before_ending"] == "beacon"
    assert verified["after_ending"] == "beacon"
    assert result["revision"]["source"]["npc"]["price"] == 3
    assert world == original
    assert result["before"]["market"]["totals"]["delivered"] is True
    assert result["after"]["market"]["totals"]["delivered"] is True


def test_market_rejects_stale_source(sources):
    world, board = sources
    with pytest.raises(HarborError, match="stale"):
        balance_market(
            world, board, [{"op": "merchant_price", "price": 3}],
            expected_source_digest="0" * 64,
        )


@pytest.mark.parametrize("operations", [
    [], [{"op": "tile", "at": [1, 1], "tile": "#"}],
    [{"op": "merchant_price", "price": 0}],
    [{"op": "merchant_price", "price": 2}],
    [{"op": "merchant_price", "price": 3}, {"op": "merchant_price", "price": 4}],
])
def test_market_rejects_invalid_or_noop_edits(sources, operations):
    world, board = sources
    with pytest.raises(HarborError):
        balance_market(world, board, operations, expected_source_digest=digest(world))


def test_market_rejects_rehashed_fake_balance(sources):
    world, board = sources
    result = balance_market(
        world, board, [{"op": "merchant_price", "price": 3}],
        expected_source_digest=digest(world),
    )
    result["delta"]["points"] = 1000
    result["comparison_digest"] = digest({
        k: v for k, v in result.items() if k != "comparison_digest"
    })
    with pytest.raises(HarborError, match="replay"):
        verify_market_balance(result)


def test_market_comparison_requires_exact_fields(sources):
    world, board = sources
    result = balance_market(
        world, board, [{"op": "merchant_price", "price": 3}],
        expected_source_digest=digest(world),
    )
    result["untrusted"] = "yes"
    with pytest.raises(HarborError):
        verify_market_balance(result)
