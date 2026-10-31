"""App closed tests."""
from skeleton.gameforge.conductor_e2e_closed import GameForgeE2EClosed
from skeleton.jeeves.pipeline_live_closed import JeevesPipelineClosed
def test_e2e_closed():
    c = GameForgeE2EClosed()
    assert len(c.full_run()) == 7
def test_pipeline_closed():
    p = JeevesPipelineClosed()
    assert p.plan_build("spec")
    assert p.doctor()
