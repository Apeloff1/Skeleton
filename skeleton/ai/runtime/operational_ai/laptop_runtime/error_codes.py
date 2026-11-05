"""Stable public error classes with private prompt and file-path suppression."""
from __future__ import annotations
from .contracts import refuse

_KNOWN={"ContractViolation":"invalid-request","SpineError":"state-held",
        "Conflict":"conflict","Busy":"busy","Cancelled":"cancelled",
        "IntegrityFailure":"integrity-held","RuntimeError":"runtime-held",
        "TimeoutError":"deadline-held","OSError":"io-held",
        "GGUFManifestError":"model-held"}

def public_error(exc):
    kind=type(exc).__name__
    return {"status":"held","code":_KNOWN.get(kind,"operation-held"),
            "error_class":kind if kind in _KNOWN else "Unclassified",
            "retry_automatic":False}
