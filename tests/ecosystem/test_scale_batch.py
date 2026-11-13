"""Scale batch smoke tests."""
from skeleton.jeeves.ecosystem.eras.nes import abilities, scale
from skeleton.jeeves.ecosystem.assets.texture.texture_000 import describe, respray
from skeleton.jeeves.ecosystem.multiplayer.session_000 import open_session, pack_delta
from skeleton.jeeves.ecosystem.levels.layout_000 import rooms
from skeleton.jeeves.ecosystem.effects.burn import apply
from skeleton.jeeves.ecosystem.economy.table_000 import price

def test_era():
    a = abilities()
    assert "move" in a
    assert scale() == 1.0

def test_asset():
    d = describe()
    assert d["kind"] == "texture"
    r = respray("ash")
    assert r["ok"] is True

def test_multiplayer():
    s = open_session("host1")
    assert s["ok"] is True
    d = pack_delta({"hp": 100, "pos": 1}, ["p1"])
    assert d["ok"] is True

def test_level_and_effect():
    rs = rooms(0.94)
    assert rs[-1]["kind"] == "boss"
    e = apply("player", 2)
    assert e["ok"] is True

def test_economy():
    assert price(10, 0.9) > 0
