"""Tests for the 7-stage Final Build pipeline + 95 gate + completeness."""
from urllib.parse import urlsplit

from core import final_build as fb
from core import forge_quality


def _trusted_build_download_url(value: object) -> bool:
    """Require an exact HTTPS CDN authority, not a matching URL substring."""
    if type(value) is not str or not 1 <= len(value) <= 2048 or "\\\\" in value:
        return False
    try:
        parsed = urlsplit(value)
        return (
            parsed.scheme == "https"
            and parsed.netloc == "cdn.galaxy.studio"
            and parsed.hostname == "cdn.galaxy.studio"
            and parsed.username is None
            and parsed.password is None
            and parsed.port is None
            and not parsed.query
            and not parsed.fragment
            and parsed.path.startswith("/builds/")
            and "//" not in parsed.path
            and "/../" not in parsed.path
        )
    except ValueError:
        return False


def _pkg(era="modern", seed=5, platforms=None):
    return fb.build_package("fb_test", genre="rpg", era=era, seed=seed,
                            platforms=platforms or ["windows", "android"],
                            config={"graphic_style": "cel_shaded", "dimension": "3d"},
                            persist=False)


def test_seven_stages_present():
    r = _pkg()
    assert len(r["stages"]) == 7
    steps = [s["step"] for s in r["stages"]]
    assert steps == [1, 2, 3, 4, 5, 6, 7]
    names = [s["stage"] for s in r["stages"]]
    assert "Build Orchestrator" in names[0]
    assert "Distribution Prep" in names[-1]


def test_every_stage_has_verification_gate():
    r = _pkg()
    for s in r["stages"]:
        assert "gate" in s and "passed" in s["gate"] and "score" in s["gate"]
    assert r["gates_total"] == 7


def test_95_production_threshold():
    r = _pkg()
    assert r["production_threshold"] == forge_quality.PRODUCTION_THRESHOLD == 95
    # passing gates require score >= 95
    for s in r["stages"]:
        if s["gate"]["passed"]:
            assert s["gate"]["score"] >= 95


def test_completeness_gate_and_shipping():
    r = _pkg()
    assert r["completeness"]["complete"] is True
    assert r["completeness"]["stages_covered"] == r["completeness"]["stages_expected"]
    assert r["totals"]["gamefiles"] > 0
    assert r["can_ship"] is True
    assert r["status"] == "ready_to_download"


def test_platform_builds_and_downloads():
    r = _pkg(platforms=["windows", "macos", "linux", "android", "ios"])
    assert len(r["platforms"]) == 5
    assert len(r["downloads"]) == 5
    assert all(_trusted_build_download_url(d["url"]) for d in r["downloads"])


def test_gdd_reflects_choices_gates_platforms():
    r = _pkg()
    g = r["gdd"]
    assert "Final Build & Packaging" in g
    assert "Platforms:" in g
    assert "Locked choices:" in g
    assert "graphic_style=cel_shaded" in g
