"""Authenticated-by-store, digest-bound preflight trace. Not a release signature."""
from __future__ import annotations
from hashlib import sha256
from ..contracts import SpineError, Identity, SpineLimits, canonical, digest, hexdigest
from .contracts import CapacityPlan


def describe_decision(plan: CapacityPlan) -> dict:
    """Deliberately omit plaintext prompts, snippets and private conversation."""
    return {
        'schema': 'skeleton.ai.context-capacity.v1',
        'projection_sha256': plan.projection.context_sha256,
        'history_sha256': plan.history_digest,
        'candidate_evidence_sha256': plan.evidence_digest,
        'selected_evidence_sha256': plan.selected_evidence_digest,
        'retained_turns': plan.retained_turns,
        'omitted_turns': plan.omitted_turns,
        'evidence_candidates': plan.evidence_candidates,
        'retained_sources': plan.retained_sources,
        'omitted_sources': plan.omitted_sources,
        'planning_trials': plan.trials,
        'token_admission': plan.token_status,
        'native_prompt_tokens': plan.tokens,
        'conservative_estimated_tokens': plan.conservative_estimate,
        'proof_sha256': plan.proof_digest,
    }


def decision_digest(identity: Identity, limits: SpineLimits, projection_sha: str,
                    history_sha: str, evidence_sha: str, selected_sha: str,
                    omitted_turns: int, omitted_sources: int,
                    token_status: str, count: int | None) -> str:
    for value in (projection_sha, history_sha, evidence_sha, selected_sha):
        hexdigest(value, 'context evidence digest')
    return digest({
        'schema': 'skeleton.ai.context-capacity.v1',
        'principal': identity.key(),
        'model': identity.model_sha256,
        'tokenizer': identity.tokenizer_sha256,
        'context_tokens': limits.context_tokens,
        'output_reserve': limits.max_output_tokens,
        'projection_sha256': projection_sha,
        'history_sha256': history_sha,
        'evidence_sha256': evidence_sha,
        'selected_sha256': selected_sha,
        'omitted_turns': omitted_turns,
        'omitted_sources': omitted_sources,
        'status': token_status,
        'native_count': count,
    })


def validate_decision(record: dict) -> dict:
    if type(record) is not dict or set(record) != {
        'schema','projection_sha256','history_sha256','candidate_evidence_sha256',
        'selected_evidence_sha256','retained_turns','omitted_turns',
        'evidence_candidates','retained_sources','omitted_sources',
        'planning_trials','token_admission','native_prompt_tokens',
        'conservative_estimated_tokens','proof_sha256'}:
        raise SpineError('malformed context capacity decision')
    if record['schema'] != 'skeleton.ai.context-capacity.v1':
        raise SpineError('unknown context capacity schema')
    for key in ('projection_sha256','history_sha256','candidate_evidence_sha256',
                'selected_evidence_sha256','proof_sha256'):
        hexdigest(record[key], key)
    for key in ('retained_turns','omitted_turns','evidence_candidates',
                'retained_sources','omitted_sources','planning_trials',
                'conservative_estimated_tokens'):
        if type(record[key]) is not int or record[key] < 0:
            raise SpineError('invalid context capacity metric')
    if record['retained_sources'] + record['omitted_sources'] != record['evidence_candidates']:
        raise SpineError('inconsistent context evidence count')
    if record['planning_trials'] < 1 or record['planning_trials'] > 8192:
        raise SpineError('invalid planning trial count')
    if record['token_admission'] not in ('exact-backend-count-admitted',
                                         'native-backend-must-enforce-unknown-precount'):
        raise SpineError('invalid token admission state')
    count = record['native_prompt_tokens']
    if count is not None and (type(count) is not int or count < 0):
        raise SpineError('invalid reported tokenizer count')
    if record['token_admission'] == 'exact-backend-count-admitted' and count is None:
        raise SpineError('native exact count missing')
    if record['token_admission'] != 'exact-backend-count-admitted' and count is not None:
        raise SpineError('unverified native token count claimed')
    return record
