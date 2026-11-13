"""Capacity-first deterministic inference projection.

No lease is acquired or native computation spent here. Full chat history
remains durable outside this *temporary* context window. The plan attempts
an exact bound when the backend exports a trustworthy count_tokens, otherwise
records that native enforcement remains unverified until generation.
"""
from __future__ import annotations
from hashlib import sha256
from ..contracts import Identity, SpineLimits, SpineError, canonical
from ..context import Evidence, compile_projection
from .contracts import CapacityPlan, CapacityPolicy
from .selection import select_initial, reduce
from .validation import bounded_sources, validate_history, validate_sources
from .tokenizer import check
from .proofs import decision_digest

CONTEXT_OVERFLOW = 'context must be trimmed before native tokenizer admission'
TOKEN_OVERFLOW = 'exact tokenizer context ceiling exceeded'


def prepare_context(*, identity: Identity, backend, history: tuple[dict, ...],
                    prompt: str, evidence=(), limits: SpineLimits,
                    policy: CapacityPolicy | None = None) -> CapacityPlan:
    policy = policy or CapacityPolicy()
    if not isinstance(identity, Identity) or not isinstance(limits, SpineLimits):
        raise SpineError('context planner requires pinned identity and limits')
    if not isinstance(prompt, str) or not prompt.strip() or len(prompt.encode('utf8')) > limits.input_bytes:
        raise SpineError('current prompt exceeds admission budget')
    if backend.model_digest != identity.model_sha256 or backend.tokenizer_digest != identity.tokenizer_sha256:
        raise SpineError('context backend identity mismatch')
    history_sha = validate_history(history, limits)
    candidates = bounded_sources(evidence, policy)
    evidence_sha = validate_sources(identity, candidates, policy)
    selection = select_initial(history, candidates, limits.max_sources)
    trials = 0
    while trials < policy.maximum_trials:
        trials += 1
        try:
            projection = compile_projection(identity, selection.history, prompt,
                                            selection.evidence, limits)
        except SpineError as exc:
            if str(exc) != CONTEXT_OVERFLOW:
                raise
        else:
            try:
                admitted = check(backend, projection.messages, limits,
                                 require_exact=policy.require_native_precount)
            except SpineError as exc:
                if str(exc) != TOKEN_OVERFLOW:
                    raise
            else:
                selected_sha = sha256(canonical([{
                    'source': item.source_id, 'revision': item.revision,
                    'sha256': item.sha256,
                } for item in selection.evidence])).hexdigest()
                proof_sha = decision_digest(identity, limits, projection.context_sha256,
                    history_sha, evidence_sha, selected_sha, selection.omitted_turns,
                    selection.omitted_sources, admitted.status, admitted.prompt_tokens)
                result = CapacityPlan(
                    projection=projection, history_digest=history_sha,
                    evidence_digest=evidence_sha, selected_evidence_digest=selected_sha,
                    retained_turns=len(selection.history)//2,
                    omitted_turns=selection.omitted_turns,
                    evidence_candidates=len(candidates),
                    retained_sources=len(selection.evidence),
                    omitted_sources=selection.omitted_sources,
                    trials=trials, token_status=admitted.status,
                    tokens=admitted.prompt_tokens,
                    conservative_estimate=projection.estimated_tokens,
                    proof_digest=proof_sha,
                    source_identities=tuple((item.source_id,item.revision,item.sha256)
                        for item in selection.evidence),
                )
                if result.retained_turns + result.omitted_turns != len(history)//2:
                    raise SpineError('lost context turn accounting')
                return result
        selection = reduce(selection)
        if selection is None:
            raise SpineError('current prompt cannot fit model context even without history or evidence')
    raise SpineError('context admission exhausted bounded planning attempts')
