"""Read-only context admission for newly queued, not-yet-executed requests.

This is a *capacity snapshot*, not a promise that context will be identical
when a queue worker eventually starts. Workers independently re-run preflight
under session fencing. Source freshness is checked at authoritative commit.
"""
from __future__ import annotations
from ..execution_spine.capacity.preview import preview
from ..execution_spine.contracts import SpineError
from .contracts import FlightSpec, FlightConflict


def inspect_before_submit(ledger, spine, spec: FlightSpec) -> dict:
    if not isinstance(spec, FlightSpec):
        raise FlightConflict('typed flight request required for preflight')
    if ledger.identity != spine.identity or spec.identity != spine.identity:
        raise FlightConflict('flight admission principal/model mismatch')
    # An already accepted job must be replayable without requiring old source
    # material or old model capacity settings to remain available. The ledger
    # independently revalidates the *entire original* request fingerprint.
    try:
        ledger.inspect(spec.job_id)
    except FlightConflict as exc:
        # Missing IDs are normal; other ledger integrity/custody errors must
        # block, not masquerade as absence.
        if str(exc) != 'flight job not found':
            raise
    else:
        return {'status':'existing-job-verify-with-ledger','context_preflight':'not-repeated'}
    report = preview(spine, spec.session, spec.prompt)
    # Only source/projection digests and bounded metrics are surfaced. The
    # generated chat response remains unknown until the native worker executes.
    return {
        'status':'new-job-context-preflight-admitted-not-execution-attestation',
        'context_sha256':report['projection_sha256'],
        'token_status':report['token_admission'],
        'omitted_turns':report['omitted_turns'],
        'omitted_sources':report['omitted_sources'],
        'model_calls':0,
    }
