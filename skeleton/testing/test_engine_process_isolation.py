from __future__ import annotations

import ast
import json
from importlib import resources
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _compose() -> str:
    return (ROOT / "docker-compose.yml").read_text(encoding="utf-8")


def _service_block(source: str, service: str, next_service: str) -> str:
    start = f"  {service}:"
    end = f"\n  {next_service}:"
    assert start in source
    assert end in source
    return source.split(start, 1)[1].split(end, 1)[0]


def _manifest() -> dict[str, object]:
    return json.loads(
        resources.files("skeleton.app")
        .joinpath("manifest.json")
        .read_text(encoding="utf-8")
    )


def _provider_registry_names(tree: ast.AST) -> set[str]:
    names = {"ProviderRegistry"}
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom):
            continue
        for alias in node.names:
            if alias.name == "ProviderRegistry":
                names.add(alias.asname or alias.name)
    return names


def _is_provider_registry_from_env_call(node: ast.Call, names: set[str]) -> bool:
    func = node.func
    if not isinstance(func, ast.Attribute) or func.attr != "from_env":
        return False
    receiver = func.value
    if isinstance(receiver, ast.Name):
        return receiver.id in names
    return isinstance(receiver, ast.Attribute) and receiver.attr == "ProviderRegistry"


def _local_provider_consumers() -> tuple[str, ...]:
    consumers: list[str] = []
    for path in sorted((ROOT / "backend").rglob("*.py")):
        relative = path.relative_to(ROOT).as_posix()
        if "/tests/" in "/" + relative:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=relative)
        names = _provider_registry_names(tree)
        if any(
            isinstance(node, ast.Call)
            and _is_provider_registry_from_env_call(node, names)
            for node in ast.walk(tree)
        ):
            consumers.append(relative)
    return tuple(consumers)


def test_provider_registry_activation_detection_covers_alias_and_qualified_calls() -> None:
    alias_tree = ast.parse(
        "from skeleton.provider_runtime import ProviderRegistry as Registry\n"
        "Registry.from_env()\n"
    )
    alias_names = _provider_registry_names(alias_tree)
    alias_calls = [node for node in ast.walk(alias_tree) if isinstance(node, ast.Call)]
    assert any(
        _is_provider_registry_from_env_call(node, alias_names)
        for node in alias_calls
    )

    qualified_tree = ast.parse(
        "import skeleton.provider_runtime as provider_runtime\n"
        "provider_runtime.ProviderRegistry.from_env()\n"
    )
    qualified_names = _provider_registry_names(qualified_tree)
    qualified_calls = [
        node for node in ast.walk(qualified_tree) if isinstance(node, ast.Call)
    ]
    assert any(
        _is_provider_registry_from_env_call(node, qualified_names)
        for node in qualified_calls
    )


def test_remaining_local_provider_consumers_are_media_only() -> None:
    assert set(_local_provider_consumers()) == {
        "backend/core/expressive_tts.py",
        "backend/routes/image_generation.py",
    }


def test_runtime_provider_credentials_follow_parity_cutover_state() -> None:
    compose = _compose()
    skeleton = _service_block(compose, "skeleton", "backend")
    backend = _service_block(compose, "backend", "frontend")
    consumers = _local_provider_consumers()

    for credential in ("OPENAI_API_KEY", "EMERGENT_LLM_KEY"):
        marker = credential + "=${"
        assert marker in skeleton
        if consumers:
            # Stage-5 cutover law: do not remove backend credentials while any
            # production backend module can still instantiate the local runtime.
            assert marker in backend, consumers
        else:
            assert marker not in backend

    # Non-provider product credentials remain backend-owned.  This prevents an
    # overbroad secret migration from changing product payment/auth ownership.
    assert "JWT_SECRET=${JWT_SECRET:" in backend
    assert "STRIPE_API_KEY=${STRIPE_API_KEY:-}" in backend


def test_engine_durable_state_is_bound_to_persistent_skeleton_volume() -> None:
    compose = _compose()
    skeleton = _service_block(compose, "skeleton", "backend")

    expected = {
        "SKL_ENGINE_EXECUTION_STATE_PATH=/app/data/engine_execution.sqlite",
        "SKL_ENGINE_SUBMISSION_STATE_PATH=/app/data/engine_submissions.sqlite",
        "SKL_ENGINE_TOOL_RECEIPT_PATH=/app/data/engine_tool_receipts.sqlite",
    }
    for marker in expected:
        assert marker in skeleton

    assert "skeleton_data:/app/data" in skeleton
    assert ":memory:" not in skeleton


def test_engine_service_auth_token_is_scoped_to_backend_and_engine() -> None:
    compose = _compose()
    skeleton = _service_block(compose, "skeleton", "backend")
    backend = _service_block(compose, "backend", "frontend")
    frontend = _service_block(compose, "frontend", "mongo")
    marker = (
        "SKL_ENGINE_SERVICE_TOKEN="
        "${SKL_ENGINE_SERVICE_TOKEN:?SKL_ENGINE_SERVICE_TOKEN must be set to a high-entropy value}"
    )

    assert marker in skeleton
    assert marker in backend
    assert skeleton.count(marker) == 1
    assert backend.count(marker) == 1
    assert "SKL_ENGINE_SERVICE_TOKEN=" not in frontend


def test_backend_waits_for_healthy_engine_before_serving_ai_ingress() -> None:
    compose = _compose()
    backend = _service_block(compose, "backend", "frontend")

    assert "SKELETON_INTERNAL_URL=${SKELETON_INTERNAL_URL:-http://skeleton:8001}" in backend
    assert "skeleton:\n        condition: service_healthy" in backend
    assert "mongo:\n        condition: service_healthy" in backend


def test_manifest_declares_engine_as_backend_runtime_dependency() -> None:
    manifest = _manifest()
    services = {
        item["name"]: item
        for item in manifest["services"]
        if isinstance(item, dict) and isinstance(item.get("name"), str)
    }

    assert services["backend"]["depends_on"] == ["mongo", "skeleton"]
    construction = manifest["construction"]
    assert construction["provider_activation_boundary"] == "skeleton/provider_runtime.py"
    assert construction["provider_runtime_boundary"] == "skeleton/provider_runtime.py"
    assert construction["provider_compatibility_boundary"] == "backend/core/ai_provider.py"
    assert construction["backend_engine_client"] == "backend/core/engine_client.py"
    assert construction["engine_execution_boundary"] == "skeleton/api/engine_routes.py"
    assert "backend/core/engine_client.py" in manifest["required_paths"]


def test_backend_compose_cannot_gain_undeclared_provider_credentials() -> None:
    compose = _compose()
    backend = _service_block(compose, "backend", "frontend")

    # OpenAI/Emergent remain transitional compatibility credentials until the
    # local ProviderRegistry activation inventory reaches zero. No additional
    # provider family may appear in the backend process during that migration.
    forbidden = (
        "ANTHROPIC_API_KEY",
        "GEMINI_API_KEY",
        "GOOGLE_API_KEY",
        "GROK_API_KEY",
        "XAI_API_KEY",
    )
    present = [name for name in forbidden if name + "=" in backend]
    assert present == []


def test_engine_principal_identity_is_explicit_and_matches_backend_client_default() -> None:
    compose = _compose()
    skeleton = _service_block(compose, "skeleton", "backend")

    assert (
        "SKL_ENGINE_SERVICE_PRINCIPAL="
        "${SKL_ENGINE_SERVICE_PRINCIPAL:-codedock-backend}"
    ) in skeleton

    client = (ROOT / "backend/core/engine_client.py").read_text(encoding="utf-8")
    assert 'service_principal: str = "codedock-backend"' in client
    assert '"x-zaibatsu-attester": self.config.service_principal' in client


def test_engine_transport_requires_authenticated_service_token() -> None:
    compose = _compose()
    skeleton = _service_block(compose, "skeleton", "backend")
    backend = _service_block(compose, "backend", "frontend")
    token_binding = (
        "SKL_ENGINE_SERVICE_TOKEN="
        "${SKL_ENGINE_SERVICE_TOKEN:?SKL_ENGINE_SERVICE_TOKEN must be set to a high-entropy value}"
    )

    assert token_binding in skeleton
    assert token_binding in backend

    client = (ROOT / "backend/core/engine_client.py").read_text(encoding="utf-8")
    routes = (ROOT / "skeleton/api/engine_routes.py").read_text(encoding="utf-8")
    assert '"authorization": "Bearer " + token' in client
    assert "SKL_ENGINE_SERVICE_TOKEN" in client
    assert "hmac.compare_digest" in routes
    assert "engine service authentication failed" in routes
