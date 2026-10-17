"""App foundation backend services (users/auth/sessions, projects/builds,
build job queue, asset storage).

Hexagonal layout: ``ports`` declares the Protocols; ``sqlite_*`` modules and
``assets`` are local adapters.  Nothing here mounts HTTP routes and no secret
or token material is ever returned over a transport by these services
(see issue #3637).  HTTP wiring belongs to Backend; authN/Z gates belong to
Middleware and consume ``AuthService.resolve_session`` through the
``SessionResolver`` port.
"""
from skeleton.app_services import job_api
from skeleton.app_services.job_api import (
    JobContext,
    JobHandle,
    JobResult,
    JobStatus,
    JobWorker,
    cancel,
    enqueue,
    get_result,
    get_status,
    register_handler,
    start_worker,
)
from skeleton.app_services.events import (
    ENVELOPE_VERSION,
    EventBusBridge,
    FanOutPublisher,
    JobEventPublisher,
    NullJobEventPublisher,
    make_envelope,
)

__all__ = [
    "job_api", "JobContext", "JobHandle", "JobResult", "JobStatus", "JobWorker",
    "cancel", "enqueue", "get_result", "get_status", "register_handler", "start_worker",
    "ENVELOPE_VERSION",
    "EventBusBridge",
    "FanOutPublisher",
    "JobEventPublisher",
    "NullJobEventPublisher",
    "make_envelope",
]
