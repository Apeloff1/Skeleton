"""One-call assembly of the registry-bound s2s gate.

Wires Pack F pieces (key ring, policy table, telemetry) with this slice's
registry, replay window, binding and audit trail. Opt-in: nothing here
touches ``skeleton/api/server.py``; apps call :func:`install_registry_s2s_gate`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Optional

from skeleton.gate_plane.admit import AdmissionMatrix
from skeleton.gate_plane.s2s.audit import AuditSink, S2SAuditTrail, TelemetryAuditSink
from skeleton.gate_plane.s2s.authz import PolicyTable, default_gate_plane_policies
from skeleton.gate_plane.s2s.bound_gate import CertSource, RegistryS2SAuthGate
from skeleton.gate_plane.s2s.clock import Clock
from skeleton.gate_plane.s2s.gate import install_s2s_gate
from skeleton.gate_plane.s2s.keyring import KeyRing
from skeleton.gate_plane.s2s.registry import ServiceRegistry
from skeleton.gate_plane.s2s.verifier import DEFAULT_CLOCK_SKEW_S, DEFAULT_MAX_AGE_S, RegistryVerifier


@dataclass
class S2SAssembly:
    gate: RegistryS2SAuthGate
    verifier: RegistryVerifier
    audit: S2SAuditTrail
    registry: ServiceRegistry
    keyring: KeyRing

    def sync_audit(self) -> int:
        return self.audit.sync_keyring(self.keyring)


def build_registry_s2s_gate(
    *,
    audience: str,
    keyring: KeyRing,
    registry: ServiceRegistry,
    nonce_store: Any,
    policies: Optional[PolicyTable] = None,
    telemetry: Any = None,
    audit_sinks: Iterable[AuditSink] = (),
    clock: Optional[Clock] = None,
    matrix: Optional[AdmissionMatrix] = None,
    admission: bool = True,
    max_age_s: float = DEFAULT_MAX_AGE_S,
    clock_skew_s: float = DEFAULT_CLOCK_SKEW_S,
    revoked_jtis: Any = None,
    cert_source: Optional[CertSource] = None,
) -> S2SAssembly:
    verifier = RegistryVerifier(
        audience, keyring, registry=registry, nonce_store=nonce_store, clock=clock,
        max_age_s=max_age_s, clock_skew_s=clock_skew_s, revoked_jtis=revoked_jtis,
    )
    trail = S2SAuditTrail(audit_sinks, clock=clock)
    if telemetry is not None:
        trail.add_sink(TelemetryAuditSink(telemetry))
    trail.watch_registry(registry)
    hooks = [trail.gate_hook]
    if telemetry is not None and hasattr(telemetry, "s2s_hook"):
        hooks.insert(0, telemetry.s2s_hook)
    gate = RegistryS2SAuthGate(
        verifier, policies if policies is not None else default_gate_plane_policies(),
        matrix=matrix, admission=admission, hooks=hooks, cert_source=cert_source,
    )
    return S2SAssembly(gate, verifier, trail, registry, keyring)


def install_registry_s2s_gate(app: Any, assembly: S2SAssembly) -> None:
    """Same registration contract as Pack F's :func:`install_s2s_gate`."""
    install_s2s_gate(app, assembly.gate)


__all__ = ["S2SAssembly", "build_registry_s2s_gate", "install_registry_s2s_gate"]
