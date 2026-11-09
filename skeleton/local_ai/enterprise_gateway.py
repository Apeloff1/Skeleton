"""
Enterprise Gateway for Local AI.
Auth via CAS, rate limiting, audit logging, health checks, and full stack dispatch.
SOTA enterprise grade. Complete internals.
"""
from typing import Dict, Optional
from .full_stack import get_stack
from .rate_limiter import RateLimiter
from .audit_log import AuditLog
from .error_handler import ErrorHandler
from .health_monitor import HealthMonitor
from .fail_closed import guard_cas

class EnterpriseGateway:
    def __init__(self):
        self.stack = get_stack()
        self.limiter = RateLimiter(capacity=120)
        self.audit = AuditLog("chronicle/enterprise_audit.jsonl")
        self.handler = ErrorHandler()
        self.health = HealthMonitor()

    def request(self, prompt: str, cas: str, session: str = "enterprise") -> Dict:
        try:
            guard_cas(cas)
            allow = self.limiter.allow(cas)
            if not allow["allowed"]:
                raise PermissionError("rate limit exceeded")
            result = self.stack.run(prompt, cas, session)
            self.audit.log({"event": "request", "cas": cas[:8], "session": session, "ok": True})
            return {"status": "ok", "result": result, "health": self.health.check()}
        except Exception as e:
            recovered = self.handler.handle(e, {"prompt": prompt[:32], "cas": cas[:8]})
            self.audit.log({"event": "error", "type": type(e).__name__, "recovered": recovered})
            raise

    def status(self) -> Dict:
        return {"enterprise": True, "health": self.health.check(), "limiter": self.limiter.tokens}

def get_gateway() -> EnterpriseGateway:
    return EnterpriseGateway()
