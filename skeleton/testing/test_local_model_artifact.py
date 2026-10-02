from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from skeleton.ai.runtime.inference import (
    LocalModelArtifactError,
    ReferenceNGramModel,
    load_local_model_artifact,
    local_model_adapter_from_env,
)
from skeleton.provider_runtime import ProviderRegistry, ProviderUnavailableError


def _write_reference_artifact(tmp_path: Path) -> tuple[Path, ReferenceNGramModel, bytes]:
    model = ReferenceNGramModel.train(
        (
            "local models answer without provider network access",
            "canonical product context remains data not authority",
        ),
        order=2,
        model_id="artifact-bootstrap-reference",
    )
    raw = json.dumps(
        model.to_dict(),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    path = tmp_path / "local-model.json"
    path.write_bytes(raw)
    return path, model, raw


def _configure_local(monkeypatch, path: Path) -> None:
    monkeypatch.setenv("AI_PROVIDER", "local")
    monkeypatch.setenv("AI_LOCAL_MODEL_PATH", str(path))
    monkeypatch.setenv("AI_ARCHITECTURE_ROOT", str(Path(__file__).resolve().parents[2]))
    monkeypatch.delenv("AI_SECONDARY_API_KEY", raising=False)
    monkeypatch.delenv("AI_SECONDARY_BASE_URL", raising=False)
    monkeypatch.delenv("AI_SECONDARY_MODEL", raising=False)
    monkeypatch.delenv("AI_VERIFICATION_MODEL", raising=False)


def test_reference_artifact_loads_with_exact_content_and_model_identity(tmp_path) -> None:
    path, model, raw = _write_reference_artifact(tmp_path)
    loaded = load_local_model_artifact(path)

    assert loaded.receipt.schema == "reference_ngram"
    assert loaded.receipt.artifact_sha256 == hashlib.sha256(raw).hexdigest()
    assert loaded.receipt.artifact_bytes == len(raw)
    assert loaded.receipt.model_id == model.model_id
    assert loaded.receipt.model_digest == model.model_digest
    assert loaded.receipt.reference == (
        "local-model-artifact:" + hashlib.sha256(raw).hexdigest()
    )
    assert loaded.model.model_digest == model.model_digest


def test_env_bootstrap_attaches_immutable_activation_receipt(
    tmp_path,
    monkeypatch,
) -> None:
    path, model, raw = _write_reference_artifact(tmp_path)
    _configure_local(monkeypatch, path)
    monkeypatch.setenv("AI_LOCAL_MODEL_CACHE_SIZE", "7")
    monkeypatch.setenv("AI_LOCAL_MODEL_SEED", "42")

    adapter = local_model_adapter_from_env()

    assert adapter.provider_id == "local"
    assert adapter.model == model.model_id
    assert adapter.default_seed == 42
    assert adapter.engine.cache_size == 7
    assert adapter.artifact_receipt.artifact_sha256 == hashlib.sha256(raw).hexdigest()
    assert adapter.artifact_receipt.model_digest == model.model_digest


def test_provider_registry_local_mode_has_no_external_fallback_or_verifier(
    tmp_path,
    monkeypatch,
) -> None:
    path, model, _raw = _write_reference_artifact(tmp_path)
    _configure_local(monkeypatch, path)
    # A placeholder primary key may exist in a generic environment. Local mode
    # must not instantiate or require the external provider adapter.
    monkeypatch.setenv("OPENAI_API_KEY", "unused-placeholder")

    registry = ProviderRegistry.from_env()
    adapter = registry.require_active()
    architecture = registry.architecture_receipt()

    assert registry.active_id == "local"
    assert adapter.provider_id == "local"
    assert adapter.model == model.model_id
    assert registry.available is True
    assert registry.redundancy_status()["enabled"] is False
    assert registry.verification_adapter_for(adapter) is None
    assert architecture["provider_id"] == "local"
    assert architecture["provider_family"] == "runtime_model"


@pytest.mark.parametrize(
    ("name", "value"),
    (
        ("AI_SECONDARY_API_KEY", "placeholder"),
        ("AI_SECONDARY_BASE_URL", "https://secondary.invalid/v1"),
        ("AI_SECONDARY_MODEL", "secondary-model"),
        ("AI_VERIFICATION_MODEL", "external-verifier"),
    ),
)
def test_local_mode_rejects_external_provider_configuration(
    tmp_path,
    monkeypatch,
    name: str,
    value: str,
) -> None:
    path, _model, _raw = _write_reference_artifact(tmp_path)
    _configure_local(monkeypatch, path)
    monkeypatch.setenv(name, value)

    with pytest.raises(ProviderUnavailableError):
        ProviderRegistry.from_env()


@pytest.mark.parametrize(
    "raw",
    (
        b'{"kind":"reference_ngram","kind":"reference_ngram"}',
        b'{"kind":NaN}',
        b'["not-an-object"]',
        b'not-json',
    ),
)
def test_artifact_parser_fails_closed_on_ambiguous_or_invalid_json(
    tmp_path,
    raw: bytes,
) -> None:
    path = tmp_path / "invalid-model.json"
    path.write_bytes(raw)

    with pytest.raises(LocalModelArtifactError):
        load_local_model_artifact(path)


def test_artifact_model_digest_drift_is_rejected(tmp_path) -> None:
    path, model, _raw = _write_reference_artifact(tmp_path)
    payload = model.to_dict()
    payload["model_digest"] = "0" * 64
    path.write_text(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ),
        encoding="utf-8",
    )

    with pytest.raises(LocalModelArtifactError, match="invalid"):
        load_local_model_artifact(path)


@pytest.mark.parametrize(
    ("name", "value"),
    (
        ("AI_LOCAL_MODEL_CACHE_SIZE", "-1"),
        ("AI_LOCAL_MODEL_CACHE_SIZE", "16385"),
        ("AI_LOCAL_MODEL_SEED", str(2**63)),
        ("AI_LOCAL_MODEL_SEED", "not-an-int"),
    ),
)
def test_local_bootstrap_bounds_operator_numeric_configuration(
    tmp_path,
    monkeypatch,
    name: str,
    value: str,
) -> None:
    path, _model, _raw = _write_reference_artifact(tmp_path)
    _configure_local(monkeypatch, path)
    monkeypatch.setenv(name, value)

    with pytest.raises(LocalModelArtifactError):
        local_model_adapter_from_env()
