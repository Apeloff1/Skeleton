from dataclasses import dataclass

import pytest

from skeleton.forge.ai_builder.procgen import (BspConfig, CurrencyDrop, EconomyLootSource, EncounterConfig,
                                               LootEntry, LootSource, PacingCurve, ProcgenError, Streams,
                                               bsp_layout, pacing_report, place_encounters, place_loot,
                                               risk_value_correlation)
from skeleton.simulation.economy.harbor import Harbor
from skeleton.simulation.economy.sim import CurrencySpec, EconomySim, FaucetSpec, ItemSpec

PLAYER = {"hp": 100, "dps": 10}


def layout(seed=1):
    return bsp_layout(Streams(seed).stream("dungeon/bsp"), BspConfig())


def econ():
    return EconomySim([CurrencySpec("gold")],
                      [ItemSpec("potion", "gold", 5, 20, 8), ItemSpec("gem", "gold", 1, 200, 80),
                       ItemSpec("arrow", "gold", 50, 2, 1), ItemSpec("token", "gold", 1)],
                      [FaucetSpec("kill", "gold", 5)])


def test_pacing_curve_shape():
    c = PacingCurve(jitter=0)
    assert c.value(0) == pytest.approx(c.base) and c.value(1) == pytest.approx(c.peak)
    assert c.value(0.5, 3) < c.value(0.5, 2)  # rest dip
    assert c.value(0.5, 3, allow_rest=False) == c.value(0.5, 2)
    with pytest.raises(ProcgenError):
        PacingCurve(base=0.9, peak=0.5)


def test_encounters_deterministic():
    a = place_encounters(layout(), PLAYER, Streams(3).stream("encounters"))
    b = place_encounters(layout(), PLAYER, Streams(3).stream("encounters"))
    c = place_encounters(layout(), PLAYER, Streams(4).stream("encounters"))
    assert a.digest() == b.digest() != c.digest()


@pytest.mark.parametrize("seed", range(10))
def test_encounters_stay_under_validator_limits(seed):
    lay = layout(seed)
    cfg = EncounterConfig()
    plan = place_encounters(lay, PLAYER, Streams(seed).stream("encounters"), cfg)
    for rp in plan.rooms.values():
        assert rp.damage < 0.8 * PLAYER["hp"]          # validator's near-lethal line
        assert rp.damage <= cfg.cap * PLAYER["hp"] + 1e-6
        for e in rp.encounters:
            assert e.enemy_hp > 0 and e.enemy_dps >= 0
            assert e.damage == pytest.approx(e.enemy_hp / PLAYER["dps"] * e.enemy_dps, abs=1e-5)
    assert plan.rooms[lay.start].encounters == ()
    curve = plan.curve()
    assert curve[-1] == max(curve)                        # goal fight is the peak
    rep = pacing_report(curve)
    assert rep["trend"] > 0 and not rep["spikes"]


def test_encounters_scale_with_player():
    lay = layout(2)
    weak = place_encounters(lay, {"hp": 50, "dps": 5}, Streams(2).stream("e"))
    strong = place_encounters(lay, {"hp": 500, "dps": 50}, Streams(2).stream("e"))
    assert weak.curve() == pytest.approx(strong.curve(), abs=0.1)  # relative to the player (stat rounding can flip a pick)
    with pytest.raises(ProcgenError):
        place_encounters(lay, {"hp": 0, "dps": 1}, Streams(2).stream("e"))


def test_pacing_report_flags():
    rep = pacing_report([0.1, 0.1, 0.9, 0.1])
    assert rep["spikes"] == [2]
    assert pacing_report([0.5, 0.4, 0.3])["flat"]


def test_economy_loot_source_uses_sim_prices():
    src = EconomyLootSource(econ())
    entries = {e.item_id: e for e in src.entries()}
    assert set(entries) == {"potion", "gem", "arrow"}       # unpriced item skipped
    assert entries["gem"].value == 80 and entries["potion"].value == 8  # vendor_sell_price
    assert entries["arrow"].weight > entries["gem"].weight  # inverse-value fallback
    assert src.describe()["weights"] == "inverse_value"
    assert list(src.currency_drops()) == [CurrencyDrop("gold", 5)]
    assert isinstance(src, LootSource)


def test_harbor_weights_used_only_when_balanced_and_covering():
    sim = econ()
    good = EconomyLootSource(sim, Harbor({"potion": 0.5, "gem": 0.1, "arrow": 0.4}))
    assert good.describe()["weights"] == "harbor"
    assert {e.item_id: e.weight for e in good.entries()}["gem"] == 0.1
    assert EconomyLootSource(sim, Harbor({"potion": 0.7, "gem": 0.1})).describe()["weights"] == "inverse_value"
    assert EconomyLootSource(sim, Harbor({"potion": 2.0, "gem": 1, "arrow": 1})).describe()["weights"] == "inverse_value"


@dataclass
class FakeSource:
    items: tuple

    def entries(self):
        return self.items

    def currency_drops(self):
        return ()

    def describe(self):
        return {"source": "fake"}


def test_loot_follows_risk_and_is_deterministic():
    src = FakeSource((LootEntry("a", "c", 10, 1.0, 9), LootEntry("b", "c", 30, 0.5, 9), LootEntry("x", "c", 3, 2, 9)))
    risk = {f"r{i}": i / 9 for i in range(10)}
    a = place_loot(risk, src, Streams(1).stream("loot"), goal="r9")
    b = place_loot(risk, src, Streams(1).stream("loot"), goal="r9")
    assert a.digest() == b.digest()
    assert a.median_value == 10
    assert risk_value_correlation(a) > 0.5
    for r in a.rooms.values():
        assert r.value <= r.budget


def test_loot_rejects_bad_source():
    with pytest.raises(ProcgenError):
        place_loot({"r": 1}, object(), Streams(1).stream("l"))  # type: ignore[arg-type]
    with pytest.raises(ProcgenError):
        place_loot({"r": 1}, FakeSource(()), Streams(1).stream("l"))
