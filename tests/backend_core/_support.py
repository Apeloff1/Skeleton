from __future__ import annotations

from core.core_v1.clock import FakeClock
from core.core_v1.memory_store import (MemoryDeliveryRepository, MemoryEventRepository,
                                       MemorySecretRepository, MemorySubscriptionRepository)
from core.core_v1.models import Scope
from core.core_v1.pagination import CursorCodec
from core.core_v1.service import WebhookService
from core.core_v1.transport import AllowAllPolicy, RecordingTransport

ADMIN = Scope("t1", "a@example.com", "admin")
VIEWER = Scope("t1", "v@example.com", "viewer")
OTHER = Scope("t2", "o@example.com", "admin")


def memory_service(**kw):
    clock = kw.pop("clock", FakeClock())
    transport = kw.pop("transport", RecordingTransport())
    svc = WebhookService(subs=MemorySubscriptionRepository(), secrets=MemorySecretRepository(),
                         events=MemoryEventRepository(), deliveries=MemoryDeliveryRepository(),
                         transport=transport, url_policy=AllowAllPolicy(), clock=clock,
                         cursor_codec=CursorCodec(b"k" * 32), **kw)
    return svc, clock, transport
