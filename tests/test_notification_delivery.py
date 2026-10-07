"""A failed alert is not treated as delivered, and a retry does not fan out again."""

from skeleton.intelligence.notification_center import NotificationCenter


def test_a_failed_send_is_not_a_duplicate() -> None:
    center = NotificationCenter(dedupe_window_s=60)
    calls = {"n": 0}

    def fail_once(note):
        calls["n"] += 1
        return calls["n"] > 1

    center.add_channel("app", fail_once)
    first = center.notify("disk", "low", source="host")
    assert first["deliveries"]["app"] == "failed"
    second = center.notify("disk", "low", source="host")
    assert second.get("status") != "deduplicated"
    assert second["deliveries"]["app"] == "delivered"


def test_retry_does_not_resend_to_a_channel_that_accepted() -> None:
    accepted = []
    failed = {"open": True}

    def good(note):
        accepted.append(note["title"])
        return True

    def bad(note):
        return not failed["open"]

    center = NotificationCenter()
    center.add_channel("good", good)
    center.add_channel("bad", bad)
    center.notify("disk", "low", source="host")
    assert accepted == ["disk"]
    assert center.card()["retry_queue"] == 1
    failed["open"] = False
    assert center.flush_retries() == 1
    assert accepted == ["disk"]
    assert center.card()["retry_queue"] == 0


def test_existing_delivery_dedupe_and_severity_contracts() -> None:
    center = NotificationCenter()
    received = []
    center.add_channel("app", lambda note: received.append(note) or True)
    center.notify("Alert", "something", severity="warning")
    assert len(received) == 1

    filtered = NotificationCenter()
    seen = []
    filtered.add_channel("crit-only", lambda note: seen.append(note) or True, min_severity="critical")
    filtered.notify("Low", "info event", severity="info")
    assert seen == []

    deduped = NotificationCenter(dedupe_window_s=60)
    deduped.add_channel("app", lambda note: True)
    deduped.notify("Same", "body", source="s")
    assert deduped.notify("Same", "body", source="s")["status"] == "deduplicated"

    queued = NotificationCenter()
    queued.add_channel("bad", lambda note: False)
    queued.notify("X", "y")
    assert queued.card()["retry_queue"] == 1

    critical = []
    failing = NotificationCenter()
    failing.add_channel("bad", lambda note: False, min_severity="info")
    failing.add_channel("crit", lambda note: critical.append(note) or True, min_severity="critical")
    failing.notify("disk", "low", severity="info")
    assert failing.flush_retries() == 0
    assert critical == []
    assert failing.card()["retry_queue"] == 1
