"""Focused historical Studio contract regressions without package side effects."""
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TREES = ("skeleton/jeeves/studio", "skeleton/ai/agents/jeeves/studio")


def load(tree, name):
    spec = importlib.util.spec_from_file_location(name, ROOT / tree / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("tree", TREES)
def test_ratchet(tree):
    dev = load(tree, "ai_driven_dev").AIDrivenDev()
    assert dev.step(0.95, 0.96)["ratchet"] == 0.96
    assert dev.step(0.95, 0.93)["ratchet"] == 0.96


@pytest.mark.parametrize("tree", TREES)
def test_auction(tree):
    auction = load(tree, "auction_stub").AuctionStub()
    assert not auction.list("", 10)["ok"]
    assert not auction.list("relic", True)["ok"]
    assert auction.list("relic", 10)["ok"]
    assert not auction.bid("relic", 10, "ada")["ok"]
    assert auction.bid("relic", 12, "ada")["ok"]
    assert auction.close("relic")["bidder"] == "ada"
    assert not auction.list("relic", 1)["ok"]
    assert not auction.bid("relic", 20, "bea")["ok"]
    assert not auction.close([])["ok"]


@pytest.mark.parametrize("tree", TREES)
def test_local_digest_pointer(tree):
    save = load(tree, "cloud_save").CloudSave()
    assert not save.push("abc", "slot")["ok"]
    digest = "ab" * 32
    result = save.push(digest, "slot")
    assert result["ok"] and not result["synced"]
    assert save.pull("slot")["digest"] == digest
    assert not save.pull("slot")["synced"]
    assert not save.pull("missing")["ok"]


@pytest.mark.parametrize("tree", TREES)
def test_tilemap(tree):
    level = load(tree, "level_generator").LevelGenerator()
    assert level.to_godot_tilemap({}) == "# TileMap data v2\n# reason: missing_tiles\n"
    assert level.to_godot_tilemap({"tiles": [[0, 1], [2, 0]]}) == "# TileMap data v2\n1,0,1\n0,1,2\n"


@pytest.mark.parametrize("name", ("ai_driven_dev", "auction_stub", "cloud_save", "level_generator"))
def test_mirror(name):
    assert (ROOT / TREES[0] / (name + ".py")).read_bytes() == (
        ROOT / TREES[1] / (name + ".py")
    ).read_bytes()
