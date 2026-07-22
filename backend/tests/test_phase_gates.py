"""Tests for the 100-phase advanced gate ladder + snowball questionnaire."""
from core import phase_gates as pg
from core import snowball_forge as sf
from core import snowball_questionnaire as sq


def _manifest(era="modern", seed=5):
    return sf.escalate("pg_test", genre="rpg", seed=seed, era=era, persist=False)


def test_phase_gates_100_phases():
    out = pg.build(_manifest())
    assert out["advanced_phases"] == 100
    assert out["phases_total"] == 100
    assert out["bands_total"] == 8
    assert len(out["phases"]) == 100
    # phases inherit their band's verdict
    assert all("gate" in p for p in out["phases"])


def test_phase_gates_pass_on_clean_build():
    out = pg.build(_manifest())
    assert out["all_gates_green"] is True
    assert out["pass_pct"] == 100
    assert out["bands_passed"] == 8


def test_phase_gates_band_ranges_cover_1_to_100():
    out = pg.build(_manifest())
    covered = []
    for b in out["bands"]:
        covered.extend(range(b["phase_range"][0], b["phase_range"][1] + 1))
    assert sorted(covered) == list(range(1, 101))


def test_questionnaire_conformance():
    q = sq.build(_manifest(era="8bit"))
    assert q["era"] == "8bit"
    assert q["total"] >= 8
    assert q["conformance_pct"] == 100
    assert q["all_conformant"] is True
    ids = {it["id"] for it in q["items"]}
    assert {"era_locked", "gdd_parity_every_step", "assets_era_appropriate"} <= ids


def test_questionnaire_per_stage_snowball():
    q = sq.build(_manifest())
    stage_qs = [it for it in q["items"] if it["id"].endswith("_snowball")]
    assert len(stage_qs) == 6  # one per item stage
    assert all(it["passed"] for it in stage_qs)
