from __future__ import annotations
import hashlib,pytest
from skeleton.ai.governance.administration import AdminPrincipal,AdminRequest,AdministrationPlaneError,authorize_admin
def d(x): return hashlib.sha256(x.encode()).hexdigest()
def principal():
    return AdminPrincipal("operator",("config.read","config.write","break.fix"),d("identity"))
def test_admin_requires_scope_and_approval():
    decision=authorize_admin(principal=principal(),request=AdminRequest("r","operator","config.write","svc",d("approval")),approval_required=True)
    assert decision.allowed is True and decision.audit_receipt_required is True
def test_missing_scope_denied_without_effective_scope():
    decision=authorize_admin(principal=principal(),request=AdminRequest("r","operator","root.delete","svc",d("approval")))
    assert decision.allowed is False and decision.effective_scope is None
def test_break_glass_requires_distinct_receipt_path():
    denied=authorize_admin(principal=principal(),request=AdminRequest("r","operator","break.fix","svc"),break_glass_capabilities=("break.fix",))
    assert denied.allowed is False and "break-glass-receipt-required" in denied.reasons
    allowed=authorize_admin(principal=principal(),request=AdminRequest("r2","operator","break.fix","svc",None,d("break")),break_glass_capabilities=("break.fix",))
    assert allowed.allowed is True and allowed.break_glass_used is True
