"""Canonical crawl checkpoints become companion events without a second store."""
import asyncio
from datetime import datetime, timezone

import pytest

from core.dragon_crawler import CrawlerError, DragonCrawlerApplication
from skeleton.ai.webcrawler.dragon_capture_projection import (
    GENESIS,
    CompanionCursorError,
    project_companion_feed,
)
from skeleton.ai.webcrawler.operations import CrawlRequest, CrawlRun

SEED = "https://example.org/start"
HIDDEN = {"burn_started", "burn_chunk", "burn_complete", "distill_complete", "acquisition_accepted"}


def _event(sequence, kind, **extra):
    event = {
        "sequence": sequence,
        "kind": kind,
        "at": 1_000_000.0 + sequence,
        "url": "https://example.org/page",
        "reason": extra.pop("reason", None),
        "event_digest": "ab" * 32,
    }
    event.update(extra)
    return event


def _page(events, **kwargs):
    return project_companion_feed("session-1", events, fallback_url=SEED, **kwargs)


def test_captured_checkpoint_projects_without_burn_or_page_text():
    page = _page([
        _event(1, "dispatch_reserved"),
        _event(2, "captured", reason="kept\nnote", usage={"requests": 4}, source_id="source-1"),
        _event(3, "completed", reason="frontier_drained"),
    ])
    assert [event["kind"] for event in page["events"]] == [
        "fetch_started", "fetch_received", "crawl_complete",
    ]
    assert HIDDEN.isdisjoint(event["kind"] for event in page["events"])
    assert page["events"][1]["previous_digest"] == page["events"][0]["digest"]
    assert page["events"][1]["digest"] == page["events"][1]["event_id"]
    assert page["events"][0]["previous_digest"] == GENESIS
    payload = page["events"][1]["payload"]
    assert payload["source"] == "canonical_crawler_checkpoint"
    assert payload["operational_kind"] == "captured"
    assert payload["reason"] == "keptnote"
    assert "usage" not in payload and "text" not in payload and "source_id" not in payload
    assert page["history_truncated"] is False
    assert page["source"] == "canonical_crawler_checkpoint"


def test_http_retry_waits_instead_of_reading_the_page():
    page = _page([_event(1, "retry", reason="http_503:scheduled")])
    assert page["events"][0]["kind"] == "retry_wait"
    assert page["events"][0]["payload"]["operational_kind"] == "retry"
    assert page["events"][0]["payload"]["reason"] == "http_503:scheduled"


def test_slice_capture_projects_into_the_companion_chain():
    import time
    from skeleton.ai.webcrawler.core import FetchResponse

    class Fetcher:
        def fetch_once(self, url, *, user_agent, max_bytes):
            if url.endswith("/robots.txt"):
                body = b"User-agent: *\nAllow: /\n"
                return FetchResponse(url, 200, {"content-type": "text/plain"}, body, time.time())
            body = b"<title>Root</title><main>Hello world</main>"
            return FetchResponse(url, 200, {"content-type": "text/html"}, body, time.time())

    started = time.time()
    run = CrawlRun.create(
        CrawlRequest(
            seed_urls=("https://example.org/",),
            allowed_hosts=("example.org",),
            min_host_delay_seconds=0.25,
        ),
        scope={"tenant_id": "tenant", "owner_id": "owner"},
        consent={
            "consent_id": "consent-slice",
            "capture_acknowledged": True,
            "source_rights_acknowledged": True,
            "expires_at": started + 3600,
        },
        now=started,
        fetcher=Fetcher(),
    )
    # run_slice installs these before the first network checkpoint.
    run._authorize = None
    run._cancelled = None
    run._on_checkpoint = None
    assert run._step(started) is not None
    assert run._step(started + 5) is not None
    projected = project_companion_feed(
        "session-slice", run.snapshot()["events"], fallback_url="https://example.org/",
    )
    assert [event["kind"] for event in projected["events"]] == [
        "fetch_started", "robots_check", "fetch_started", "fetch_received",
    ]
    assert HIDDEN.isdisjoint(event["kind"] for event in projected["events"])
    assert projected["events"][3]["payload"]["operational_kind"] == "captured"
    assert "text" not in projected["events"][3]["payload"]
    assert projected["events"][1]["previous_digest"] == projected["events"][0]["digest"]
    assert projected["events"][3]["previous_digest"] == projected["events"][2]["digest"]
    assert projected["history_truncated"] is False


def test_unknown_and_burn_labels_stay_visual_probes():
    page = _page([_event(1, "burn_complete"), _event(2, "mystery")])
    assert [event["kind"] for event in page["events"]] == ["visual_probe", "visual_probe"]
    assert page["events"][0]["payload"]["operational_kind"] == "burn_complete"
    assert "persisted" not in page["events"][0]["payload"]


def test_truncated_tail_keeps_operational_sequence_and_genesis_link():
    page = _page([_event(8, "robots", url=None), _event(9, "resume")])
    assert page["history_truncated"] is True
    assert [event["sequence"] for event in page["events"]] == [8, 9]
    assert page["events"][0]["previous_digest"] == GENESIS
    assert page["events"][0]["url"] == SEED
    assert page["events"][0]["kind"] == "robots_check"
    assert page["events"][1]["kind"] == "frontier_discovered"
    followed = _page(
        [_event(8, "robots", url=None), _event(9, "resume")],
        after_sequence=8,
        expected_digest=page["events"][0]["digest"],
    )
    assert [event["sequence"] for event in followed["events"]] == [9]
    with pytest.raises(CompanionCursorError, match="journal head"):
        _page([_event(8, "robots")], after_sequence=8, expected_digest="cd" * 32)
    with pytest.raises(CompanionCursorError, match="digest cursor"):
        _page([_event(1, "captured")], expected_digest="zz" * 32)


def test_missing_url_and_gap_fail_closed():
    with pytest.raises(ValueError, match="companion-replayable"):
        project_companion_feed("session-1", [_event(1, "pause", url=None)], fallback_url=None)
    with pytest.raises(ValueError, match="companion-replayable"):
        _page([_event(4, "captured"), _event(6, "captured")])


class _Sessions:
    def __init__(self, rows):
        self.rows = rows

    async def find_one(self, query, sort=None):
        matched = []
        for row in self.rows:
            if row.get("tenant_id") != query.get("tenant_id") or row.get("owner_id") != query.get("owner_id"):
                continue
            status = query.get("status")
            if isinstance(status, dict) and row.get("status") == status.get("$ne"):
                continue
            matched.append(row)
        matched.sort(key=lambda row: (row["updated_at"], row["_id"]), reverse=True)
        return matched[0] if matched else None


def _snapshot():
    run = CrawlRun.create(
        CrawlRequest(seed_urls=(SEED,), allowed_hosts=("example.org",)),
        scope={"tenant_id": "tenant", "owner_id": "owner"},
        consent={
            "consent_id": "consent-1",
            "capture_acknowledged": True,
            "source_rights_acknowledged": True,
            "expires_at": 1_000_000.0,
        },
        now=999_000.0,
    )
    run._event("captured", now=999_100.0, url=SEED, source_id=None, reason="stored_as_evidence")
    return run.snapshot()


def _application(rows):
    application = DragonCrawlerApplication.__new__(DragonCrawlerApplication)
    application.sessions = _Sessions(rows)
    return application


def test_companion_feed_uses_latest_checkpoint_and_keeps_cursor_conflicts():
    scope = {"tenant_id": "tenant", "owner_id": "owner"}
    older = datetime(2026, 10, 1, tzinfo=timezone.utc)
    newer = datetime(2026, 10, 2, tzinfo=timezone.utc)
    application = _application([
        {
            "_id": "old", **scope, "status": "completed", "updated_at": older,
            "snapshot": _snapshot(), "request": {"seed_urls": [SEED]},
        },
        {
            "_id": "new", **scope, "status": "queued", "updated_at": newer,
            "snapshot": _snapshot(), "request": {"seed_urls": [SEED]},
        },
        {
            "_id": "gone", **scope, "status": "deleted", "updated_at": datetime(2026, 10, 3, tzinfo=timezone.utc),
            "snapshot": _snapshot(), "request": {"seed_urls": [SEED]},
        },
    ])
    feed = asyncio.run(application.companion_feed(scope))
    assert feed["active"] is True and feed["session_id"] == "new"
    assert feed["events"][0]["kind"] == "fetch_received"
    assert feed["events"][0]["payload"]["operational_kind"] == "captured"
    assert HIDDEN.isdisjoint(event["kind"] for event in feed["events"])
    with pytest.raises(CompanionCursorError, match="journal head"):
        asyncio.run(application.companion_feed(scope, after_sequence=1, expected_digest="ab" * 32))
    empty = asyncio.run(_application([]).companion_feed(scope))
    assert empty["active"] is False and empty["events"] == []
    broken = _application([
        {"_id": "bad", **scope, "status": "queued", "updated_at": newer, "snapshot": {"events": []}, "request": {}},
    ])
    with pytest.raises(CrawlerError, match="companion-replayable"):
        asyncio.run(broken.companion_feed(scope))
