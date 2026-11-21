"""PROOD publication uses durable admission and restart replay."""
import asyncio
from gameforge.prood import event_sink
from gameforge.prood.event_bus import EventBus
from zaibatsu.outbox import Outbox


def test_journal_precedes_fanout_and_recovers(monkeypatch, tmp_path):
    async def scenario():
        remote = {}
        async def apply(collection, doc):
            remote.setdefault(doc["_outbox_id"], doc.copy())
        bus = EventBus()
        path = tmp_path / "events.sqlite3"
        first = Outbox(apply, path=path)
        monkeypatch.setattr(event_sink, "_outbox", first)
        monkeypatch.setattr(event_sink, "_installed", False)
        monkeypatch.setattr(event_sink, "event_bus", bus)
        async def observe(_):
            assert await first.pending_count() == 1
        bus.subscribe("iq.grow", observe)
        assert event_sink.install_event_sink()
        assert not event_sink.install_event_sink()
        record = await bus.publish("iq.grow", {"iq": 101})
        assert record["persistence"] == "journaled"
        assert record["delivered"] == 1
        assert remote == {}
        monkeypatch.setattr(event_sink, "_outbox", Outbox(apply, path=path))
        result = await event_sink.flush_pending_events()
        assert result["confirmed"] == 1 and result["pending"] == 0
        assert list(remote.values())[0]["payload"] == {"iq": 101}
    asyncio.run(scenario())


def test_invalid_event_reports_no_custody(monkeypatch, tmp_path):
    async def scenario():
        async def apply(collection, doc):
            raise AssertionError("must not deliver")
        box = Outbox(apply, path=tmp_path / "events.sqlite3")
        bus = EventBus()
        monkeypatch.setattr(event_sink, "_outbox", box)
        monkeypatch.setattr(event_sink, "_installed", False)
        monkeypatch.setattr(event_sink, "_admission_failures", 0)
        monkeypatch.setattr(event_sink, "event_bus", bus)
        event_sink.install_event_sink()
        record = await bus.publish("bad", {"value": float("nan")})
        assert record["persistence"] == "unavailable"
        assert await box.pending_count() == 0
        assert event_sink._admission_failures == 1
    asyncio.run(scenario())
