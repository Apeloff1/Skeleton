"""Registry-aware s2s gate: mTLS-style binding + fail-closed nonce capacity.

:class:`RegistryS2SAuthGate` extends Pack F's :class:`S2SAuthGate`:

* **Certificate binding** - when the caller's :class:`ServiceIdentity` lists
  ``cert_fingerprints``, the request must present a matching client
  certificate fingerprint from an explicitly injected trusted ``cert_source``.
  By default no certificate source is trusted; raw request headers cannot
  assert mTLS identity. A token
  may also pin one fingerprint via ``ext["cnf"]``; it must then match too.
  Binding is checked *before* token verification so a mismatched request
  never records a nonce.
* **NonceStoreFull** - if the nonce store refuses to record a fresh nonce,
  the request is rejected with ``503 {"error": "nonce_store_full"}`` and a
  ``Retry-After`` header. It is never admitted.

Hooks (telemetry, audit) see every decision exactly once.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, Mapping, Optional

from skeleton.gate_plane.admit import AdmissionMatrix
from skeleton.gate_plane.s2s.authz import PolicyTable
from skeleton.gate_plane.s2s.gate import (
    DecisionHook,
    S2SAuthGate,
    S2SDecision,
    S2SOutcome,
    TokenExtractionError,
    extract_token,
)
from skeleton.gate_plane.s2s.nonce import is_nonce_store_full
from skeleton.gate_plane.s2s.registry import RegistryError, ServiceRegistry, normalize_fingerprint
from skeleton.gate_plane.s2s.tokens import TokenError, TokenErrorCode, split_token
from skeleton.gate_plane.s2s.verifier import RegistryVerifier

CERT_HEADER = "x-client-cert-sha256"
CNF_CLAIM = "cnf"
NONCE_STORE_FULL = "nonce_store_full"
BINDING_MISMATCH = "binding_mismatch"
BINDING_MISSING = "binding_missing"

CertSource = Callable[[Mapping[str, str]], Optional[str]]


def _missing_cert_source(_headers: Mapping[str, str]) -> Optional[str]:
    """Fail closed until a verified TLS termination boundary is configured."""
    return None


def header_cert_source(header: str = CERT_HEADER) -> CertSource:
    """Opt-in adapter ONLY when a trusted proxy strips client-supplied headers.

    The caller must authenticate mTLS upstream and overwrite this header;
    passing untrusted client headers as proof of a certificate is unsafe.
    """
    name = header.lower()

    def _source(headers: Mapping[str, str]) -> Optional[str]:
        for k, v in headers.items():
            if str(k).lower() == name:
                return str(v).strip() or None
        return None

    return _source


@dataclass(frozen=True)
class StatusDecision(S2SDecision):
    """An :class:`S2SDecision` with an explicit status / error (e.g. 503 nonce_store_full)."""

    status_override: int = 0
    error_override: str = ""

    @property
    def http_status(self) -> int:  # type: ignore[override]
        return self.status_override or super().http_status

    def body(self) -> Dict[str, Any]:
        out = super().body()
        if self.error_override:
            out["error"] = self.error_override
        return out

    def as_dict(self) -> Dict[str, Any]:
        out = super().as_dict()
        out["http_status"] = self.http_status
        if self.error_override:
            out["error"] = self.error_override
        return out


class RegistryS2SAuthGate(S2SAuthGate):
    def __init__(
        self,
        verifier: RegistryVerifier,
        policies: PolicyTable,
        *,
        matrix: Optional[AdmissionMatrix] = None,
        admission: bool = True,
        hooks: Iterable[DecisionHook] = (),
        cert_source: Optional[CertSource] = None,
    ) -> None:
        if not isinstance(verifier, RegistryVerifier):
            raise TypeError("RegistryS2SAuthGate needs a RegistryVerifier")
        # An authorization gate must never accept an opt-out of replay custody
        # or a permissive registry, even if those configurations exist for
        # standalone diagnostic/verifier use.
        if verifier.nonce_store is None:
            raise ValueError("registry s2s gate requires a replay nonce store")
        if not verifier.registry.strict:
            raise ValueError("registry s2s gate requires strict issuer registration")
        super().__init__(verifier, policies, matrix=matrix, admission=admission, hooks=hooks)
        self.registry: ServiceRegistry = verifier.registry
        self._local = threading.local()
        self.cert_source: CertSource = cert_source if cert_source is not None else _missing_cert_source

    # -- binding -----------------------------------------------------------
    def check_binding(self, headers: Mapping[str, str]) -> Optional[str]:
        """Return a rejection reason, or ``None`` when binding is satisfied / not required."""
        try:
            raw = extract_token(headers)
        except TokenExtractionError:
            return None  # base gate reports bad credentials
        if raw is None:
            return None
        try:
            _, claims, _, _ = split_token(raw)
        except TokenError:
            return None  # base gate reports malformed token
        iss = claims.get("iss")
        ident = self.registry.get(iss) if isinstance(iss, str) else None
        ext = claims.get("ext") if isinstance(claims.get("ext"), dict) else {}
        pinned = ext.get(CNF_CLAIM) if isinstance(ext, dict) else None
        required = ident is not None and ident.requires_binding
        if not required and pinned is None:
            return None
        presented_raw = self.cert_source(headers)
        if presented_raw is None:
            return BINDING_MISSING
        try:
            presented = normalize_fingerprint(presented_raw)
        except RegistryError:
            return BINDING_MISMATCH
        if required and presented not in ident.cert_fingerprints:  # type: ignore[union-attr]
            return BINDING_MISMATCH
        if pinned is not None:
            try:
                if normalize_fingerprint(str(pinned)) != presented:
                    return BINDING_MISMATCH
            except RegistryError:
                return BINDING_MISMATCH
        return None

    # -- evaluation ----------------------------------------------------------
    def evaluate(self, method: str, path: str, headers: Mapping[str, str]) -> S2SDecision:
        meth = (method or "GET").upper()
        p = path or "/"
        if not self.matrix.is_open(p):
            reason = self.check_binding(headers)
            if reason is not None:
                return self._emit(meth, p, self._unauth(reason, TokenErrorCode.BAD_CLAIMS))
        # Capture decisions from the base evaluate so we can intercept NonceStoreFull
        # without double-emitting to hooks.
        self._local.quiet = True
        try:
            decision = super().evaluate(meth, p, headers)
        except Exception as exc:  # noqa: BLE001 - only NonceStoreFull is mapped; others re-raise
            self._local.quiet = False
            if not is_nonce_store_full(exc):
                raise
            retry = str(max(1, int(getattr(exc, "retry_after_s", 1))))
            decision = StatusDecision(
                S2SOutcome.EMERGENCY_READ_ONLY,
                NONCE_STORE_FULL,
                headers=(("retry-after", retry),),
                status_override=503,
                error_override=NONCE_STORE_FULL,
            )
            return self._emit(meth, p, decision)
        self._local.quiet = False
        return self._emit(meth, p, decision)

    def _emit(self, method: str, path: str, decision: S2SDecision) -> S2SDecision:
        if getattr(self._local, "quiet", False):
            return decision
        return super()._emit(method, path, decision)


__all__ = [
    "BINDING_MISMATCH",
    "BINDING_MISSING",
    "CERT_HEADER",
    "CNF_CLAIM",
    "NONCE_STORE_FULL",
    "RegistryS2SAuthGate",
    "StatusDecision",
    "header_cert_source",
]
