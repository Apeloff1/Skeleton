"""Conservative host+cgroup memory proof for a *new* model image."""
from __future__ import annotations
from .contracts import AdmissionError, Reservation, CapacityPolicy


def check(policy: CapacityPolicy, reservation: Reservation) -> dict:
    if reservation.reserve_bytes > policy.budget_bytes:
        raise AdmissionError('model memory exceeds configured total capacity')
    measured = reservation.reserve_bytes + policy.minimum_host_margin_bytes
    # Memory telemetry is not a proof the native loader cannot fail: it is a
    # fail-closed low-memory rejection before model allocation or sidecar spawn.
    if measured > 8_000_000_000:
        raise AdmissionError('requested measured headroom exceeds observation limit')
    from ..isolation.resource_gate import require_headroom
    proof = require_headroom(measured)
    if not isinstance(proof, dict) or proof.get('admitted') is not True:
        raise AdmissionError('unknown local memory telemetry refused')
    return {'status': 'pre-activation-headroom-observed',
            'required_model_bytes': reservation.reserve_bytes,
            'observed': proof}
