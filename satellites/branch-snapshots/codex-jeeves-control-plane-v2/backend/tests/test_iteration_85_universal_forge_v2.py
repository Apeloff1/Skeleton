"""Session 19 / iter 85 — Universal Forge expansion + compose/seed + snowball
auto-seed regression.

Covers:
  • catalog → 326 categories, 20 families incl. new ones (furniture/weapon/...)
  • generate for one category per new family (sword, robot, chair, bread, bust,
    boulder, drum, chest, icon, mannequin, geyser) — parts > 0, NO 500s.
  • compose-scene populates a build with trees+critters+boulders and mounts.
  • seed_for_build (rpg/shooter/survival) mints families>0.
  • Regression: construct snowball/forge still 200 + universal>0; universal
    assets DO NOT leak into /constructs/list or /materials/list.
"""
from __future__ import annotations

import os
import pytest
import requests

BASE_URL = os.environ.get("EXPO_BACKEND_URL") or os.environ.get(
    "EXPO_PUBLIC_BACKEND_URL", "https://player-retention.preview.emergentagent.com"
).rstrip("/")
API = f"{BASE_URL}/api/galaxy-studio"


@pytest.fixture(scope="module")
def s():
    sess = requests.Session()
    sess.headers.update({"Content-Type": "application/json"})
    return sess


# ── Catalog: new family/category counts ───────────────────────────────────
def test_catalog_counts_and_new_families(s):
    r = s.get(f"{API}/forge/catalog", timeout=30)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["category_count"] == 326, f"category_count={d['category_count']}"
    assert d["family_count"] == 20, f"family_count={d['family_count']}"

    fam_by_key = {f["key"]: f for f in d["families"]}
    for fk in [
        "furniture", "weapon", "container", "machine", "instrument",
        "food", "ui", "avatar", "terrain",
    ]:
        assert fk in fam_by_key, f"missing family {fk}"
        assert fam_by_key[fk]["count"] > 0, f"family {fk} count is 0"


# ── Generate: one category per new family + a couple regressions ──────────
@pytest.mark.parametrize("category,expected_family", [
    ("sword", "weapon"),
    ("robot", "machine"),
    ("chair", "furniture"),
    ("bread", "food"),
    ("bust", "avatar"),
    ("boulder", "terrain"),
    ("drum", "instrument"),
    ("chest", "container"),
    ("icon", "ui"),
    ("mannequin", "avatar"),
    ("geyser", "terrain"),
])
def test_generate_per_family(s, category, expected_family):
    payload = {"category": category, "era": "modern", "use_llm": False}
    r = s.post(f"{API}/forge/generate", json=payload, timeout=30)
    assert r.status_code == 200, f"{category}: HTTP {r.status_code} {r.text[:300]}"
    spec = r.json()
    assert spec.get("family") == expected_family, (
        f"{category} family={spec.get('family')} expected={expected_family}"
    )
    geom = spec.get("geometry") or []
    assert isinstance(geom, list) and len(geom) > 0, f"{category} has empty geometry"


# ── Compose scene ─────────────────────────────────────────────────────────
def test_compose_scene_forest(s):
    payload = {
        "build_id": "scene_qa",
        "era": "modern",
        "items": [
            {"category": "tree", "count": 6},
            {"category": "critter", "count": 3},
            {"category": "boulder", "count": 2},
        ],
    }
    r = s.post(f"{API}/forge/compose", json=payload, timeout=60)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["total"] == 11, f"total={d['total']}"
    assert len(d["composed"]) == 3
    assert d["mounted"] is True

    # Verify list shows all 11
    r2 = s.get(f"{API}/forge/list", params={"build_id": "scene_qa"}, timeout=30)
    assert r2.status_code == 200, r2.text
    items = r2.json()
    assert items["total"] >= 11, f"list total={items['total']} (expected ≥11)"


# ── Seed for build (snowball auto-seed) ───────────────────────────────────
@pytest.mark.parametrize("genre", ["rpg", "shooter", "survival"])
def test_seed_for_build(s, genre):
    payload = {"build_id": f"seed_qa_{genre}", "era": "modern", "genre": genre}
    r = s.post(f"{API}/forge/seed", json=payload, timeout=60)
    assert r.status_code == 200, f"{genre}: {r.text[:400]}"
    d = r.json()
    assert d["total"] > 0, f"{genre} total={d['total']}"
    assert isinstance(d.get("families"), list) and len(d["families"]) > 0


# ── Regression: construct snowball/forge still works + universal>0 ────────
def test_construct_snowball_forge_includes_universal(s):
    # Use the construct snowball forge route (no final build memory guard hit).
    payload = {"build_id": "fb_universal_qa", "era": "modern", "genre": "rpg",
               "seed": 1, "platoon_size": 4, "persist": False}
    r = s.post(f"{API}/constructs/snowball/forge", json=payload, timeout=120)
    assert r.status_code == 200, f"snowball forge HTTP {r.status_code}: {r.text[:400]}"
    d = r.json()
    # Universal count should be reported (auto-seed wired in).
    universal = d.get("universal") or d.get("universal_count") or d.get("totals", {}).get("universal")
    assert universal and int(universal) > 0, (
        f"snowball forge response missing universal>0; keys={list(d.keys())}, "
        f"totals={d.get('totals')}"
    )


def test_constructs_list_not_polluted_by_universal(s):
    r = s.get(f"{API}/constructs/list", timeout=30)
    assert r.status_code == 200, r.text
    rows = r.json().get("items", [])
    leaks = [x for x in rows if (x.get("kind") in {
        "flora", "creature", "fx", "character", "wearable", "vehicle", "sound",
        "world", "furniture", "weapon", "container", "machine", "instrument",
        "food", "ui", "avatar", "terrain", "prop",
    })]
    assert not leaks, f"universal-family kinds leaked into /constructs/list: {len(leaks)} samples={leaks[:2]}"


def test_materials_list_not_polluted_by_universal(s):
    r = s.get(f"{API}/materials/list", timeout=30)
    assert r.status_code == 200, r.text
    rows = r.json().get("items", [])
    leaks = [x for x in rows if (x.get("kind") in {
        "flora", "creature", "fx", "character", "wearable", "vehicle", "sound",
        "world", "furniture", "weapon", "container", "machine", "instrument",
        "food", "ui", "avatar", "terrain", "prop",
    })]
    assert not leaks, f"universal-family kinds leaked into /materials/list: {len(leaks)} samples={leaks[:2]}"
