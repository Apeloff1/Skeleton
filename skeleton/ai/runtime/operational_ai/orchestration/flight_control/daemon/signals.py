"""Portable CLI signal-to-exception conversion, without HTTPServer deadlock."""
from __future__ import annotations
from contextlib import contextmanager
import signal
from threading import current_thread,main_thread

@contextmanager
def termination_interrupt():
    """Convert SIGTERM into KeyboardInterrupt so context unwinding drains.

    Must be installed only by the CLI's main thread. Never call server.shutdown
    inside a signal handler: BaseServer.shutdown waits on serve_forever and
    would deadlock if called in the same thread.
    """
    if current_thread() is not main_thread():
        raise RuntimeError('signal handling must use main thread')
    original=signal.getsignal(signal.SIGTERM)
    def interrupt(*_):
        raise KeyboardInterrupt('local inference termination requested')
    signal.signal(signal.SIGTERM,interrupt)
    try:yield
    finally:signal.signal(signal.SIGTERM,original)
