"""Registration and syntax inventory never turn existence into readiness."""
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI

from gameforge.coverage_inventory import InventoryCache, scan_sources
from routes import gameforge_coverage as route


def test_ast_is_nonexecuting_and_ignores_string_declarations(tmp_path):
    (tmp_path / "engine.py").write_text(
        'raise RuntimeError("must not execute")\nclass ActualEngine: pass\n'
        'text = """class FakeSystem: pass"""\n', encoding="utf-8")
    (tmp_path / "broken.py").write_text("class BrokenEngine(\n", encoding="utf-8")
    result = scan_sources(tmp_path)
    assert not result.complete
    assert result.errors == 1
    assert [r.classes for r in result.engine_records] == [("ActualEngine",)]
    assert result.summary()["live"] == 0
    assert result.summary()["runtime_qualified"] is False
    assert result.page(0, 1)["records"][0]["path"] == "gameforge/engine.py"
    assert result.page(0, 1, "errors")["records"][0]["status"] == "syntax_error"


def test_manifest_tracks_exact_source_changes_and_is_stable(tmp_path):
    engine = tmp_path / "module.py"
    engine.write_text("class QuestEngine: pass\n", encoding="utf-8")
    first = scan_sources(tmp_path)
    second = scan_sources(tmp_path)
    assert first.complete and first.manifest_sha256 == second.manifest_sha256
    engine.write_text("class QuestEngine: pass\n# changed\n", encoding="utf-8")
    assert scan_sources(tmp_path).manifest_sha256 != first.manifest_sha256


def test_source_symlink_is_not_followed(tmp_path):
    import pytest
    outside = tmp_path / "outside.py"
    outside.write_text("class ExternalEngine: pass\n", encoding="utf-8")
    source = tmp_path / "source"
    source.mkdir()
    try:
        (source / "link.py").symlink_to(outside)
    except OSError:
        pytest.skip("symlink creation unavailable")
    result = scan_sources(source)
    assert not result.complete and result.errors == 1
    assert result.records[0].status == "nonregular_source"
    assert not result.engine_records


def test_budget_exhaustion_is_visible(tmp_path, monkeypatch):
    from gameforge import coverage_inventory as module
    (tmp_path / "a.py").write_text("class AEngine: pass\n")
    (tmp_path / "b.py").write_text("class BEngine: pass\n")
    monkeypatch.setattr(module, "_MAX_FILES", 1)
    result = scan_sources(tmp_path)
    assert not result.complete and result.stop_reason == "scan_budget_reached"


def test_registered_routes_are_not_executed_or_marked_live(tmp_path, monkeypatch):
    app = FastAPI()
    @app.get("/api/auth/me")
    async def never():
        raise AssertionError("registration check must never invoke a handler")
    monkeypatch.setattr(route, "_INVENTORY", InventoryCache(tmp_path))
    request = SimpleNamespace(app=app)
    report = route.coverage(request)
    assert report["overall_percent"] is None
    assert report["registered_subsystems"] == 1
    assert all(z["percent"] is None for z in report["zip_audit"])
    assert report["engines"]["live"] == 0
    assert report["subsystems"][0]["status"] == "registered"
    assert route.selftest(request)["ready"] is False
    assert route.activate()["activated"] == 0
