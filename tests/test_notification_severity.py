"""A critical alert is not a duplicate of an earlier info alert."""

from skeleton.intelligence.notification_center import NotificationCenter


def test_higher_severity_is_not_deduped_and_retry_respects_the_channel() -> None:
    center = NotificationCenter(dedupe_window_s=60)
    seen = []
    center.add_channel("app", lambda note: seen.append(note["severity"]) or True)
    center.notify("disk", "low", severity="info", source="host")
    result = center.notify("disk", "full", severity="critical", source="host")
    assert result.get("status") != "deduplicated"
    assert "deliveries" in result
    assert seen == ["info", "critical"]

    critical = []
    failing = NotificationCenter()
    failing.add_channel("bad", lambda note: False, min_severity="info")
    failing.add_channel("crit", lambda note: critical.append(note) or True, min_severity="critical")
    failing.notify("disk", "low", severity="info")
    assert failing.flush_retries() == 0
    assert critical == []
    assert failing.card()["retry_queue"] == 1
