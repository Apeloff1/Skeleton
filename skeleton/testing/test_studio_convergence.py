import pytest
from skeleton.automation.studio_convergence import evaluate

def test_complete(): assert evaluate(queued=0,blocked=0,active_lanes=0,quarantined_lanes=0).status=="complete"
def test_stalled(): assert evaluate(queued=2,blocked=0,active_lanes=0,quarantined_lanes=1).status=="stalled"
def test_degraded(): assert evaluate(queued=2,blocked=1,active_lanes=1,quarantined_lanes=0).status=="degraded"
def test_progressing(): assert evaluate(queued=2,blocked=0,active_lanes=1,quarantined_lanes=0).status=="progressing"
def test_negative_rejected():
    with pytest.raises(ValueError): evaluate(queued=-1,blocked=0,active_lanes=0,quarantined_lanes=0)
