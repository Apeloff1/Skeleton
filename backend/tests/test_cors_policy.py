from __future__ import annotations

from pathlib import Path

from core.exec_guard import configure_cors_environment, normalize_cors_origins


_DEPLOYMENT_KEYS = (
    "EMERGENT_DEPLOY",
    "ENVIRONMENT",
    "K_SERVICE",
    "KUBERNETES_SERVICE_HOST",
    "WEBSITE_INSTANCE_ID",
    "DYNO",
)


def _clear_deployment(monkeypatch) -> None:
    for key in _DEPLOYMENT_KEYS:
        monkeypatch.delenv(key, raising=False)


def test_production_unset_and_blank_fail_closed(monkeypatch, tmp_path: Path) -> None:
    _clear_deployment(monkeypatch)
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.delenv("CORS_ORIGINS", raising=False)
    empty = tmp_path / ".env"
    empty.write_text("", encoding="utf-8")

    assert configure_cors_environment(empty) == ("https://cors-disabled.invalid",)

    monkeypatch.setenv("CORS_ORIGINS", "   ")
    assert configure_cors_environment(empty) == ("https://cors-disabled.invalid",)


def test_dotenv_origin_is_resolved_before_synthetic_development_default(
    monkeypatch, tmp_path: Path
) -> None:
    _clear_deployment(monkeypatch)
    monkeypatch.delenv("CORS_ORIGINS", raising=False)
    monkeypatch.delenv("ALLOW_DEV_CORS_WILDCARD", raising=False)
    dotenv = tmp_path / ".env"
    dotenv.write_text(
        "ENVIRONMENT=development\nCORS_ORIGINS=https://app.local.example/\n",
        encoding="utf-8",
    )

    assert configure_cors_environment(dotenv) == ("https://app.local.example",)
    assert __import__("os").environ["CORS_ORIGINS"] == "https://app.local.example"


def test_process_environment_wins_over_dotenv(monkeypatch, tmp_path: Path) -> None:
    _clear_deployment(monkeypatch)
    monkeypatch.setenv("CORS_ORIGINS", "https://process.example")
    monkeypatch.setenv("ENVIRONMENT", "production")
    dotenv = tmp_path / ".env"
    dotenv.write_text(
        "ENVIRONMENT=development\nCORS_ORIGINS=https://dotenv.example\n",
        encoding="utf-8",
    )

    assert configure_cors_environment(dotenv) == ("https://process.example",)


def test_dotenv_production_marker_fails_closed_before_server_load_dotenv(
    monkeypatch, tmp_path: Path
) -> None:
    _clear_deployment(monkeypatch)
    monkeypatch.delenv("CORS_ORIGINS", raising=False)
    dotenv = tmp_path / ".env"
    dotenv.write_text("ENVIRONMENT=production\n", encoding="utf-8")

    assert configure_cors_environment(dotenv) == ("https://cors-disabled.invalid",)


def test_development_wildcard_requires_explicit_opt_in(monkeypatch, tmp_path: Path) -> None:
    _clear_deployment(monkeypatch)
    monkeypatch.delenv("CORS_ORIGINS", raising=False)
    monkeypatch.delenv("ALLOW_DEV_CORS_WILDCARD", raising=False)
    dotenv = tmp_path / ".env"
    dotenv.write_text("CORS_ORIGINS=*\n", encoding="utf-8")

    assert configure_cors_environment(dotenv) == (
        "http://localhost",
        "http://127.0.0.1",
    )

    dotenv.write_text(
        "CORS_ORIGINS=*\nALLOW_DEV_CORS_WILDCARD=true\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("CORS_ORIGINS", raising=False)
    assert configure_cors_environment(dotenv) == ("*",)


def test_production_wildcard_fails_closed_even_with_dev_opt_in() -> None:
    assert normalize_cors_origins(
        "*", production=True, allow_dev_wildcard=True
    ) == ("https://cors-disabled.invalid",)


def test_explicit_origins_are_normalized_and_deduplicated() -> None:
    assert normalize_cors_origins(
        " https://example.com/,https://example.com, http://localhost/ ",
        production=True,
    ) == ("https://example.com", "http://localhost")


def test_invalid_or_partially_invalid_origins_fail_closed() -> None:
    invalid_values = (
        "example.com",
        "ftp://example.com",
        "https://user:pass@example.com",
        "https://example.com/path",
        "https://example.com?query=1",
        "https://example.com#fragment",
        "https://example.com:99999",
        "https://good.example,not-an-origin",
    )
    for raw in invalid_values:
        assert normalize_cors_origins(raw, production=True) == (
            "https://cors-disabled.invalid",
        )


def test_local_invalid_origin_falls_back_to_loopback_only() -> None:
    assert normalize_cors_origins("https://good.example,not-an-origin", production=False) == (
        "http://localhost",
        "http://127.0.0.1",
    )


def test_blank_process_value_does_not_fall_through_to_dotenv(
    monkeypatch, tmp_path: Path
) -> None:
    _clear_deployment(monkeypatch)
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("CORS_ORIGINS", "")
    dotenv = tmp_path / ".env"
    dotenv.write_text("CORS_ORIGINS=https://dotenv.example\n", encoding="utf-8")

    assert configure_cors_environment(dotenv) == ("https://cors-disabled.invalid",)
