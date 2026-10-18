"""Security regression: optional router failures never reveal exception payloads."""

from fastapi import FastAPI

from core import routes_registry


def test_router_import_failure_reports_only_exception_class(monkeypatch, capsys):
    secret = "private-route-import-secret-do-not-print"

    def fail_import(_name: str):
        raise RuntimeError(secret)

    monkeypatch.setattr(routes_registry.importlib, "import_module", fail_import)
    app = FastAPI()
    report = routes_registry.register_routes(app, [("routes.optional_feature", "router")])
    captured = capsys.readouterr()

    assert report["ok"] == 0
    assert report["skipped"] == 1
    assert "RuntimeError" in report["skipped_names"][0]
    assert secret not in str(report)
    assert secret not in captured.out
    assert secret not in captured.err
    assert "RuntimeError" in captured.err
