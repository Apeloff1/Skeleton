from pathlib import Path
from scripts.check_p3_learning_closure import validate
ROOT=Path(__file__).resolve().parents[1]
def test_current_t2_extension_state_is_valid():
    r=validate(ROOT)
    assert r["status"]=="active"
    assert r["task_count"]==6
    assert r["scheduled_volume_count"]==32
    assert r["queued_volume_count"]==165
