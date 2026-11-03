"""Host process smoke contract; actual Windows hardware remains a separate hold."""
from skeleton.game.gameplay.ridge_rescue.consumer_smoke import run_smoke


def test_consumer_process_smoke_full_campaign():
    report = run_smoke()
    assert report["result"] == "passed-on-current-host"
    assert report["actions"] > 20
    assert report["chapters"] == 2
    assert report["real_processes"]
    assert report["portable_export_verified"]
    assert not report["windows_device_certified"]
    assert not report["release_certified"]
