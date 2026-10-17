"""Observability-as-code contract: dashboards and alerts only reference metrics
that backend/core/observability.py actually exposes at /api/metrics."""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
OBS = ROOT / "deploy" / "observability"
PROM_BUILTINS = {"up"}
FUNCS = {"max", "min", "sum", "avg", "topk", "rate", "delta", "increase", "by", "count"}


def _load_backend_observability():
    spec = importlib.util.spec_from_file_location(
        "_backend_observability_under_test", ROOT / "backend" / "core" / "observability.py"
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def _exposed_metric_names(text: str) -> set[str]:
    names = set()
    for line in text.splitlines():
        if line and not line.startswith("#"):
            names.add(re.split(r"[{\s]", line, maxsplit=1)[0])
    return names


def _metrics_in_expr(expr: str) -> set[str]:
    stripped = re.sub(r"\{[^}]*\}", "", expr)
    stripped = re.sub(r"\[[^\]]*\]", "", stripped)
    tokens = set(re.findall(r"[a-zA-Z_:][a-zA-Z0-9_:]*", stripped))
    return {t for t in tokens if t not in FUNCS}


def _exposition(monkeypatch, **env):
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    mod = _load_backend_observability()
    mod.LATENCY.observe("/api/health", 12.5)
    return mod.prom_metrics()


def test_exposition_includes_build_info_and_uptime(monkeypatch):
    text = _exposition(monkeypatch, APP_VERSION="16.1.0", ENVIRONMENT="staging")
    assert 'codedock_build_info{version="16.1.0",environment="staging"} 1' in text
    assert re.search(r"^codedock_process_uptime_seconds \d+(\.\d+)?$", text, re.M)
    assert 'codedock_http_latency_ms_count{path="/api/health"} 1' in text


def test_build_info_labels_are_sanitised(monkeypatch):
    text = _exposition(monkeypatch, APP_VERSION='1"2\n3\\x', ENVIRONMENT="prod")
    assert 'version="12 3x"' in text


def test_build_version_defaults_to_dev(monkeypatch):
    monkeypatch.delenv("APP_VERSION", raising=False)
    assert 'version="dev"' in _exposition(monkeypatch)


def _dashboard_exprs():
    for path in sorted((OBS / "grafana" / "dashboards").glob("*.json")):
        board = json.loads(path.read_text())
        assert board["uid"] and board["title"]
        for panel in board["panels"]:
            assert panel["datasource"]["uid"] == "prometheus"
            for target in panel["targets"]:
                yield path.name, target["expr"]


def _alert_exprs():
    doc = yaml.safe_load((OBS / "prometheus" / "alerts.yml").read_text())
    for group in doc["groups"]:
        for rule in group["rules"]:
            assert rule["labels"]["severity"] in {"critical", "warning", "info"}
            yield rule["alert"], rule["expr"]


def test_dashboards_and_alerts_reference_only_exposed_metrics(monkeypatch):
    exposed = _exposed_metric_names(_exposition(monkeypatch)) | PROM_BUILTINS
    exprs = list(_dashboard_exprs()) + list(_alert_exprs())
    assert exprs
    for name, expr in exprs:
        missing = _metrics_in_expr(expr) - exposed
        assert not missing, f"{name}: {expr!r} references unexposed metrics {missing}"


def test_prometheus_scrapes_backend_metrics_path_and_loads_alerts():
    cfg = yaml.safe_load((OBS / "prometheus" / "prometheus.yml").read_text())
    job = next(j for j in cfg["scrape_configs"] if j["job_name"] == "tutolage-backend")
    assert job["metrics_path"] == "/api/metrics"
    assert job["static_configs"][0]["targets"] == ["backend:8001"]
    assert "/etc/prometheus/alerts.yml" in cfg["rule_files"]


def test_observability_compose_mounts_existing_files_and_binds_localhost():
    doc = yaml.safe_load((ROOT / "docker-compose.observability.yml").read_text())
    for name in ("prometheus", "grafana"):
        svc = doc["services"][name]
        assert ":latest" not in svc["image"]
        for port in svc["ports"]:
            assert port.startswith("127.0.0.1:")
        for vol in svc["volumes"]:
            src = vol.split(":")[0]
            assert (ROOT / src).exists(), src
