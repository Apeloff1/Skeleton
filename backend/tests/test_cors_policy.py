from core import exec_guard
from core.exec_guard import configure_cors_environment, normalize_cors_origins


def test_production_unset_and_blank_fail_closed():
    assert normalize_cors_origins(None, production=True) == ("https://cors-disabled.invalid",)
    assert normalize_cors_origins("   ", production=True) == ("https://cors-disabled.invalid",)


def test_production_wildcard_fails_closed(monkeypatch):
    monkeypatch.setenv("ALLOW_DEV_CORS_WILDCARD", "true")
    assert normalize_cors_origins("*", production=True) == ("https://cors-disabled.invalid",)


def test_development_wildcard_requires_explicit_opt_in(monkeypatch):
    monkeypatch.delenv("ALLOW_DEV_CORS_WILDCARD", raising=False)
    assert normalize_cors_origins("*", production=False) == (
        "http://localhost",
        "http://127.0.0.1",
    )
    monkeypatch.setenv("ALLOW_DEV_CORS_WILDCARD", "true")
    assert normalize_cors_origins("*", production=False) == ("*",)


def test_explicit_origins_are_normalized_and_deduplicated():
    assert normalize_cors_origins(
        " https://example.com/,https://example.com, http://localhost:3000/ ",
        production=True,
    ) == ("https://example.com", "http://localhost:3000")


def test_invalid_origins_fail_closed():
    assert normalize_cors_origins("example.com,ftp://example.com/path", production=True) == (
        "https://cors-disabled.invalid",
    )


def test_partially_invalid_origins_fail_closed():
    assert normalize_cors_origins("https://good.example,not-an-origin", production=True) == (
        "https://cors-disabled.invalid",
    )
    assert normalize_cors_origins("https://good.example,not-an-origin", production=False) == (
        "http://localhost",
        "http://127.0.0.1",
    )


def test_configuration_loads_dotenv_before_normalizing(monkeypatch):
    """An explicit backend .env value must win before import-time normalization."""
    monkeypatch.delenv("CORS_ORIGINS", raising=False)
    monkeypatch.delenv("EMERGENT_DEPLOY", raising=False)
    monkeypatch.delenv("ENVIRONMENT", raising=False)

    def fake_load_dotenv(path):
        assert str(path).endswith("/backend/.env")
        monkeypatch.setenv("CORS_ORIGINS", "https://configured.example/")
        return True

    monkeypatch.setattr(exec_guard, "load_dotenv", fake_load_dotenv)
    assert configure_cors_environment() == ("https://configured.example",)
    assert exec_guard.os.environ["CORS_ORIGINS"] == "https://configured.example"
