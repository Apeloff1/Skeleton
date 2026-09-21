from __future__ import annotations

from skeleton.app.bootstrap import public_bootstrap_payload


def test_public_bootstrap_is_dependency_closed_and_sanitized():
    payload = public_bootstrap_payload()

    assert payload["schema_version"] == 1
    assert payload["application"]["name"] == "Skeleton"
    assert payload["application"]["version"] == "16"

    services = {item["name"]: item for item in payload["services"]}
    assert {"frontend", "backend", "skeleton", "mongo"}.issubset(services)
    assert services["backend"]["health_path"] == "/api/health"
    assert services["skeleton"]["health_path"] == "/api/v1/health/live"

    default = payload["profiles"]["default"]
    assert set(default["services"]) == {"mongo", "backend", "skeleton", "frontend"}
    assert default["layers"][0] == ["mongo"]
    assert default["layers"][-1] == ["frontend"]

    serialized = repr(payload)
    for forbidden in ("required_env", "optional_env", "public_url", "container_port", "entrypoint"):
        assert forbidden not in serialized


def test_public_bootstrap_full_profile_contains_default_profile():
    payload = public_bootstrap_payload()

    default = set(payload["profiles"]["default"]["services"])
    full = set(payload["profiles"]["full"]["services"])

    assert default.issubset(full)
    assert "chroma" in full
