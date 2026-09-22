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
