from __future__ import annotations

from skeleton.cortex import live
from skeleton.kernel.events import EventBus


def test_attach_tolerates_cortex_without_event_observer(monkeypatch):
    class CortexWithoutObserver:
        pass

    cortex = CortexWithoutObserver()
    bus = EventBus()
    monkeypatch.setattr(live, "live_cortex", lambda _bus: cortex)

    assert live.attach(bus) is cortex
    assert not hasattr(cortex, "_on_event")
