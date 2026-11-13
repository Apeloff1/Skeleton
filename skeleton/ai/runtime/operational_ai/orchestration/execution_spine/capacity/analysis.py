"""Conservative, private capacity telemetry for read-only operational review."""
from __future__ import annotations
from ..contracts import SpineError
from .proofs import validate_decision


def summarize(decisions: tuple[dict, ...], *, limit: int = 1024) -> dict:
    if type(decisions) is not tuple or type(limit) is not int or not 1 <= limit <= 4096:
        raise SpineError('invalid context capacity telemetry window')
    if len(decisions) > limit:
        raise SpineError('context telemetry window exceeds bound')
    exact = missing = omitted_turns = omitted_sources = attempts = 0
    max_estimate = 0
    for record in decisions:
        validate_decision(record)
        if record['token_admission'] == 'exact-backend-count-admitted':
            exact += 1
        else:
            missing += 1
        omitted_turns += record['omitted_turns']
        omitted_sources += record['omitted_sources']
        attempts += record['planning_trials']
        max_estimate = max(max_estimate,record['conservative_estimated_tokens'])
    return {'schema':'skeleton.ai.capacity-rollup.v1',
            'decisions':len(decisions), 'native_precounter_verified':exact,
            'native_precounter_unverified':missing,'omitted_history_turns':omitted_turns,
            'omitted_evidence_sources':omitted_sources,'total_planning_trials':attempts,
            'largest_conservative_estimate':max_estimate,
            'status':'diagnostic-not-release-evidence'}
