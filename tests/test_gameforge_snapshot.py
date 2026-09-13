from skeleton.frontier.gameforge_snapshot import RuntimeSnapshot

def test_snapshot_reports_saturation():
 s=RuntimeSnapshot("ready",True,2,2,2); assert s.saturated()
