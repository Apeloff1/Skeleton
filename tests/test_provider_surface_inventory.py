from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_provider_bootstrap.py"


def _module():
    spec = importlib.util.spec_from_file_location("check_provider_bootstrap", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write(root: Path, relative: str, source: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")


def test_inventory_classifies_credential_network_owner(tmp_path: Path) -> None:
    module = _module()
    _write(
        tmp_path,
        "skeleton/provider_runtime.py",
        "import httpx\nOPENAI_API_KEY = 'marker-only'\n",
    )

    inventory = module.discover_provider_surface_inventory(tmp_path)

    assert inventory == [
        {
            "path": "skeleton/provider_runtime.py",
            "classification": "credential_network_owner",
            "credential_markers": ["OPENAI_API_KEY"],
            "provider_sdk_imports": [],
            "network_client_imports": ["httpx"],
            "provider_endpoints": [],
        }
    ]


def test_inventory_detects_raw_provider_endpoint(tmp_path: Path) -> None:
    module = _module()
    _write(
        tmp_path,
        "backend/core/model_edge.py",
        "import httpx\nURL = 'https://api.openai.com/v1/responses'\n",
    )

    inventory = module.discover_provider_surface_inventory(tmp_path)

    assert inventory[0]["path"] == "backend/core/model_edge.py"
    assert inventory[0]["classification"] == "raw_provider_network"
    assert inventory[0]["network_client_imports"] == ["httpx"]
    assert inventory[0]["provider_endpoints"] == ["api.openai.com"]


def test_inventory_is_deterministic_and_ignores_test_trees(tmp_path: Path) -> None:
    module = _module()
    _write(
        tmp_path,
        "skeleton/z_provider.py",
        "OPENAI_API_KEY = 'marker-only'\n",
    )
    _write(
        tmp_path,
        "backend/a_model.py",
        "from openai import OpenAI\n",
    )
    _write(
        tmp_path,
        "backend/tests/test_provider.py",
        "import httpx\nOPENAI_API_KEY = 'test-only'\n",
    )
    _write(
        tmp_path,
        "skeleton/testing/provider_fixture.py",
        "import requests\nANTHROPIC_API_KEY = 'test-only'\n",
    )

    first = module.discover_provider_surface_inventory(tmp_path)
    second = module.discover_provider_surface_inventory(tmp_path)

    assert first == second
    assert [item["path"] for item in first] == [
        "backend/a_model.py",
        "skeleton/z_provider.py",
    ]
    assert all("/tests/" not in item["path"] for item in first)
    assert all("/testing/" not in item["path"] for item in first)
