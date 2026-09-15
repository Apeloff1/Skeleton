from skeleton.frontier.gameforge_health_score import HealthScore

def test_health_score_is_bounded_window():
 h=HealthScore(2); h.record(False); h.record(True); h.record(True); assert h.value==1.0 and h.healthy
