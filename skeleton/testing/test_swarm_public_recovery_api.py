from skeleton.agents import (
    Checkpoint,
    CheckpointStore,
    RecoveryStatus,
    SwarmRecoveryManager,
    TenantCheckpointStore,
    TenantMetadataCheckpoint,
    validate_restore_state,
)
from skeleton.api.server import create_app


def test_public_recovery_exports_are_importable() -> None:
    assert Checkpoint.__name__ == "Checkpoint"
    assert CheckpointStore.__name__ == "CheckpointStore"
    assert RecoveryStatus.__name__ == "RecoveryStatus"
    assert SwarmRecoveryManager.__name__ == "SwarmRecoveryManager"
    assert TenantCheckpointStore.__name__ == "TenantCheckpointStore"
    assert TenantMetadataCheckpoint.__name__ == "TenantMetadataCheckpoint"
    assert callable(validate_restore_state)


def test_operator_mounts_recovery_and_retention_routes() -> None:
    app = create_app()
    paths = {route.path for route in app.routes}
    assert "/api/v1/swarm/operator/checkpoint" in paths
    assert "/api/v1/swarm/operator/restore-latest" in paths
    assert "/api/v1/swarm/operator/recovery" in paths
    assert "/api/v1/swarm/operator/prune-terminal" in paths
