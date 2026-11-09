"""
Regression: /manifest + /genres extraction (Jun 2026) and the shared
galaxy_studio_constants module. Guards against:
  - the static /manifest & /genres routes being shadowed by dynamic routes
  - the constants module drifting from what galaxy_studio re-exports
  - the data blocks being mangled during the line-range migration
"""
import httpx
import pytest

BASE = "http://localhost:8001"


def test_constants_module_self_consistent():
    from routes import galaxy_studio_constants as c
    assert c.TOTAL_GENRES == len(c.GALAXY_GENRES)
    assert c.TOTAL_SUBGENRES == sum(len(g["subgenres"]) for g in c.GALAXY_GENRES.values())
    assert len(c.BUILD_PHASES) == 100
    assert c.AGENT_MANIFEST["total"]["agents"] == 1444700
    assert c.SYNERGY_NETWORK["total_links"] == 15


def test_galaxy_studio_reexports_match_constants():
    from routes import galaxy_studio as gs
    from routes import galaxy_studio_constants as c
    assert gs.GALAXY_GENRES is c.GALAXY_GENRES
    assert gs.BUILD_PHASES is c.BUILD_PHASES
    assert gs.AGENT_MANIFEST is c.AGENT_MANIFEST
    assert gs.TOTAL_GENRES == c.TOTAL_GENRES


@pytest.mark.asyncio
async def test_manifest_endpoint():
    async with httpx.AsyncClient(base_url=BASE, timeout=15) as cl:
        r = await cl.get("/api/galaxy-studio/manifest")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["total_agents"] == 1444700
    assert d["total_phases"] == 100
    assert d["total_genres"] == d["total_genres"] and d["total_genres"] > 0
    assert isinstance(d["phases"], list) and len(d["phases"]) == 100
    assert "constellations" in d["synergy_network"]


@pytest.mark.asyncio
async def test_genres_endpoint():
    async with httpx.AsyncClient(base_url=BASE, timeout=15) as cl:
        r = await cl.get("/api/galaxy-studio/genres")
    assert r.status_code == 200, r.text
    d = r.json()
    assert len(d["genres"]) == d["total_genres"]
    # static path must NOT be shadowed by a dynamic route → real genre payload
    first = d["genres"][0]
    assert {"id", "name", "subgenres", "subgenre_count"} <= set(first.keys())
