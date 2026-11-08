from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def _compose_service_block(service: str, next_service: str) -> str:
    compose = (REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    return compose.split(f"  {service}:\n", 1)[1].split(f"\n  {next_service}:\n", 1)[0]


def test_skeleton_compose_healthcheck_uses_public_liveness_contract() -> None:
    skeleton = _compose_service_block("skeleton", "backend")

    assert "/api/v1/health/live" in skeleton
    assert "timeout=5" in skeleton
    assert "http://localhost:8001/health')" not in skeleton


def test_dockerfile_and_compose_share_skeleton_liveness_path() -> None:
    dockerfile = (REPO_ROOT / "Dockerfile").read_text(encoding="utf-8")
    skeleton = _compose_service_block("skeleton", "backend")
    liveness_path = "/api/v1/health/live"

    assert liveness_path in dockerfile
    assert liveness_path in skeleton


def test_skeleton_healthcheck_stays_loopback_only() -> None:
    skeleton = _compose_service_block("skeleton", "backend")

    assert "http://127.0.0.1:8001/api/v1/health/live" in skeleton


def test_first_install_application_ports_enforce_literal_loopback() -> None:
    """No environment-only opt-in to publish protected app APIs to the LAN."""
    skeleton = _compose_service_block("skeleton", "backend")
    backend = _compose_service_block("backend", "frontend")
    frontend = _compose_service_block("frontend", "mongo")
    assert '"127.0.0.1:${SKELETON_PORT:-8010}:8001"' in skeleton
    assert '"127.0.0.1:${BACKEND_PORT:-8001}:8001"' in backend
    assert '"127.0.0.1:${FRONTEND_PORT:-3000}:${FRONTEND_CONTAINER_PORT:-3000}"' in frontend
    source = (REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    for name in ("APP_BIND_HOST", "SKELETON_BIND_HOST", "BACKEND_BIND_HOST", "FRONTEND_BIND_HOST"):
        assert "${" + name not in source


def test_first_install_ui_remains_independent_of_backend() -> None:
    frontend = _compose_service_block("frontend", "mongo")
    assert "depends_on:" not in frontend
    assert "EXPO_PUBLIC_BACKEND_URL" in frontend


def test_private_store_ports_and_required_auth_stay_guarded() -> None:
    source = (REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    assert "SKL_ENGINE_SERVICE_TOKEN=${SKL_ENGINE_SERVICE_TOKEN:?" in source
    assert "JWT_SECRET=${JWT_SECRET:?" in source
    assert '"127.0.0.1:${MONGO_PORT:-27017}:27017"' in source
    assert '"127.0.0.1:${CHROMA_PORT:-8000}:8000"' in source
    assert "condition: service_healthy" in source
