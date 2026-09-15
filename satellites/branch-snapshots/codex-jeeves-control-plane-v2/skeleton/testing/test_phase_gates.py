"""Blueprint phase-gate ladder tests (Prood phase_gates port — synthetic manifests)."""
from __future__ import annotations

from skeleton.forge import phase_gates as pg


def _clean_manifest(**overrides):
    """Minimal manifest that satisfies every gate for the clean-path test."""
    m = {
        "era": "modern_aaa",
        "era_label": "Modern AAA",
        "awareness": {"era": "modern_aaa", "choices_logged": 3},
        "ladder": [
            {
                "stage": "hub",
                "grade_floor": 1,
                "parity_ok": True,
                "quality": {"all_passed": True},
            },
            {
                "stage": "world",
                "grade_floor": 2,
                "parity_ok": True,
                "quality": {"all_passed": True},
            },
            {
                "stage": "narrative",
                "grade_floor": 3,
                "parity_ok": True,
                "quality": {"all_passed": True},
            },
        ],
        "parity_locked": True,
        "parity_pct": 100,
        "plan_hash": "deadbeefcafebabe0123456789abcdef",
        "storage": {
            "used_pct": 42,
            "used_label": "420 MB",
            "cap_label": "1 GB",
        },
        "capacity": {
            "assets_forged": 4,
            "asset_capacity": 64,
            "utilization_pct": 6,
        },
        "choice_gates": {"all_reflected": True},
    }
    m.update(overrides)
    return m


def _assets(forged: int = 4, families=None):
    return {"forged": forged, "families": families or ["tiles", "sprites"]}


def test_phase_gates_100_phases_eight_bands():
    out = pg.build(_clean_manifest(), _assets())
    assert out["advanced_phases"] == 100
    assert out["phases_total"] == 100
    assert out["bands_total"] == 8
    assert len(out["phases"]) == 100
    assert len(out["bands"]) == 8
    assert all("gate" in p for p in out["phases"])


def test_phase_gates_band_ranges_cover_1_to_100():
    out = pg.build(_clean_manifest(), _assets())
    covered = []
    for b in out["bands"]:
        covered.extend(range(b["phase_range"][0], b["phase_range"][1] + 1))
    assert sorted(covered) == list(range(1, 101))


def test_phase_gates_pass_on_clean_manifest():
    out = pg.build(_clean_manifest(), _assets())
    assert out["all_gates_green"] is True
    assert out["pass_pct"] == 100
    assert out["bands_passed"] == 8
    assert out["asset_grounded"] is True
    assert out["forged_assets"] == 4
    assert out["file_plan"]["era"] == "modern_aaa"
    assert out["file_plan"]["file_target"] == pg.DEFAULT_FILE_TARGET


def test_phase_gates_missing_plan_hash_fails_determinism():
    m = _clean_manifest()
    m.pop("plan_hash")
    out = pg.build(m, _assets())
    by_gate = {b["gate"]: b for b in out["bands"]}
    assert by_gate["determinism"]["passed"] is False
    assert by_gate["all_green"]["passed"] is False
    assert out["all_gates_green"] is False
    # Procedural band (determinism) phases all fail
    proc = [p for p in out["phases"] if p["gate"] == "determinism"]
    assert proc and all(p["passed"] is False for p in proc)


def test_phase_gates_choices_locked_requires_era_and_choices():
    m = _clean_manifest(awareness={"era": None, "choices_logged": 0})
    out = pg.build(m, _assets())
    by_gate = {b["gate"]: b for b in out["bands"]}
    assert by_gate["choices_locked"]["passed"] is False
    assert by_gate["all_green"]["passed"] is False
    assert out["all_gates_green"] is False


def test_phase_gates_phases_inherit_band_verdict():
    m = _clean_manifest()
    m.pop("plan_hash")
    out = pg.build(m, _assets())
    for band in out["bands"]:
        band_phases = [p for p in out["phases"] if p["band"] == band["band"]]
        assert band_phases
        assert all(p["passed"] is band["passed"] for p in band_phases)
        assert all(p["gate"] == band["gate"] for p in band_phases)


def test_phase_gates_capacity_requires_forged_assets():
    out = pg.build(_clean_manifest(), assets=None)
    by_gate = {b["gate"]: b for b in out["bands"]}
    assert by_gate["capacity"]["passed"] is False
    assert out["asset_grounded"] is False
    assert out["all_gates_green"] is False


def test_phase_gates_file_target_injection():
    out = pg.build(_clean_manifest(), _assets(), file_target=500)
    assert out["file_plan"]["file_target"] == 500
    # Band weights sum to 1.0 → round(500 * w) across bands ≈ 500
    total = sum(b["file_target"] for b in out["bands"])
    assert total == sum(
        round(500 * pg._BAND_FILE_WEIGHT[b["band"]]) for b in out["bands"]
    )
    out2 = pg.build(_clean_manifest(), _assets(), era_file_target=2000)
    assert out2["file_plan"]["file_target"] == 2000


def test_phase_gates_gate_keys_identical_to_prood():
    expected = {
        "choices_locked",
        "world_quality",
        "gdd_parity",
        "grade_escalation",
        "determinism",
        "storage_tracked",
        "capacity",
        "all_green",
    }
    out = pg.build(_clean_manifest(), _assets())
    assert {b["gate"] for b in out["bands"]} == expected
