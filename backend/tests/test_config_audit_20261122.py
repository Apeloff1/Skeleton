"""Startup config audit: advisory findings that never leak values."""

from __future__ import annotations

import ast
import logging
from pathlib import Path

import pytest

from core.config_audit import audit_config, log_config_audit

SECRET = "p" * 48
PROD_OK = {
    "APP_ENV": "production",
    "PROVENANCE_SECRET": SECRET,
    "GAMEFORGE_JWT_SECRET": "j" * 48,
    "MONGO_URL": "mongodb+srv://cluster0.example.net/app",
    "CORS_ORIGINS": "https://app.example.com",
}


def codes(env: dict[str, str]) -> set[str]:
    return {f.code for f in audit_config(env)}


def test_well_configured_production_has_no_findings():
    assert audit_config(PROD_OK) == []


def test_production_without_provenance_secret_warns_only():
    env = {k: v for k, v in PROD_OK.items() if k != "PROVENANCE_SECRET"}
    findings = audit_config(env)
    assert [(f.code, f.severity, f.variable) for f in findings] == [
        ("provenance_secret_unset", "warning", "PROVENANCE_SECRET")
    ]
    assert "MONGO_URL fallback" in findings[0].message


def test_provenance_unset_outside_production_is_silent_but_weak_secret_warns():
    assert codes({}) == set()
    assert codes({"PROVENANCE_SECRET": "short"}) == {"provenance_secret_weak"}


def test_provenance_key_derivation_is_unchanged():
    # The audit is warn-only: the ledger still derives its key exactly as before.
    source = (Path(__file__).resolve().parents[1] / "core" / "provenance_ledger.py").read_text(encoding="utf-8")
    assert 'os.environ.get("PROVENANCE_SECRET") or os.environ.get("MONGO_URL") or "emergent-provenance-v1"' in source


@pytest.mark.parametrize(
    ("override", "expected"),
    [
        ({"GAMEFORGE_AUTH_ENFORCE": "false"}, "auth_disabled_in_production"),
        ({"GAMEFORGE_AUTH_ENFORCE": "maybe"}, "auth_enforce_invalid"),
        ({"GAMEFORGE_JWT_SECRET": ""}, "jwt_secret_missing"),
        ({"MONGO_URL": "mongodb://localhost:27017"}, "mongo_url_local_default"),
        ({"CORS_ORIGINS": "*"}, "cors_wildcard_in_production"),
        ({"STRIPE_API_KEY": "sk_test_x"}, "stripe_webhook_secret_missing"),
    ],
)
def test_production_findings(override: dict[str, str], expected: str):
    assert expected in codes({**PROD_OK, **override})


def test_jwt_secret_file_counts_as_configured():
    env = {**PROD_OK, "GAMEFORGE_JWT_SECRET": "", "GAMEFORGE_JWT_SECRET_FILE": "/run/secrets/jwt"}
    assert "jwt_secret_missing" not in codes(env)


def test_findings_never_contain_values(caplog: pytest.LogCaptureFixture):
    # Synthetic sentinel: never put a real credential-bearing URI in source.
    password = "hunter2-password"
    env = {
        "APP_ENV": "production",
        "PROVENANCE_SECRET": "tiny",
        "GAMEFORGE_AUTH_ENFORCE": "nonsense-flag",
        "MONGO_URL": f"mongodb://fixture-user:{password}@localhost/app",
        "STRIPE_API_KEY": "sk_live_should_not_print",
        "CORS_ORIGINS": "*",
    }
    with caplog.at_level(logging.WARNING):
        findings = log_config_audit(logging.getLogger("test.audit"), env)
    assert len(findings) >= 5
    rendered = caplog.text + repr([f.as_dict() for f in findings])
    for value in ("tiny", "nonsense-flag", password, "sk_live_should_not_print"):
        assert value not in rendered


def test_lifespan_runs_the_audit_without_blocking_boot():
    tree = ast.parse((Path(__file__).resolve().parents[1] / "server.py").read_text(encoding="utf-8"))
    lifespan = next(n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef) and n.name == "lifespan")
    guarded = [
        node
        for node in ast.walk(lifespan)
        if isinstance(node, ast.Try)
        and any(isinstance(c, ast.ImportFrom) and c.module == "core.config_audit" for c in ast.walk(node))
    ]
    assert len(guarded) == 1 and guarded[0].handlers
