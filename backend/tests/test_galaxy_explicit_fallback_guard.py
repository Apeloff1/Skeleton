"""Explicit file budgets never turn unavailable source into synthetic artifacts."""
import pytest
from routes import galaxy_studio as galaxy


def test_explicit_budget_rejects_fallback_and_emergency_stubs(monkeypatch):
    build = {"title": "Finite", "genre": "rpg", "scale_info": {"explicit_target_files": 3}}
    monkeypatch.setattr(galaxy, "_phase_generic", lambda *_args: {})
    monkeypatch.setattr(galaxy, "_generate_fallback_files",
                        lambda *_args: pytest.fail("synthetic fallback must not execute"))
    with pytest.raises(galaxy.GalaxyBuildStopped, match="phase_generation_failed"):
        galaxy._call_phase_func("unknown-phase", build)


def test_implicit_budget_retains_legacy_fallback(monkeypatch):
    build = {"title": "Legacy", "genre": "rpg", "scale_info": {}}
    monkeypatch.setattr(galaxy, "_phase_generic", lambda *_args: {})
    monkeypatch.setattr(galaxy, "_generate_fallback_files", lambda *_args: {"fallback.txt": "legacy"})
    assert galaxy._call_phase_func("unknown-phase", build) == {"fallback.txt": "legacy"}
