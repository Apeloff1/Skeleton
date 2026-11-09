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
