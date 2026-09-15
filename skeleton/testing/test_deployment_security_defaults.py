from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_compose_requires_runtime_secrets_and_limits_data_ports() -> None:
    compose = (REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8")

    assert "JWT_SECRET=${JWT_SECRET:?" in compose
    assert "MONGO_INITDB_ROOT_PASSWORD=${MONGO_INITDB_ROOT_PASSWORD:?" in compose
    assert "JWT_SECRET=${JWT_SECRET:-change-me}" not in compose
    assert "MONGO_INITDB_ROOT_PASSWORD=${MONGO_INITDB_ROOT_PASSWORD:-changeme}" not in compose
    assert '127.0.0.1:${MONGO_PORT:-27017}:27017' in compose
    assert '127.0.0.1:${CHROMA_PORT:-8000}:8000' in compose
    assert "DEBUG=${DEBUG:-false}" in compose


def test_example_env_files_do_not_ship_working_auth_secrets() -> None:
    root_env = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")
    backend_env = (REPO_ROOT / "backend" / ".env.example").read_text(encoding="utf-8")

    assert "JWT_SECRET=\n" in root_env
    assert "MONGO_INITDB_ROOT_PASSWORD=\n" in root_env
    assert "JWT_SECRET=\n" in backend_env
    assert "change-me" not in root_env
    assert "change-me" not in backend_env
