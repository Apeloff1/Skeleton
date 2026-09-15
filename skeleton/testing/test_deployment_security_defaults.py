from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def _service_block(compose: str, service: str) -> str:
    lines = compose.splitlines()
    marker = f"  {service}:"
    start = lines.index(marker)
    block = [lines[start]]
    for line in lines[start + 1:]:
        if line.startswith("  ") and not line.startswith("    ") and line.strip().endswith(":"):
            break
        block.append(line)
    return "\n".join(block)


def test_compose_requires_runtime_secrets_authenticated_mongo_and_local_data_ports() -> None:
    compose = (REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8")

    assert "JWT_SECRET=${JWT_SECRET:?" in compose
    assert "MONGO_INITDB_ROOT_PASSWORD=${MONGO_INITDB_ROOT_PASSWORD:?" in compose
    assert "MONGO_URL=${MONGO_URL:?" in compose
    assert "SKL_MONGO_URI=${SKL_MONGO_URI:?" in compose
    assert "JWT_SECRET=${JWT_SECRET:-change-me}" not in compose
    assert "MONGO_INITDB_ROOT_PASSWORD=${MONGO_INITDB_ROOT_PASSWORD:-changeme}" not in compose
    assert "mongodb://mongo:27017/tutolage" not in compose
    assert "SKL_MONGO_URI=mongodb://mongo:27017" not in compose
    assert '127.0.0.1:${MONGO_PORT:-27017}:27017' in compose
    assert '127.0.0.1:${CHROMA_PORT:-8000}:8000' in compose
    assert "DEBUG=${DEBUG:-false}" in compose
    assert "--authenticationDatabase admin" in compose
    assert "$${MONGO_INITDB_ROOT_PASSWORD}" in compose


def test_compose_pins_stateful_images_and_hardens_non_root_app_services() -> None:
    compose = (REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    skeleton = _service_block(compose, "skeleton")
    backend = _service_block(compose, "backend")
    mongo = _service_block(compose, "mongo")
    chroma = _service_block(compose, "chroma")

    assert "image: mongo:7.0.41@sha256:" in mongo
    assert "image: chromadb/chroma:latest@sha256:" in chroma
    assert "image: mongo:7.0\n" not in mongo
    assert "image: chromadb/chroma:latest\n" not in chroma

    for service in (skeleton, backend):
        assert "security_opt:\n      - no-new-privileges:true" in service
        assert "cap_drop:\n      - ALL" in service


def test_compose_healthchecks_use_runtime_available_tools_and_canonical_routes() -> None:
    compose = (REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    skeleton = _service_block(compose, "skeleton")
    backend = _service_block(compose, "backend")

    assert "python" in skeleton
    assert "http://127.0.0.1:8001/api/v1/health/live" in skeleton
    assert "python" in backend
    assert "http://127.0.0.1:8001/api/health" in backend
    assert '"curl"' not in backend
    assert "http://localhost:8001/health" not in skeleton


def test_example_env_files_do_not_ship_working_auth_or_database_credentials() -> None:
    root_env = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")
    backend_env = (REPO_ROOT / "backend" / ".env.example").read_text(encoding="utf-8")

    assert "JWT_SECRET=\n" in root_env
    assert "MONGO_INITDB_ROOT_PASSWORD=\n" in root_env
    assert "MONGO_URL=\n" in root_env
    assert "SKL_MONGO_URI=\n" in root_env
    assert "JWT_SECRET=\n" in backend_env
    assert "MONGO_URL=\n" in backend_env
    assert "change-me" not in root_env
    assert "change-me" not in backend_env
    assert "mongodb://localhost:27017" not in root_env
    assert "mongodb://localhost:27017" not in backend_env
