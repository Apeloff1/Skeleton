from scripts.check_p3_deferred_batch_01 import validate


def test_p3_deferred_batch_01_is_consistent_with_frozen_source_queue() -> None:
    result = validate()
    assert result == {
        "status": "valid",
        "batch_id": "P3-DEFERRED-BATCH-01",
        "selected_volume_count": 11,
        "projected_remaining_volume_count": 167,
        "task_count": 4,
        "contract_count": 33,
    }
