from __future__ import annotations

import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CHECKER = ROOT / "scripts/check_provider_bootstrap.py"


def _checker():
    spec = importlib.util.spec_from_file_location("provider_bootstrap_check", CHECKER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_current_provider_surface_inventory_is_fully_classified() -> None:
    module = _checker()
    contract = json.loads(
        (ROOT / "machine/ai_app_construction.json").read_text(encoding="utf-8")
    )
    surfaces = contract["provider_surfaces"]

    assert surfaces
    for surface in surfaces:
        assert surface["surface_class"] in module._ALLOWED_SURFACE_CLASSES
        assert isinstance(surface["credential_owner"], bool)
        assert isinstance(surface["network_transport_owner"], bool)
        assert isinstance(surface["sdk_client_owner"], bool)
        assert sorted(surface["discovery_edge_classes"]) == sorted(
            edge
            for edge, enabled in (
                ("credential", surface["credential_owner"]),
                ("network_transport", surface["network_transport_owner"]),
                ("sdk_client", surface["sdk_client_owner"]),
            )
            if enabled
        )

    assert module.validate_provider_bootstrap(ROOT) == []


def test_discovery_classifies_sdk_credential_and_raw_network_edges(
    tmp_path: Path,
) -> None:
    module = _checker()
    root = tmp_path / "skeleton"
    root.mkdir()
    path = root / "model_provider.py"
    path.write_text(
        "\n".join(
            (
                "import urllib.request",
                "from openai import AsyncOpenAI",
                'OPENAI_API_KEY = "marker"',
                'BASE = "https://api.openai.com/v1"',
            )
        ),
        encoding="utf-8",
    )

    discovered = module.discover_provider_surfaces(tmp_path)
    signals = discovered["skeleton/model_provider.py"]

    assert signals["edge_classes"] == [
        "credential",
        "network_transport",
        "sdk_client",
    ]
    assert signals["sdk_imports"] == ["openai"]
    assert signals["network_imports"] == ["urllib.request"]
    assert signals["provider_urls"] == ["api.openai.com"]


def test_generic_network_without_provider_context_is_not_misclassified(
    tmp_path: Path,
) -> None:
    module = _checker()
    root = tmp_path / "skeleton" / "utilities"
    root.mkdir(parents=True)
    (root / "download.py").write_text(
        "import urllib.request\n",
        encoding="utf-8",
    )

    assert module.discover_provider_surfaces(tmp_path) == {}


def test_network_provider_path_is_classified_without_literal_credential(
    tmp_path: Path,
) -> None:
    module = _checker()
    root = tmp_path / "backend" / "services"
    root.mkdir(parents=True)
    (root / "model_gateway.py").write_text(
        "import httpx\n",
        encoding="utf-8",
    )

    signals = module.discover_provider_surfaces(tmp_path)[
        "backend/services/model_gateway.py"
    ]
    assert signals["edge_classes"] == ["network_transport"]
    assert signals["network_imports"] == ["httpx"]


def test_application_provider_surfaces_are_delegation_only() -> None:
    module = _checker()
    contract = json.loads(
        (ROOT / "machine/ai_app_construction.json").read_text(encoding="utf-8")
    )
    surfaces = contract["provider_surface_convergence_blueprint"][
        "application_isolation_surfaces"
    ]

    assert surfaces
    for item in surfaces:
        path = ROOT / item["path"]
        source = path.read_text(encoding="utf-8")
        for token in item["required_tokens"]:
            assert token in source

        signals = module._provider_surface_signals(path, source)
        edges = set()
        if signals["credential_markers"]:
            edges.add("credential")
        if signals["sdk_imports"]:
            edges.add("sdk_client")
        if module._looks_like_provider_network_surface(path, source, signals):
            edges.add("network_transport")

        assert not edges.intersection(item["forbidden_edge_classes"])


def test_provider_surface_evidence_receipt_is_current_head_and_secret_free() -> None:
    module = _checker()
    evidence = module.build_provider_surface_evidence(
        ROOT,
        head_sha="0123456789abcdef",
        errors=[],
    )

    assert evidence["schema_version"] == 1
    assert evidence["head_sha"] == "0123456789abcdef"
    assert evidence["valid"] is True
    assert evidence["validation_errors"] == []

    declared = {item["id"]: item for item in evidence["declared_surfaces"]}
    assert declared["engine-runtime"]["credential_owner"] is True
    assert declared["engine-runtime"]["network_transport_owner"] is True
    assert declared["engine-runtime"]["sdk_client_owner"] is True
    assert "skeleton/provider_runtime.py" in evidence["discovered_surfaces"]
    assert "skeleton/automation/free_model.py" in evidence["discovered_surfaces"]

    rendered = json.dumps(evidence, sort_keys=True)
    assert "Bearer " not in rendered
    assert "api_key_value" not in rendered


def test_provider_surface_evidence_records_validation_failure() -> None:
    module = _checker()
    evidence = module.build_provider_surface_evidence(
        ROOT,
        head_sha="bad-head",
        errors=["synthetic failure"],
    )

    assert evidence["valid"] is False
    assert evidence["validation_errors"] == ["synthetic failure"]



def test_ai_credential_read_is_classified_without_provider_filename_or_sdk(
    tmp_path: Path,
) -> None:
    module = _checker()
    root = tmp_path / "backend" / "services"
    root.mkdir(parents=True)
    (root / "tool_registry.py").write_text(
        "import os\nkey = os.environ.get('EMERGENT_LLM_KEY', '')\n",
        encoding="utf-8",
    )

    discovered = module.discover_provider_surfaces(tmp_path)

    assert discovered["backend/services/tool_registry.py"]["edge_classes"] == [
        "credential"
    ]
    assert discovered["backend/services/tool_registry.py"][
        "credential_markers"
    ] == ["EMERGENT_LLM_KEY"]
