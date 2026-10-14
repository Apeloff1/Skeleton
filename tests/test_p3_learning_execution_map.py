from pathlib import Path
from scripts.check_p3_learning_execution_map import validate
ROOT=Path(__file__).resolve().parents[1]
def test_current_t2_authority_is_valid():
    r=validate(ROOT)
    assert r["source_volume_count"]==197
    assert r["scheduled_volume_count"]==32
    assert r["queued_volume_count"]==165
    assert r["task_count"]==6
    # The authoritative P3-T2 backlog now marks all six tasks closed.
    assert r["in_progress_count"] == 0
    assert r["landed_unpromoted_count"] == 0
    assert r["ready_count"] == 0
    assert r["blocked_count"] == 0
