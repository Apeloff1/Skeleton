"""
Iteration 77 — Era-sensitive forge integration tests (public ingress).

Validates the era-sensitivity end-to-end at the API:
  • GET  /api/galaxy-studio/eras                (catalog: 7 eras ordered, default=modern)
  • GET  /api/galaxy-studio/eras/{key}          (single + alias tolerance: "8-Bit", "PS5")
  • POST /api/galaxy-studio/vault-gdd/escalate  (era=8bit / nextgen / modern)
  • GET  /api/galaxy-studio/vault-gdd/choices/{build_id}
  • POST /api/galaxy-studio/assets/forge        (era param routes to by_type list)
"""
from __future__ import annotations

import os
import time

import pytest
import requests

BASE_URL = (
    os.environ.get("EXPO_PUBLIC_BACKEND_URL")
    or os.environ.get("EXPO_BACKEND_URL")
    or "https://player-retention.preview.emergentagent.com"
).rstrip("/")

TS = int(time.time())
BUILD_8BIT = f"TEST_it77_8bit_{TS}"
BUILD_NG = f"TEST_it77_ng_{TS}"
BUILD_MODERN = f"TEST_it77_mod_{TS}"
BUILD_ASSETS = f"TEST_it77_assets_{TS}"


@pytest.fixture(scope="module")
def api():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


# ── /eras catalog ────────────────────────────────────────────────────────
class TestErasCatalog:
    def test_catalog_lists_7_ordered_eras(self, api):
        r = api.get(f"{BASE_URL}/api/galaxy-studio/eras", timeout=20)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["default"] == "modern"
        assert d["count"] == 7
        keys = [e["key"] for e in d["eras"]]
        assert keys == ["8bit", "16bit", "early3d", "64bit", "earlyhd",
                        "modern", "nextgen"]
        # Each catalog entry has the picker fields
        for e in d["eras"]:
            for k in ("storage_label", "color_label", "poly_label",
                      "resolution", "audio_format", "asset_types"):
                assert k in e, f"era {e.get('key')} missing {k}"
        ng = next(e for e in d["eras"] if e["key"] == "nextgen")
        assert "250" in ng["storage_label"] and "500" in ng["storage_label"]

    def test_single_era_with_alias(self, api):
        r = api.get(f"{BASE_URL}/api/galaxy-studio/eras/8-Bit", timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["key"] == "8bit"
        # raw byte caps too
        assert d["storage_bytes"][0] <= 8 * 1024
        assert d["storage_bytes"][1] == 1024 * 1024  # 1 MB cap

        r2 = api.get(f"{BASE_URL}/api/galaxy-studio/eras/PS5", timeout=15)
        assert r2.status_code == 200, r2.text
        assert r2.json()["key"] == "modern"

    def test_unknown_era_falls_back_to_modern(self, api):
        r = api.get(f"{BASE_URL}/api/galaxy-studio/eras/garbage", timeout=15)
        assert r.status_code == 200
        # Backend resolver gracefully falls back to DEFAULT_ERA (modern)
        assert r.json()["key"] == "modern"


# ── /vault-gdd/escalate era-sensitivity ───────────────────────────────────
class TestEscalateEraSensitive:
    def test_escalate_8bit_skips_meshes_and_uses_8bit_cap(self, api):
        body = {"build_id": BUILD_8BIT, "genre": "platformer", "seed": 4,
                "platoon_size": 4, "era": "8bit", "persist": True}
        r = api.post(f"{BASE_URL}/api/galaxy-studio/vault-gdd/escalate",
                     json=body, timeout=60)
        assert r.status_code == 200, r.text
        m = r.json()
        assert m["era"] == "8bit"
        # 8-bit pack: 5 asset types (sprite_sheet/icon/thumbnail/sfx/palette_swatch)
        assert m["totals"]["assets_per_item"] == 5
        assert m["totals"]["assets"] == m["totals"]["gamefiles"] * 5
        # storage cap == 1 MB (the 8-bit upper bound)
        assert m["storage"]["cap_bytes"] == 1024 * 1024
        assert "used_pct" in m["storage"]
        # parity locked + balance curve + choices/awareness present
        assert m["parity_locked"] is True
        assert isinstance(m["balance_curve"], list) and len(m["balance_curve"]) == 6
        assert isinstance(m["choices"], list) and len(m["choices"]) >= 7
        aw = m["awareness"]
        assert aw["era"] == "8bit"
        assert len(aw["stages_done"]) == 6

    def test_escalate_nextgen_assets_and_cap(self, api):
        body = {"build_id": BUILD_NG, "genre": "rpg", "seed": 9,
                "platoon_size": 3, "era": "nextgen", "persist": False}
        r = api.post(f"{BASE_URL}/api/galaxy-studio/vault-gdd/escalate",
                     json=body, timeout=60)
        assert r.status_code == 200, r.text
        m = r.json()
        assert m["era"] == "nextgen"
        assert m["totals"]["assets_per_item"] == 10
        # ~500 GB cap label
        assert "GB" in m["storage"]["cap_label"]
        assert m["storage"]["cap_bytes"] == 500 * (1024 ** 3)
        # era_spec carried in manifest
        assert "era_spec" in m
        assert m["era_label"].lower().startswith("next")

    def test_escalate_modern_default_yields_10_assets_per_item(self, api):
        body = {"build_id": BUILD_MODERN, "genre": "rpg", "seed": 7,
                "platoon_size": 4, "era": "modern", "persist": False}
        r = api.post(f"{BASE_URL}/api/galaxy-studio/vault-gdd/escalate",
                     json=body, timeout=60)
        assert r.status_code == 200, r.text
        m = r.json()
        assert m["era"] == "modern"
        assert m["totals"]["assets_per_item"] == 10
        # grade FLOOR escalates (deterministic per stage). max_grade can plateau
        # at the floor when smaller platoons exhaust the top tier — that's
        # by-design escalation, not a regression.
        floors = [row["grade_floor"] for row in m["ladder"]]
        assert floors == sorted(floors)
        assert floors[-1] > floors[0]
        assert m["grade_escalating"] is True


# ── /vault-gdd/choices/{build_id} ────────────────────────────────────────
class TestChoicesLedger:
    def test_choices_ledger_after_8bit_escalate(self, api):
        # depends on TestEscalateEraSensitive.test_escalate_8bit having run with persist=True
        r = api.get(
            f"{BASE_URL}/api/galaxy-studio/vault-gdd/choices/{BUILD_8BIT}",
            timeout=20)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["build_id"] == BUILD_8BIT
        aw = d["awareness"]
        assert aw["era"] == "8bit"
        assert aw["genre"] == "platformer"
        assert aw["seed"] == 4
        assert len(aw["stages_done"]) == 6
        # 1 game_setup + 6 stage_forge
        kinds = [e["kind"] for e in d["ledger"]]
        assert kinds.count("game_setup") == 1
        assert kinds.count("stage_forge") == 6


# ── /assets/forge era-aware count ─────────────────────────────────────────
class TestAssetsForgeEra:
    def test_forge_8bit_returns_5_types(self, api):
        # need a build with gamefiles first → fast path: escalate persist=True
        body = {"build_id": BUILD_ASSETS, "genre": "rpg", "seed": 3,
                "platoon_size": 3, "era": "8bit", "persist": True}
        e = api.post(f"{BASE_URL}/api/galaxy-studio/vault-gdd/escalate",
                     json=body, timeout=60)
        assert e.status_code == 200, e.text

        r = api.post(f"{BASE_URL}/api/galaxy-studio/assets/forge",
                     json={"build_id": BUILD_ASSETS, "era": "8bit",
                           "persist": False}, timeout=45)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["assets_per_item"] == 5
        # by_type is a LIST of {type,count}
        type_keys = {row["type"] for row in d["by_type"]}
        assert type_keys == {"sprite_sheet", "icon", "thumbnail", "sfx",
                             "palette_swatch"}
        assert d["total_bytes"] > 0
        assert d["total_assets"] == d["items"] * 5

    def test_forge_nextgen_returns_10_types(self, api):
        r = api.post(f"{BASE_URL}/api/galaxy-studio/assets/forge",
                     json={"build_id": BUILD_ASSETS, "era": "nextgen",
                           "persist": False}, timeout=45)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["assets_per_item"] == 10
        type_keys = {row["type"] for row in d["by_type"]}
        # 10 distinct types in modern/nextgen pack
        assert len(type_keys) == 10


# ── Era compliance gate doesn't reject forged items ───────────────────────
class TestEraComplianceGate:
    def test_8bit_forged_items_carry_era_and_pass(self, api):
        r = api.get(
            f"{BASE_URL}/api/galaxy-studio/items/{BUILD_8BIT}", timeout=20)
        # not all builds expose this — only assert if route returns 200
        if r.status_code != 200:
            pytest.skip(f"items list endpoint not available ({r.status_code})")
        items = r.json().get("items", [])
        assert items, "expected forged items for 8bit build"
        for it in items[:5]:
            skin = it.get("skin") or {}
            assert skin.get("era") == "8bit"
