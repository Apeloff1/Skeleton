from __future__ import annotations

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


def test_runtime_provider_credentials_exist_only_in_engine_process() -> None:
    compose = _compose()
    skeleton = _service_block(compose, "skeleton", "backend")
    backend = _service_block(compose, "backend", "frontend")

    for credential in ("OPENAI_API_KEY", "EMERGENT_LLM_KEY"):
        marker = credential + "=${"
        assert marker in skeleton
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


def test_backend_compose_cannot_regain_model_provider_credentials() -> None:
    compose = _compose()
    backend = _service_block(compose, "backend", "frontend")

    forbidden = (
        "OPENAI_API_KEY",
        "EMERGENT_LLM_KEY",
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
