"""Iteration 86 — Universal Forge expansion (550 categories / 30 families),
aggregate scene clamp (300), themed seed coverage, and regression isolation
of construct/material kinds from new universal families."""
from __future__ import annotations

import os
import time
import uuid

import pytest
import requests

BASE_URL = (
    os.environ.get("EXPO_BACKEND_URL")
    or os.environ.get("EXPO_PUBLIC_BACKEND_URL")
    or "https://player-retention.preview.emergentagent.com"
).rstrip("/")

API = f"{BASE_URL}/api/galaxy-studio/forge"


# ── Catalog: 550 categories, 30 families, new families present ───────────
class TestCatalog:
    def test_catalog_counts_and_new_families(self):
        r = requests.get(f"{API}/catalog", timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["category_count"] == 550, f"expected 550 categories, got {data['category_count']}"
        assert data["family_count"] == 30, f"expected 30 families, got {data['family_count']}"

        fam_by_key = {f["key"]: f for f in data["families"]}
        new_families = ["gem", "light", "book", "coin", "armor", "banner",
                        "door", "shrine", "mushroom", "trap"]
        missing = [fk for fk in new_families if fk not in fam_by_key]
        assert not missing, f"missing new families: {missing}"
        zero_count = [fk for fk in new_families if fam_by_key[fk]["count"] <= 0]
        assert not zero_count, f"families with zero count: {zero_count}"


# ── Generate: every requested category produces real geometry ───────────
@pytest.mark.parametrize("category,expected_family", [
    ("diamond", "gem"),
    ("torch", "light"),
    ("book", "book"),
    ("coin", "coin"),
    ("shield", "armor"),
    ("banner", "banner"),
    ("door", "door"),
    ("shrine", "shrine"),
    ("mushroom", "mushroom"),
    ("spike_trap", "trap"),
    ("wolf", "creature"),
    ("oak_tree", "flora"),
])
def test_generate_universal_categories(category, expected_family):
    r = requests.post(f"{API}/generate", json={
        "category": category, "era": "modern", "use_llm": False
    }, timeout=30)
    assert r.status_code == 200, f"{category} -> {r.status_code}: {r.text}"
    spec = r.json()
    assert spec.get("family") == expected_family, \
        f"{category}: family {spec.get('family')} != {expected_family}"
    geo = spec.get("geometry") or []
    assert isinstance(geo, list) and len(geo) > 0, \
        f"{category}: no geometry parts"


# ── Compose clamp: total clamped to 300 regardless of requested counts ──
class TestComposeClamp:
    def test_compose_clamps_aggregate_to_300(self):
        build_id = f"clamp_qa_{uuid.uuid4().hex[:6]}"
        r = requests.post(f"{API}/compose", json={
            "build_id": build_id, "era": "modern",
            "items": [
                {"category": "coin", "count": 200},
                {"category": "gem", "count": 200},
                {"category": "book", "count": 200},
            ],
            "mount": False,
        }, timeout=120)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["total"] == 300, f"expected total 300, got {data['total']}"
        assert data["clamped"] is True, "clamped flag should be True"
        assert data["max_per_scene"] == 300


# ── Seed: each genre seeds successfully (clamp aware) ───────────────────
@pytest.mark.parametrize("genre", ["rpg", "shooter", "survival"])
def test_seed_genre(genre):
    build_id = f"seed_{genre}_{uuid.uuid4().hex[:6]}"
    r = requests.post(f"{API}/seed", json={
        "build_id": build_id, "era": "modern", "genre": genre, "mount": False,
    }, timeout=120)
    assert r.status_code == 200, f"{genre} -> {r.status_code}: {r.text}"
    data = r.json()
    assert data["total"] > 0, f"{genre}: total {data['total']} not > 0"
    assert data.get("genre") == genre
    assert isinstance(data.get("families"), list) and data["families"]


# ── Regression: constructs/list & materials/list isolated from new families ─
class TestRegressionIsolation:
    def test_constructs_list_excludes_universal_kinds(self):
        # Seed a build with universal items to ensure they exist in DB
        build_id = f"reg_uni_{uuid.uuid4().hex[:6]}"
        seed_r = requests.post(f"{API}/seed", json={
            "build_id": build_id, "era": "modern", "genre": "rpg", "mount": False,
        }, timeout=120)
        assert seed_r.status_code == 200

        # constructs/list should NOT include universal-family kinds
        r = requests.get(f"{BASE_URL}/api/galaxy-studio/constructs/list",
                         params={"limit": 200}, timeout=30)
        assert r.status_code == 200, r.text
        items = r.json().get("items", [])
        leaked = [it for it in items
                  if it.get("kind") in {"gem", "light", "book", "coin", "armor",
                                         "banner", "door", "shrine", "mushroom",
                                         "trap", "creature", "flora", "character",
                                         "vehicle", "wearable", "prop", "world",
                                         "fx", "sound", "furniture", "weapon",
                                         "container", "machine", "instrument",
                                         "food", "ui", "avatar", "terrain"}]
        assert not leaked, f"constructs/list leaked universal kinds: {[l.get('kind') for l in leaked[:5]]}"

    def test_materials_list_excludes_universal_kinds(self):
        r = requests.get(f"{BASE_URL}/api/galaxy-studio/materials/list",
                         params={"limit": 200}, timeout=30)
        assert r.status_code == 200, r.text
        items = r.json().get("items", [])
        non_surface = [it for it in items if it.get("kind") != "surface"]
        # Allow if structure (constructs route) but reject universal families
        bad_kinds = {"gem", "light", "book", "coin", "armor", "banner", "door",
                     "shrine", "mushroom", "trap", "creature", "flora",
                     "character", "vehicle", "wearable", "prop", "fx", "sound",
                     "furniture", "weapon", "container", "machine", "instrument",
                     "food", "ui", "avatar", "terrain", "world"}
        leaked = [it for it in non_surface if it.get("kind") in bad_kinds]
        assert not leaked, f"materials/list leaked universal kinds: {[l.get('kind') for l in leaked[:5]]}"

    def test_compose_small_counts_mounts(self):
        build_id = f"reg_small_{uuid.uuid4().hex[:6]}"
        r = requests.post(f"{API}/compose", json={
            "build_id": build_id, "era": "modern",
            "items": [
                {"category": "diamond", "count": 2},
                {"category": "wolf", "count": 2},
                {"category": "oak_tree", "count": 2},
            ],
            "mount": True,
        }, timeout=60)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["total"] == 6
        assert data["clamped"] is False
        assert data["mounted"] is True
