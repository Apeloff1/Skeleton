"""Final close tests."""
from skeleton.gameforge.conductor_final import GameForgeConductorFinal
from skeleton.hive.chronicle_final import HiveChronicleFinal
def test_conductor_final():
    c = GameForgeConductorFinal()
    receipts = c.full_run()
    assert len(receipts) == 7
def test_chronicle_final():
    h = HiveChronicleFinal()
    h.gossip_root("a" * 64)
    assert h.tournament()
