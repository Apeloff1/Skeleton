"""A drain must hand shutdown back to the server, including repeated signals."""
import asyncio
import signal
from types import SimpleNamespace

from core.reliability import install_graceful_drain


def test_drain_forwards_to_server_after_grace(monkeypatch):
    async def scenario():
        received = []
        previous = lambda sig, frame: received.append((sig, frame))
        handlers = {signal.SIGTERM: previous, signal.SIGINT: previous}
        monkeypatch.setattr(signal, "getsignal", handlers.__getitem__)
        monkeypatch.setattr(signal, "signal", lambda sig, handler: handlers.__setitem__(sig, handler))
        app = SimpleNamespace(state=SimpleNamespace())
        install_graceful_drain(app, grace_seconds=.01)
        handlers[signal.SIGTERM](signal.SIGTERM, None)
        assert app.state._shedding is True
        assert received == []
        await asyncio.sleep(.03)
        assert received == [(signal.SIGTERM, None)]
    asyncio.run(scenario())


def test_second_signal_reaches_server_and_cancels_pending_handoff(monkeypatch):
    async def scenario():
        received = []
        previous = lambda sig, frame: received.append(sig)
        handlers = {signal.SIGTERM: previous, signal.SIGINT: previous}
        monkeypatch.setattr(signal, "getsignal", handlers.__getitem__)
        monkeypatch.setattr(signal, "signal", lambda sig, handler: handlers.__setitem__(sig, handler))
        app = SimpleNamespace(state=SimpleNamespace())
        install_graceful_drain(app, grace_seconds=.01)
        handlers[signal.SIGTERM](signal.SIGTERM, None)
        handlers[signal.SIGINT](signal.SIGINT, None)
        await asyncio.sleep(.03)
        assert received == [signal.SIGINT]
    asyncio.run(scenario())
