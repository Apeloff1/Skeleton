"""Cancellation that refuses uncertain in-flight claims of success."""
from __future__ import annotations
from threading import Event
from .contracts import ServingError

class Cancellation:
    def __init__(self):self._event=Event()
    def cancel(self)->None:self._event.set()
    @property
    def event(self)->Event:return self._event
    def check(self)->None:
        if self._event.is_set():raise ServingError('requested operation cancelled')
