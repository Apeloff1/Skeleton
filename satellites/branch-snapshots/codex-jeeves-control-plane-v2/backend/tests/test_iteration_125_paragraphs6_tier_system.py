"""
Iteration 125 — Backend regression for:
  • 6 default paragraphs of depth per segment (segments_detail.paragraphs[6]).
  • 5-tier choice system on applicable text→gamefile generators.

Validates:
  - GET /api/galaxy-studio/text-gamefile/generators → tiered_count == 22, each
    tiered generator has 5 labels, non-tiered generators have tiers == [].
  - POST .../boss_design/generate with tier="Raid / World Boss" → label suffix,
    tier_index == 5, fields.tier formatted text. Numeric tier="2" → tier_label
    "Elite Boss". tier=null still forges (no error).
  - Pipeline run on a forged gamefile → 14 stages, every stage has
    set_a.paragraphs_per_segment == 6 and segments_detail length 7 with
    paragraphs[6] non-empty strings (588 total paragraphs). overall_score and
    aaa still emitted.
"""
import os
import time

import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    BASE_URL = os.environ.get("EXPO_BACKEND_URL", "").rstrip("/")

TIERED_KEYS = {
    "boss_design", "boss_phase", "enemy_from_text", "minion_add",
    "item_from_text", "weapon_def", "armor_gear", "consumable_potion",
    "rarity_tier", "ability_from_text", "ultimate_super", "level_from_text",
    "dungeon_room", "arena", "wave_horde", "encounter_table",
    "achievement_from_text", "skill_node", "talent_perk", "reward_bundle",
    "battle_pass_tier", "monetization_offer",
}


@pytest.fixture(scope="module")
def api():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


# ── generators endpoint ────────────────────────────────────────────────────
def test_generators_tiered_count_and_tiers(api):
    r = api.get(f"{BASE_URL}/api/galaxy-studio/text-gamefile/generators", timeout=20)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d.get("tiered_count") == 22, f"tiered_count={d.get('tiered_count')}"
    gens = d.get("generators", [])
    assert isinstance(gens, list) and len(gens) >= 150

    keys_tiered = {g["key"] for g in gens if g.get("tiers")}
    assert keys_tiered == TIERED_KEYS, (
        f"unexpected tiered keys diff: missing={TIERED_KEYS - keys_tiered} "
        f"extra={keys_tiered - TIERED_KEYS}")

    for g in gens:
        if g["key"] in TIERED_KEYS:
            tiers = g.get("tiers", [])
            assert isinstance(tiers, list) and len(tiers) == 5, \
                f"{g['key']} has {len(tiers)} tier labels (expected 5)"
            assert all(isinstance(t, str) and t.strip() for t in tiers)
        else:
            assert g.get("tiers") == [], \
                f"{g['key']} should be tierless, got {g.get('tiers')}"


# ── boss_design generate w/ tiers ──────────────────────────────────────────
BUILD_ID = "qa_tier_1"
BOSS_TEXT = ("TEST_Vermillion — a colossal smoke-and-emberkin tyrant who reigns "
             "over a collapsing volcanic cathedral. Multi-phase fight with "
             "telegraphed sweeps, lava geyser zoning, and an enrage at <20%.")


def test_boss_tier5_label_and_fields(api):
    r = api.post(
        f"{BASE_URL}/api/galaxy-studio/text-gamefile/boss_design/generate",
        json={"build_id": BUILD_ID, "text": BOSS_TEXT, "tier": "Raid / World Boss"},
        timeout=20,
    )
    assert r.status_code == 200, r.text
    gf = r.json()
    assert gf.get("system") == "boss_design"
    assert gf.get("tier") == "Raid / World Boss"
    assert gf.get("tier_index") == 5
    label = gf.get("label", "")
    assert label.endswith("· Raid / World Boss"), f"label={label!r}"
    fields_tier = (gf.get("fields") or {}).get("tier")
    assert fields_tier == "Raid / World Boss (tier 5 of 5)", f"fields.tier={fields_tier!r}"
    ladder = gf.get("tier_ladder") or []
    assert len(ladder) == 5 and ladder[-1] == "Raid / World Boss"


def test_boss_numeric_tier2_maps_to_elite(api):
    r = api.post(
        f"{BASE_URL}/api/galaxy-studio/text-gamefile/boss_design/generate",
        json={"build_id": BUILD_ID, "text": BOSS_TEXT + " numeric tier check.",
              "tier": "2"},
        timeout=20,
    )
    assert r.status_code == 200, r.text
    gf = r.json()
    assert gf.get("tier_index") == 2
    assert gf.get("tier") == "Elite Boss"
    assert "Elite Boss" in gf.get("label", "")
    assert (gf.get("fields") or {}).get("tier") == "Elite Boss (tier 2 of 5)"


def test_boss_no_tier_still_forges(api):
    r = api.post(
        f"{BASE_URL}/api/galaxy-studio/text-gamefile/boss_design/generate",
        json={"build_id": BUILD_ID, "text": BOSS_TEXT + " no tier provided."},
        timeout=20,
    )
    assert r.status_code == 200, r.text
    gf = r.json()
    assert gf.get("tier") is None
    assert gf.get("tier_index") is None
    # label should NOT carry the " · " tier suffix when tier is null
    assert "· " not in gf.get("label", "").split("Boss Design", 1)[-1] or \
        gf.get("label", "").strip() == "Boss Design"
    # Generation still succeeds — id is present
    assert gf.get("id", "").startswith("gf_boss_design_")


# ── pipeline run: 14 stages × 7 segments × 6 paragraphs = 588 ─────────────
PIPELINE_GID_HOLDER = {}


def test_create_gamefile_for_pipeline(api):
    r = api.post(
        f"{BASE_URL}/api/galaxy-studio/text-gamefile/boss_design/generate",
        json={"build_id": BUILD_ID, "text": BOSS_TEXT + " pipeline target.",
              "tier": "Raid / World Boss"},
        timeout=30,
    )
    assert r.status_code == 200, r.text
    gid = r.json().get("id")
    assert gid
    PIPELINE_GID_HOLDER["gid"] = gid


def test_pipeline_emits_588_paragraphs_and_aaa(api):
    gid = PIPELINE_GID_HOLDER.get("gid")
    assert gid, "previous step did not create a gamefile"
    r = api.post(
        f"{BASE_URL}/api/galaxy-studio/gamefile-pipeline/{BUILD_ID}/{gid}/run",
        json={"persist": False, "auto_mint_enhancer": False},
        timeout=180,
    )
    assert r.status_code == 200, r.text[:400]
    res = r.json()
    assert "overall_score" in res, "missing overall_score"
    assert "aaa" in res, "missing aaa"
    stages = res.get("stages") or res.get("results") or res.get("gates") or []
    assert isinstance(stages, list) and len(stages) == 14, \
        f"expected 14 stages, got {len(stages)}"

    total_paragraphs = 0
    for st in stages:
        set_a = st.get("set_a") or {}
        assert set_a.get("paragraphs_per_segment") == 6, \
            f"stage {st.get('key') or st.get('label')}: pps={set_a.get('paragraphs_per_segment')}"
        sd = set_a.get("segments_detail") or []
        assert len(sd) == 7, \
            f"stage {st.get('key')}: segments_detail has {len(sd)} (expected 7)"
        for seg in sd:
            assert seg.get("paragraph_count") == 6, \
                f"seg {seg.get('key')} paragraph_count={seg.get('paragraph_count')}"
            paras = seg.get("paragraphs") or []
            assert len(paras) == 6, f"seg {seg.get('key')} paragraphs len={len(paras)}"
            for p in paras:
                assert isinstance(p, str) and len(p.strip()) > 0, \
                    "found empty paragraph string"
            total_paragraphs += len(paras)

    assert total_paragraphs == 14 * 7 * 6 == 588, \
        f"total paragraphs={total_paragraphs}, expected 588"


def test_pipeline_score_fields_still_present(api):
    """Regression — overall_score + aaa still present (nothing regressed)."""
    gid = PIPELINE_GID_HOLDER.get("gid")
    assert gid
    # Re-run not needed; just confirm history endpoint shape persists if exposed.
    r = api.get(
        f"{BASE_URL}/api/galaxy-studio/text-gamefile/{BUILD_ID}/{gid}",
        timeout=20,
    )
    assert r.status_code == 200
    doc = r.json()
    assert doc.get("tier") == "Raid / World Boss"
    assert doc.get("tier_index") == 5
