from __future__ import annotations

import json
from pathlib import Path
import shutil

from scripts.check_provider_surface_closure import (
    build_closure_receipt,
    validate_provider_surface_closure,
)


ROOT = Path(__file__).resolve().parents[1]


def _copy_minimal_repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    for relative in (
        "machine/ai_app_construction.json",
        "docker-compose.yml",
        "skeleton/provider_runtime.py",
        "skeleton/jeeves/providers.py",
        "backend/core/ai_provider.py",
        "backend/routes/image_generation.py",
        "backend/core/expressive_tts.py",
    ):
        source = ROOT / relative
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    return root


def test_current_repository_provider_surface_closure_is_valid() -> None:
    errors = validate_provider_surface_closure(ROOT)
    assert errors == []

    receipt = build_closure_receipt(ROOT, head_sha="test-head")
    assert receipt["valid"] is True
    assert receipt["head_sha"] == "test-head"
    assert receipt["gap"] == "gap-provider-surface-convergence"
    assert (
        receipt["canonical_runtime_owner"]
        == "skeleton/provider_runtime.py"
    )


def test_duplicate_runtime_model_credential_owner_is_rejected(tmp_path) -> None:
    root = _copy_minimal_repo(tmp_path)
    contract_path = root / "machine/ai_app_construction.json"
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    contract["provider_surfaces"].append(
        {
            "id": "shadow-runtime",
            "family": "runtime_model",
            "role": "forbidden duplicate runtime",
            "owner": "backend/shadow_runtime.py",
            "credential_bearing": True,
            "receipt_required": True,
            "status": "canonical",
            "surface_class": "canonical_runtime",
            "credential_owner": True,
            "network_transport_owner": True,
            "sdk_client_owner": True,
            "discovery_edge_classes": [
                "credential",
                "network_transport",
                "sdk_client",
            ],
        }
    )
    contract_path.write_text(
        json.dumps(contract, indent=2) + "\n",
        encoding="utf-8",
    )

    errors = validate_provider_surface_closure(root)

    assert any(
        "runtime model credential_owner must be owned only" in error
        for error in errors
    )
    assert any(
        "runtime model network_transport_owner must be owned only" in error
        for error in errors
    )
    assert any(
        "runtime model sdk_client_owner must be owned only" in error
        for error in errors
    )


def test_backend_runtime_provider_credential_reintroduction_is_rejected(
    tmp_path,
) -> None:
    root = _copy_minimal_repo(tmp_path)
    compose_path = root / "docker-compose.yml"
    compose = compose_path.read_text(encoding="utf-8")
    backend_start = compose.index("\n  backend:\n")
    frontend_start = compose.index("\n  frontend:\n", backend_start)
    backend = compose[backend_start:frontend_start]
    backend = backend.replace(
        "      - DEBUG=${DEBUG:-false}\n",
        "      - DEBUG=${DEBUG:-false}\n"
        "      - OPENAI_API_KEY=${OPENAI_API_KEY:-}\n",
    )
    compose_path.write_text(
        compose[:backend_start] + backend + compose[frontend_start:],
        encoding="utf-8",
    )

    errors = validate_provider_surface_closure(root)

    assert (
        "backend process still receives runtime provider credential: "
        "OPENAI_API_KEY"
    ) in errors


def test_jeeves_credential_read_is_rejected(tmp_path) -> None:
    root = _copy_minimal_repo(tmp_path)
    jeeves = root / "skeleton/jeeves/providers.py"
    source = jeeves.read_text(encoding="utf-8")
    jeeves.write_text(
        "import os\n"
        "_BAD = os.getenv('OPENAI_API_KEY')\n"
        + source,
        encoding="utf-8",
    )

    errors = validate_provider_surface_closure(root)

    assert "Jeeves provider facade reads model credentials" in errors


def test_backend_local_registry_activation_is_rejected(tmp_path) -> None:
    root = _copy_minimal_repo(tmp_path)
    path = root / "backend/routes/shadow_provider.py"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "from skeleton.provider_runtime import ProviderRegistry\n"
        "REGISTRY = ProviderRegistry.from_env()\n",
        encoding="utf-8",
    )

    errors = validate_provider_surface_closure(root)

    assert any(
        error.startswith(
            "backend local ProviderRegistry.from_env activators remain:"
        )
        and "backend/routes/shadow_provider.py" in error
        for error in errors
    )
