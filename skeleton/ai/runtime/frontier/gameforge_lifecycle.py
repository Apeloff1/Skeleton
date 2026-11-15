"""Explicit service lifecycle with fail-safe stop semantics."""

from enum import Enum


class Lifecycle(str, Enum):
    NEW = "new"
    READY = "ready"
    DRAINING = "draining"
    STOPPED = "stopped"


class ServiceLifecycle:
    def __init__(self):
        self.state = Lifecycle.NEW

    @property
    def can_accept(self):
        return self.state is Lifecycle.READY

    @property
    def draining(self):
        return self.state is Lifecycle.DRAINING

    @property
    def stopped(self):
        return self.state is Lifecycle.STOPPED

    def ready(self):
        if self.state is not Lifecycle.NEW:
            raise RuntimeError("invalid ready transition")
        self.state = Lifecycle.READY
        return self.state

    def drain(self):
        if self.state is not Lifecycle.READY:
            raise RuntimeError("invalid drain transition")
        self.state = Lifecycle.DRAINING
        return self.state

    def stop(self):
        if self.state not in (Lifecycle.DRAINING, Lifecycle.NEW):
            raise RuntimeError("invalid stop transition")
        self.state = Lifecycle.STOPPED
        return self.state
