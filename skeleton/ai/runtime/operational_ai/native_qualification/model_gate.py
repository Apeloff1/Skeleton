"""Run only the actual authenticated Skeleton native offline AI service."""
from __future__ import annotations
from .errors import deny


def require_real_service(service):
    # Hard product boundary: no test-double bypass in the native qualification runner.
    from skeleton.ai.runtime.operational_ai.orchestration.service import OfflineAIService
    from skeleton.ai.runtime.operational_ai.model.native import NativeBackend
    if type(service) is not OfflineAIService:
        deny("real-service-required")
    if type(service.gateway.backend) is not NativeBackend:
        deny("native-backend-required")
    if not hasattr(service.store, "commit") or not hasattr(service.store, "replay"):
        deny("durable-chat-required")
    if not hasattr(service, "process_fence") or service.process_fence is None:
        deny("cross-process-session-fence-required")
    return service
