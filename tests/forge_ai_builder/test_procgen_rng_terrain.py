import pytest

from skeleton.forge.ai_builder.procgen import (DEFAULT_BIOMES, Heightmap, ProcgenError, Streams, TerrainConfig,
                                               canonical_bytes, classify, diamond_square, erode, generate_terrain,
                                               table_from, value_noise)
from skeleton.forge.ai_builder.procgen.erosion import thermal
from skeleton.forge.ai_builder.procgen.rng import root_digest


def draws(rng, n=8):
    return [rng.random() for _ in range(n)]


def test_streams_deterministic_and_named():
    a, b = Streams(42), Streams(42)
    assert draws(a.stream("terrain/height")) == draws(b.stream("terrain/height"))
    assert draws(a.stream("terrain/height")) != draws(a.stream("terrain/moisture"))
    assert draws(Streams(43).stream("terrain/height")) != draws(a.stream("terrain/height"))
    assert root_digest(42) == root_digest("42") or root_digest(42) != root_digest(43)


def test_substreams_independent_of_draw_order():
    a, b = Streams(9), Streams(9)
    draws(a.stream("loot"), 100)  # consuming one stream must not shift another
    assert draws(a.stream("encounters")) == draws(b.stream("encounters"))
    assert "loot" in a.issued() and "encounters" in a.issued()


@pytest.mark.parametrize("bad", ["", "Bad Name", "a//b", "/x"])
def test_stream_names_validated(bad):
    with pytest.raises(ProcgenError):
        Streams(1).stream(bad)


def test_value_noise_range_and_determinism():
    h1 = value_noise(40, 30, Streams(1).stream("n"), scale=8, octaves=3)
    h2 = value_noise(40, 30, Streams(1).stream("n"), scale=8, octaves=3)
    assert h1.digest() == h2.digest() and (h1.width, h1.height) == (40, 30)
    assert 0.0 <= h1.low and h1.high <= 1.0 and h1.high > h1.low


def test_diamond_square_size():
    hm = diamond_square(4, Streams(2).stream("ds"))
    assert (hm.width, hm.height) == (17, 17)
    with pytest.raises(ProcgenError):
        diamond_square(0, Streams(2).stream("ds"))


def test_thermal_conserves_mass_and_flattens():
    hm = value_noise(32, 32, Streams(3).stream("n"), scale=4)
    out, moved = thermal(hm, iterations=5, talus=0.01)
    assert moved > 0
    assert abs(sum(out.cells) - sum(hm.cells)) < 1e-6
    rough = lambda m: sum(abs(m.at(x, y) - m.at(x + 1, y)) for y in range(m.height) for x in range(m.width - 1))
    assert rough(out) < rough(hm)


def test_erode_reports():
    hm = value_noise(24, 24, Streams(4).stream("n"), scale=6)
    out, rep = erode(hm, Streams(4).stream("e"))
    assert rep.as_dict()["thermal_moved"] >= 0 and 0 <= out.low <= out.high <= 1


def test_biome_thresholds():
    assert DEFAULT_BIOMES.classify(0.1, 0.5) == "water"
    assert DEFAULT_BIOMES.classify(0.5, 0.1) == "desert"
    assert DEFAULT_BIOMES.classify(0.5, 0.9) == "forest"
    assert DEFAULT_BIOMES.classify(0.99, 0.9) == "snow"
    assert DEFAULT_BIOMES.classify(-1, 2) == "water"
    with pytest.raises(ProcgenError):
        table_from([(0.5, [(1.0, "a")])], ["a"])  # does not reach height 1
    t = table_from([(0.5, [(1.0, "low")]), (1.0, [(0.5, "dry"), (1.0, "wet")])], ["dry"])
    hm = Heightmap.from_rows([[0.2, 0.8], [0.8, 0.8]])
    mm = Heightmap.from_rows([[0.0, 0.2], [0.9, 0.5]])
    assert classify(hm, mm, t).cells == ("low", "dry", "wet", "dry")


@pytest.mark.parametrize("method", ["value", "diamond_square"])
def test_terrain_byte_identical(method):
    cfg = TerrainConfig(width=32, height=24, method=method, droplets=50)
    a = generate_terrain(Streams(11), cfg)
    b = generate_terrain(Streams(11), cfg)
    assert canonical_bytes(a.as_dict()) == canonical_bytes(b.as_dict())
    c = generate_terrain(Streams(12), cfg)
    assert a.receipt.height_digest != c.receipt.height_digest
    assert a.receipt.request_digest == a.request.request_digest
    assert (a.height.width, a.height.height) == (32, 24)
    assert 0 < a.walkable_fraction() <= 1


def test_terrain_config_validation():
    with pytest.raises(ProcgenError):
        TerrainConfig(method="perlin")
    with pytest.raises(ProcgenError):
        TerrainConfig(width=4)
