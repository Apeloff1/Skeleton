from core.exec_guard import normalize_cors_origins


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
