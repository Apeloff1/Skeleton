from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.ai_provider import OpenAIProviderAdapter, ProviderRegistry, ProviderUnavailableError
from core.provider_architecture import (
    ProviderArchitectureError,
    ProviderArchitectureReceipt,
    load_provider_architecture,
)


def _write_contract_root(root: Path, *, tag: str = "arch-map/test") -> None:
    (root / "machine").mkdir(parents=True)
    (root / "docs").mkdir(parents=True)
    architecture = {
        "status": "active",
        "architecture_tag": tag,
    }
    construction = {
        "status": "active",
        "construction_version": "test-1",
        "architecture_tag": tag,
        "human_manual": "docs/AI_APP_CONSTRUCTION_MANUAL.md",
        "provider_bootstrap": {
            "mandatory": True,
            "mode": "fail_closed",
            "must_read": [
                "machine/manifest.json",
                "machine/architecture.json",
                "machine/ai_app_construction.json",
                "docs/AI_APP_CONSTRUCTION_MANUAL.md",
            ],
        },
        "runtime_model_providers": [
            {
                "id": "openai",
                "architecture_read_required": True,
                "construction_manual_read_required": True,
                "activation_receipt_required": True,
            }
        ],
    }
    (root / "machine/manifest.json").write_text('{"schema_version": 1}\n', encoding="utf-8")
    (root / "machine/architecture.json").write_text(
        json.dumps(architecture), encoding="utf-8"
    )
    (root / "machine/ai_app_construction.json").write_text(
        json.dumps(construction), encoding="utf-8"
    )
    (root / "docs/AI_APP_CONSTRUCTION_MANUAL.md").write_text(
        "# Mandatory manual\n", encoding="utf-8"
    )


def test_real_openai_provider_reads_active_repository_contract() -> None:
    receipt = load_provider_architecture("openai")

    assert receipt.provider_id == "openai"
    assert receipt.architecture_tag == "arch-map/v3.6"
    assert receipt.construction_version == "3.6.0"
    assert len(receipt.contract_digest) == 64
    assert "docs/AI_APP_CONSTRUCTION_MANUAL.md" in receipt.required_documents


def test_loader_rejects_undeclared_provider(tmp_path: Path) -> None:
    _write_contract_root(tmp_path)

    with pytest.raises(ProviderArchitectureError, match="not declared"):
        load_provider_architecture("unknown", root=tmp_path)


def test_loader_rejects_architecture_tag_drift(tmp_path: Path) -> None:
    _write_contract_root(tmp_path, tag="arch-map/a")
    construction_path = tmp_path / "machine/ai_app_construction.json"
    construction = json.loads(construction_path.read_text(encoding="utf-8"))
    construction["architecture_tag"] = "arch-map/b"
    construction_path.write_text(json.dumps(construction), encoding="utf-8")

    with pytest.raises(ProviderArchitectureError, match="does not match"):
        load_provider_architecture("openai", root=tmp_path)


def test_loader_rejects_missing_mandatory_manual(tmp_path: Path) -> None:
    _write_contract_root(tmp_path)
    (tmp_path / "docs/AI_APP_CONSTRUCTION_MANUAL.md").unlink()

    with pytest.raises(ProviderArchitectureError, match="not materialized|unavailable"):
        load_provider_architecture("openai", root=tmp_path)


class _Adapter:
    provider_id = "openai"
    model = "test"
    available = True

    def status(self):
        return {"id": self.provider_id, "model": self.model, "available": True}

    async def generate(self, request):
        return request


def test_registry_requires_architecture_receipt_before_activation() -> None:
    calls: list[str] = []

    def loader(provider_id: str) -> ProviderArchitectureReceipt:
        calls.append(provider_id)
        return ProviderArchitectureReceipt(
            provider_id=provider_id,
            architecture_tag="arch-map/test",
            construction_version="test",
            contract_digest="0" * 64,
            manual_path="docs/AI_APP_CONSTRUCTION_MANUAL.md",
            required_documents=("machine/architecture.json",),
        )

    registry = ProviderRegistry([_Adapter()], active="openai", architecture_loader=loader)

    assert registry.require_active().provider_id == "openai"
    assert calls == ["openai"]
    assert registry.require_active().provider_id == "openai"
    assert calls == ["openai"]
    assert registry.architecture_receipt()["architecture_tag"] == "arch-map/test"


def test_registry_fails_closed_when_architecture_read_fails() -> None:
    def loader(_provider_id: str) -> ProviderArchitectureReceipt:
        raise ProviderArchitectureError("contract unavailable")

    registry = ProviderRegistry([_Adapter()], active="openai", architecture_loader=loader)

    assert registry.available is False
    with pytest.raises(ProviderUnavailableError, match="architecture acknowledgement failed"):
        registry.require_active()


def test_direct_openai_adapter_cannot_bypass_architecture(monkeypatch) -> None:
    class _Client:
        class _Responses:
            async def create(self, **_kwargs):
                raise AssertionError("provider I/O must not occur")

        responses = _Responses()

    def deny(_provider_id: str):
        raise ProviderArchitectureError("missing contract")

    monkeypatch.setattr("skeleton.provider_runtime.load_provider_architecture", deny)
    adapter = OpenAIProviderAdapter(
        api_key="test-key",
        model="test-model",
        client=_Client(),
    )

    assert adapter.available is False
    with pytest.raises(ProviderUnavailableError, match="architecture acknowledgement failed"):
        adapter._get_client()


def test_backend_provider_facade_reexports_engine_runtime() -> None:
    from skeleton.provider_runtime import (
        OpenAIProviderAdapter as EngineOpenAIProviderAdapter,
        ProviderRegistry as EngineProviderRegistry,
        ProviderRequest as EngineProviderRequest,
    )
    from core.ai_provider import (
        OpenAIProviderAdapter as BackendOpenAIProviderAdapter,
        ProviderRegistry as BackendProviderRegistry,
        ProviderRequest as BackendProviderRequest,
    )

    assert BackendOpenAIProviderAdapter is EngineOpenAIProviderAdapter
    assert BackendProviderRegistry is EngineProviderRegistry
    assert BackendProviderRequest is EngineProviderRequest
