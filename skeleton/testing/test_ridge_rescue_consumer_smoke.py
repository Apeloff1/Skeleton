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


def test_source_and_portable_processes_reach_identical_earned_state():
    """A packaged consumer game must preserve canonical gameplay semantics."""
    from skeleton.game.gameplay.ridge_rescue.consumer_smoke import run_portable_smoke

    source = run_smoke()
    portable = run_portable_smoke()
    for field in (
        "earned_head", "actions", "quit_after_actions", "chapters",
        "portable_export_verified", "portable_restore_audited",
        "partial_restore_resume_verified", "full_history_backup_restored",
        "restore_overwrite_rejected", "tampered_restore_rejected",
        "invalid_mutation_rejected",
    ):
        assert portable[field] == source[field], field
    assert portable["portable_zipapp_verified"]
    assert portable["source_checkout_dependency"] is False
    assert portable["archive_files"] > 0
    assert portable["archive_sha256"]
    assert not portable["windows_device_certified"]
    assert not portable["release_certified"]
