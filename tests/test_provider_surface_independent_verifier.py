from __future__ import annotations

import json
from pathlib import Path

from scripts.verify_provider_surface_closure import verify_repository


def _write_contract(root: Path, *, isolation_path: str = "backend/facade.py") -> None:
    machine = root / "machine"
    machine.mkdir(parents=True, exist_ok=True)
    payload = {
        "provider_surfaces": [
            {
                "id": "engine-runtime",
                "family": "runtime_model",
                "role": "canonical",
                "owner": "skeleton/provider_runtime.py",
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
            },
            {
                "id": "backend-facade",
                "family": "runtime_model",
                "role": "facade",
                "owner": isolation_path,
                "credential_bearing": False,
                "receipt_required": True,
                "status": "compatibility",
                "surface_class": "noncredential_compatibility_facade",
                "credential_owner": False,
                "network_transport_owner": False,
                "sdk_client_owner": False,
                "discovery_edge_classes": [],
            },
        ],
        "provider_surface_convergence_blueprint": {
            "application_isolation_surfaces": [
                {
                    "path": isolation_path,
                    "role": "test facade",
                    "required_tokens": ["CANONICAL_DELEGATION"],
                    "forbidden_edge_classes": [
                        "credential",
                        "network_transport",
                        "sdk_client",
                    ],
                }
            ]
        },
    }
    (machine / "ai_app_construction.json").write_text(
        json.dumps(payload),
        encoding="utf-8",
    )


def _valid_repo(tmp_path: Path) -> Path:
    root = tmp_path
    (root / "skeleton").mkdir()
    (root / "backend").mkdir()
    (root / "skeleton" / "provider_runtime.py").write_text(
        "\n".join(
            [
                "import os",
                "import openai",
                'key = os.getenv("OPENAI_API_KEY")',
                'endpoint = "https://api.openai.com/v1/responses"',
                "",
            ]
        ),
        encoding="utf-8",
    )
    (root / "backend" / "facade.py").write_text(
        'CANONICAL_DELEGATION = "skeleton/provider_runtime.py"\n',
        encoding="utf-8",
    )
    mirror = root / "skeleton" / "ai" / "runtime"
    mirror.mkdir(parents=True, exist_ok=True)
    (mirror / "provider_runtime.py").write_bytes(
        (root / "skeleton" / "provider_runtime.py").read_bytes()
    )
    _write_contract(root)
    return root


def test_independent_verifier_accepts_declared_provider_ownership(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root = _valid_repo(tmp_path)
    monkeypatch.setenv("GITHUB_SHA", "abc123")

    receipt = verify_repository(root)

    assert receipt["valid"] is True
    assert receipt["errors"] == []
    assert receipt["head_sha"] == "abc123"
    assert receipt["scanned_python_files"] == 3
    assert receipt["declared_surface_digest"]
    edges = {
        row["path"]: set(row["edge_classes"])
        for row in receipt["discovered_provider_edges"]
    }
    assert edges["skeleton/provider_runtime.py"] == {
        "credential",
        "network_transport",
        "sdk_client",
    }


def test_independent_verifier_ignores_inert_provider_url_catalog(
    tmp_path: Path,
) -> None:
    root = _valid_repo(tmp_path)
    (root / "backend" / "catalog.py").write_text(
        'OPENAI_ENDPOINT = "https://api.openai.com/v1/responses"\n',
        encoding="utf-8",
    )

    receipt = verify_repository(root)

    assert receipt["valid"] is True
    assert not any(
        row["path"] == "backend/catalog.py"
        for row in receipt["discovered_provider_edges"]
    )


def test_independent_verifier_rejects_undeclared_vendor_sdk_edge(
    tmp_path: Path,
) -> None:
    root = _valid_repo(tmp_path)
    (root / "backend" / "rogue.py").write_text(
        "import anthropic\n",
        encoding="utf-8",
    )

    receipt = verify_repository(root)

    assert receipt["valid"] is False
    assert any(
        "undeclared provider-bearing production surface: backend/rogue.py"
        in error
        for error in receipt["errors"]
    )


def test_independent_verifier_rejects_application_credential_read(
    tmp_path: Path,
) -> None:
    root = _valid_repo(tmp_path)
    (root / "backend" / "facade.py").write_text(
        "\n".join(
            [
                "import os",
                'CANONICAL_DELEGATION = "skeleton/provider_runtime.py"',
                'key = os.getenv("OPENAI_API_KEY")',
                "",
            ]
        ),
        encoding="utf-8",
    )

    receipt = verify_repository(root)

    assert receipt["valid"] is False
    assert any(
        "backend/facade.py owns forbidden credential edges"
        in error
        for error in receipt["errors"]
    )


def test_independent_verifier_rejects_inconsistent_declared_edges(
    tmp_path: Path,
) -> None:
    root = _valid_repo(tmp_path)
    contract_path = root / "machine" / "ai_app_construction.json"
    payload = json.loads(contract_path.read_text(encoding="utf-8"))
    payload["provider_surfaces"][0]["discovery_edge_classes"] = []
    contract_path.write_text(json.dumps(payload), encoding="utf-8")

    receipt = verify_repository(root)

    assert receipt["valid"] is False
    assert any(
        "discovery_edge_classes does not match ownership flags" in error
        for error in receipt["errors"]
    )

def test_independent_verifier_accepts_byte_identical_ai_provider_mirror(
    tmp_path: Path,
) -> None:
    root = _valid_repo(tmp_path)
    mirror = root / "skeleton" / "ai" / "runtime"
    mirror.mkdir(parents=True, exist_ok=True)
    source = root / "skeleton" / "provider_runtime.py"
    (mirror / "provider_runtime.py").write_bytes(source.read_bytes())

    receipt = verify_repository(root)

    assert receipt["valid"] is True
    assert not any(
        "provider runtime AI mirror drifted" in error
        for error in receipt["errors"]
    )


def test_independent_verifier_rejects_drifted_ai_provider_mirror(
    tmp_path: Path,
) -> None:
    root = _valid_repo(tmp_path)
    mirror = root / "skeleton" / "ai" / "runtime"
    mirror.mkdir(parents=True, exist_ok=True)
    (mirror / "provider_runtime.py").write_text(
        "import openai\n# drifted mirror\n",
        encoding="utf-8",
    )

    receipt = verify_repository(root)

    assert receipt["valid"] is False
    assert any(
        "canonical provider runtime AI mirror drifted from source" in error
        for error in receipt["errors"]
    )

def test_independent_verifier_rejects_missing_canonical_provider_source(
    tmp_path: Path,
) -> None:
    root = _valid_repo(tmp_path)
    (root / "skeleton" / "provider_runtime.py").unlink()

    receipt = verify_repository(root)

    assert receipt["valid"] is False
    assert "canonical provider runtime source is missing" in receipt["errors"]
    assert any(
        "declared provider owner is missing: skeleton/provider_runtime.py"
        in error
        for error in receipt["errors"]
    )


def test_independent_verifier_rejects_missing_canonical_provider_mirror(
    tmp_path: Path,
) -> None:
    root = _valid_repo(tmp_path)
    (
        root
        / "skeleton"
        / "ai"
        / "runtime"
        / "provider_runtime.py"
    ).unlink()

    receipt = verify_repository(root)

    assert receipt["valid"] is False
    assert "canonical provider runtime AI mirror is missing" in receipt["errors"]


def test_independent_verifier_rejects_declared_edge_loss(
    tmp_path: Path,
) -> None:
    root = _valid_repo(tmp_path)
    source = root / "skeleton" / "provider_runtime.py"
    source.write_text(
        "\n".join(
            [
                "import os",
                'key = os.getenv("OPENAI_API_KEY")',
                "",
            ]
        ),
        encoding="utf-8",
    )
    mirror = root / "skeleton" / "ai" / "runtime" / "provider_runtime.py"
    mirror.write_bytes(source.read_bytes())

    receipt = verify_repository(root)

    assert receipt["valid"] is False
    assert any(
        "skeleton/provider_runtime.py lost declared provider edges: "
        in error
        and "network_transport" in error
        and "sdk_client" in error
        for error in receipt["errors"]
    )
