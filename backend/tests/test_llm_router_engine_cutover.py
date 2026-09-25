from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SOURCE = (ROOT / "backend/routes/llm_router.py").read_text(encoding="utf-8")


def test_llm_router_has_no_local_provider_activation_or_transport() -> None:
    assert "ProviderRegistry" not in SOURCE
    assert "ProviderRequest" not in SOURCE
    assert "core.ai_provider" not in SOURCE
    assert "AI_REGISTRY" not in SOURCE

    assert "EngineClient" in SOURCE
    assert "EngineTextRequest" in SOURCE
    assert "execute_engine_text" in SOURCE


def test_llm_router_delegates_provider_and_model_ownership_to_engine() -> None:
    assert 'verification_profile="assistant_proposal"' in SOURCE
    assert '"provider": "skeleton-engine"' in SOURCE
    assert '"model": "engine-routed"' in SOURCE
    assert '"model_pinning_unavailable"' in SOURCE
    assert "provider/model selection and failover are engine-owned" in SOURCE.lower()


def test_llm_router_failure_is_engine_bounded_without_provider_fallback() -> None:
    assert "except (EngineTextError, TimeoutError, asyncio.TimeoutError)" in SOURCE
    assert '"error_code": "engine_unavailable"' in SOURCE
    assert "adapter.generate(" not in SOURCE
