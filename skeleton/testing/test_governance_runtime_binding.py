from __future__ import annotations

from pathlib import Path

from skeleton.api.server import ServerState


def test_server_state_binds_one_durable_governance_owner(
    tmp_path,
    monkeypatch,
) -> None:
    path = tmp_path / "governance-lifecycle.sqlite3"
    monkeypatch.setenv("SKL_GOVERNANCE_LIFECYCLE_PATH", str(path))

    first = ServerState()
    registry = first.bind_governance_registry()
    assert first.bind_governance_registry() is registry

    registry.register_canonical_write(
        "memory",
        record_id="memory-runtime-binding",
        tenant_id="tenant-a",
        source_ref="memory://assistant/memory-runtime-binding",
        data_class="confidential",
        purposes=("model-inference", "retrieval-synthesis"),
        created_at=10.0,
        retention_until=20.0,
    )
    first.close_governance_registry()

    restarted = ServerState()
    restored = restarted.bind_governance_registry()
    inventory = restored.export_inventory("tenant-a")

    assert inventory["count"] == 1
    assert inventory["records"][0]["record_id"] == "memory-runtime-binding"
    assert inventory["records"][0]["data_class"] == "confidential"
    assert inventory["records"][0]["retention_until"] == 20.0
    restarted.close_governance_registry()


def test_compose_binds_governance_lifecycle_to_skeleton_durable_volume() -> None:
    root = Path(__file__).resolve().parents[2]
    compose = (root / "docker-compose.yml").read_text(encoding="utf-8")

    assert (
        "SKL_GOVERNANCE_LIFECYCLE_PATH=/app/data/governance_lifecycle.sqlite"
        in compose
    )
    assert "skeleton_data:/app/data" in compose
